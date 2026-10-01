#!/usr/bin/env python3

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from domain.scoring import calculate_summary
from domain.workflow import normalize_form_workflow
from pipeline.sections import section_script_path
from review_app.paths import (
    FORM_SCHEMA_PATH,
    PIPELINE_OUT_DIR,
    RUNS_DIR,
    resolve_questions_path,
)

ROOT = Path(__file__).resolve().parent
OUT = PIPELINE_OUT_DIR
OUT.mkdir(parents=True, exist_ok=True)
RUNS = RUNS_DIR
RUNS.mkdir(parents=True, exist_ok=True)

SKELETON = resolve_questions_path()
SCHEMA_PATH = FORM_SCHEMA_PATH

REPO_RE = re.compile(r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<name>[A-Za-z0-9_.-]+)$")


def _normalize_repo_name(name: str) -> str:
    return name[:-4] if name.endswith(".git") else name


def log_line(level: str, message: str, *, err: bool = False) -> None:
    stream = sys.stderr if err else sys.stdout
    print(f"[{level}] {message}", file=stream, flush=True)


def parse_owner_repo(repo_input: str) -> tuple[str, str, str | None]:
    s = repo_input.strip()
    if s.startswith("git@"):
        m = re.search(r":([^/]+)/([^/]+?)(?:\.git)?$", s)
        if not m:
            raise ValueError(f"Cannot parse repo from '{repo_input}'")
        return m.group(1), m.group(2), None
    if s.startswith("http://") or s.startswith("https://"):
        parsed = urlparse(s)
        host = parsed.netloc.lower()
        if host not in {"github.com", "www.github.com"}:
            raise ValueError(f"Cannot parse GitHub URL: '{repo_input}'")
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2:
            raise ValueError(f"Cannot parse GitHub URL: '{repo_input}'")
        owner = parts[0]
        name = _normalize_repo_name(parts[1])
        ref = None
        if len(parts) >= 4 and parts[2] == "tree":
            raw_ref = "/".join(parts[3:])
            ref = unquote(raw_ref).strip("/") or None
        return owner, name, ref
    m = REPO_RE.match(s)
    if m:
        return m.group("owner"), m.group("name"), None
    raise ValueError(f"Unsupported repo format: '{repo_input}'")


def run(cmd: list[str], env: dict | None = None) -> int:
    log_line("INFO", f"CMD {' '.join(shlex.quote(c) for c in cmd)}")
    p = subprocess.run(cmd, env=env)
    return p.returncode


def _parse_dotenv(path: Path) -> dict:
    env: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return env


def _read_token() -> str | None:
    env_tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if env_tok:
        return env_tok.strip() or None
    dotenv = ROOT / ".env"
    if dotenv.exists():
        env_map = _parse_dotenv(dotenv)
        return env_map.get("GITHUB_TOKEN") or env_map.get("GH_TOKEN")
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Run all scripts 1..5 for a given GitHub repository")
    ap.add_argument(
        "repo", help="Repo URL or owner/repo (e.g., https://github.com/org/name or org/name)"
    )
    ap.add_argument(
        "--run-id",
        default=os.environ.get("REVIEW_RUN_ID", "").strip() or None,
        help="Isolated evaluation/run id (default: new uuid). Output goes to data/runs/<id>/.",
    )
    args = ap.parse_args()

    try:
        owner, name, requested_ref = parse_owner_repo(args.repo)
    except ValueError as e:
        log_line("WARN", f"PIPELINE INPUT ERROR {e}", err=True)
        return 2

    run_id = "".join(ch for ch in (args.run_id or uuid.uuid4().hex) if ch.isalnum() or ch in "-_")
    if not run_id:
        run_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc).isoformat()

    log_line(
        "START",
        f"PIPELINE START repo={owner}/{name} requested_ref={requested_ref or '-'} run_id={run_id}",
    )

    outdir = OUT.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    runs_root = RUNS.resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if not SKELETON.exists():
        log_line("WARN", f"PIPELINE ABORT missing skeleton form: {SKELETON}", err=True)
        return 3

    env = os.environ.copy()
    # Ensure child scripts can import `utils.*` when executed from the scripts/ directory
    # by exposing the project root on PYTHONPATH.
    root_str = str(ROOT)
    prev_pp = env.get("PYTHONPATH", "").strip()
    if prev_pp:
        env["PYTHONPATH"] = root_str + os.pathsep + prev_pp
    else:
        env["PYTHONPATH"] = root_str
    env.setdefault("PYTHONUTF8", "1")
    env["REVIEW_RUN_ID"] = run_id
    token_value = _read_token()
    if token_value:
        env["GITHUB_TOKEN"] = token_value
        env["GH_TOKEN"] = token_value
        log_line("INFO", "TOKEN source=env_or_dotenv present=yes")
    else:
        log_line("WARN", "TOKEN source=env_or_dotenv present=no")
    if requested_ref:
        env["REPO_REF"] = requested_ref
        log_line("INFO", f"REPO_REF requested={requested_ref}")
    else:
        env.pop("REPO_REF", None)

    py = sys.executable

    working_form = run_dir / "form.json"
    try:
        with (
            open(SKELETON, encoding="utf-8") as sf,
            open(working_form, "w", encoding="utf-8") as wf,
        ):
            skeleton = json.load(sf)
            if isinstance(skeleton, dict):
                meta = skeleton.setdefault("meta", {})
                if isinstance(meta, dict):
                    meta["repo"] = f"{owner}/{name}"
                    meta["requested_ref"] = requested_ref or ""
                    meta["evaluation_id"] = run_id
                    meta["run_id"] = run_id
                    meta["started_at"] = started_at
            json.dump(skeleton, wf, ensure_ascii=False, indent=2)
    except Exception as e:
        log_line("WARN", f"PIPELINE ABORT init working form failed: {e}", err=True)
        return 4
    log_line("INFO", f"WORKING_FORM initialized path={working_form} run_id={run_id}")

    steps: list[tuple[str, str, list[str]]] = [
        (
            "1",
            "Prerequisites and baseline project signals",
            [
                py,
                str(section_script_path("1")),
                "--owner",
                owner,
                "--repo",
                name,
                "--input",
                str(working_form),
                "--output",
                str(working_form),
            ],
        ),
        (
            "2",
            "Open source quality and maintenance heuristics",
            [
                py,
                str(section_script_path("2")),
                "--repo",
                f"{owner}/{name}",
                "--skeleton",
                str(working_form),
                "--out",
                str(working_form),
            ],
        ),
        (
            "3",
            "Code quality and CI/security posture",
            [
                py,
                str(section_script_path("3")),
                "--repo",
                f"{owner}/{name}",
                "--input",
                str(working_form),
                "--output",
                str(working_form),
            ],
        ),
        (
            "4",
            "Documentation quality and usability checks",
            [
                py,
                str(section_script_path("4")),
                "--repo",
                f"{owner}/{name}",
                "--input",
                str(working_form),
                "--output",
                str(working_form),
            ],
        ),
    ]

    section5_cmd = [
        py,
        str(section_script_path("5")),
        "--owner",
        owner,
        "--repo",
        name,
        "--input",
        str(working_form),
        "--output",
        str(working_form),
    ]
    if requested_ref:
        section5_cmd.extend(["--ref", requested_ref])
    steps.append(("5", "Security API and crypto capability checks", section5_cmd))

    failed_steps: list[str] = []
    for step_id, step_label, step_cmd in steps:
        log_line("STEP", f"{step_id}/5 START {step_label}")
        rc = run(step_cmd, env)
        if rc == 0:
            log_line("DONE", f"{step_id}/5 DONE {step_label}")
        else:
            failed_steps.append(step_id)
            log_line("WARN", f"{step_id}/5 FAIL exit={rc} {step_label}", err=True)

    log_line("STEP", "FINALIZE START normalization and workflow sync")
    try:
        with open(working_form, encoding="utf-8") as f:
            form_obj: dict[str, Any] = json.load(f)

        form_meta = form_obj.setdefault("meta", {})
        if isinstance(form_meta, dict):
            form_meta.setdefault("repo", f"{owner}/{name}")
            form_meta["evaluation_id"] = run_id
            form_meta["run_id"] = run_id
            form_meta.setdefault("started_at", started_at)
            form_meta["finished_at"] = datetime.now(timezone.utc).isoformat()
            section_meta = None
            for sec in form_obj.get("sections", []):
                if isinstance(sec, dict) and isinstance(sec.get("meta"), dict):
                    section_meta = sec.get("meta")
                    break
            fallback_effective_ref = ""
            if isinstance(section_meta, dict):
                fallback_effective_ref = str(
                    section_meta.get("effective_ref") or section_meta.get("default_branch") or ""
                ).strip()

            effective_ref = requested_ref or fallback_effective_ref
            form_meta["requested_ref"] = requested_ref or ""
            form_meta["effective_ref"] = effective_ref or ""
            form_meta["evaluated_repo_version"] = effective_ref or ""
            # Surface SHA only when ref itself looks like a commit.
            if re.fullmatch(r"[0-9a-fA-F]{7,40}", effective_ref or ""):
                form_meta["commit_sha"] = effective_ref.lower()
            form_meta["collection_failed_steps"] = list(failed_steps)
            if not failed_steps:
                form_meta["collection_status"] = "done"
            elif len(failed_steps) >= 5:
                form_meta["collection_status"] = "failed"
            else:
                form_meta["collection_status"] = "partial"

            try:
                from domain.meta_enrichment import enrich_form_meta

                enrich_form_meta(form_obj)
            except Exception as enrich_err:
                log_line("WARN", f"FINALIZE META enrich skipped: {enrich_err}", err=True)

        if requested_ref:
            for sec in form_obj.get("sections", []):
                if not isinstance(sec, dict):
                    continue
                sec_meta = sec.setdefault("meta", {})
                if isinstance(sec_meta, dict):
                    sec_meta.setdefault("requested_ref", requested_ref)

        def normalize_evidence_value(val: Any) -> str:
            def list_to_str(lst: list[Any]) -> str:
                out: list[str] = []
                seen = set()
                for item in lst:
                    s = ""
                    if isinstance(item, str):
                        s = item.strip()
                    elif isinstance(item, dict):
                        u = str(item.get("url") or item.get("href") or "").strip()
                        s = u if u else json.dumps(item, ensure_ascii=False)
                    else:
                        s = str(item).strip()
                    if s and s not in seen:
                        seen.add(s)
                        out.append(s)
                return "\n".join(out)

            if isinstance(val, list):
                return list_to_str(val)
            if isinstance(val, str):
                s = val.strip()
                if s.startswith("[") and s.endswith("]"):
                    try:
                        parsed = json.loads(s)
                        if isinstance(parsed, list):
                            return list_to_str(parsed)
                    except Exception:
                        pass
                if ";" in s and "http" in s:
                    parts = [p.strip() for p in s.split(";") if p.strip()]
                    return "\n".join(parts)
                return s
            return str(val)

        for sec in form_obj.get("sections", []):
            for q in sec.get("questions", []) if isinstance(sec.get("questions"), list) else []:
                q["evidence"] = normalize_evidence_value(q.get("evidence", ""))

        form_obj = normalize_form_workflow(form_obj, pipeline_mode=True)

        with open(working_form, "w", encoding="utf-8") as f:
            json.dump(form_obj, f, ensure_ascii=False, indent=2)
        log_line("DONE", "FINALIZE DONE normalization and workflow sync")
    except Exception as e:
        log_line("WARN", f"FINALIZE FAIL normalization and workflow sync: {e}", err=True)

    if SCHEMA_PATH.exists():
        log_line("STEP", "FINALIZE START schema validation")
        try:
            from jsonschema import validate

            with open(SCHEMA_PATH, encoding="utf-8") as sf:
                schema = json.load(sf)
            with open(working_form, encoding="utf-8") as f:
                form_final = json.load(f)
            validate(instance=form_final, schema=schema)
            log_line("DONE", "FINALIZE DONE schema validation PASS")
        except Exception as e:
            log_line("WARN", f"FINALIZE FAIL schema validation: {e}", err=True)
    else:
        log_line("WARN", f"FINALIZE SKIP schema validation missing schema at {SCHEMA_PATH}")

    log_line("STEP", "FINALIZE START summary scoring")
    try:
        with open(working_form, encoding="utf-8") as f:
            form_sc: dict[str, Any] = json.load(f)

        summary = calculate_summary(form_sc)
        form_sc["summary"] = summary
        with open(working_form, "w", encoding="utf-8") as f:
            json.dump(form_sc, f, ensure_ascii=False, indent=2)
        log_line(
            "DONE",
            f"FINALIZE DONE summary scoring grade={summary['grade']} overall={summary['overall_score']}%",
        )
    except Exception as e:
        log_line("WARN", f"FINALIZE FAIL summary scoring: {e}", err=True)

    log_line("DONE", f"PIPELINE DONE Aggregated form: {working_form}")

    # Convenience copy under data/ with unique suffix so two runs of the same repo never collide.
    try:
        with open(working_form, encoding="utf-8") as f:
            final_obj = json.load(f)
        if isinstance(final_obj, dict):
            final_obj["_evaluation_id"] = run_id
            final_obj["_draft_id"] = run_id
            meta = final_obj.setdefault("meta", {})
            if isinstance(meta, dict):
                meta["evaluation_id"] = run_id
                meta["run_id"] = run_id
            with open(working_form, "w", encoding="utf-8") as f:
                json.dump(final_obj, f, ensure_ascii=False, indent=2)
        alias = outdir / f"form_{owner}_{name}_{run_id[:8]}.json"
        alias.write_text(
            json.dumps(final_obj, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        log_line("INFO", f"PIPELINE ALIAS written path={alias}")
        (run_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "repo": f"{owner}/{name}",
                    "requested_ref": requested_ref or "",
                    "started_at": started_at,
                    "form_path": str(working_form),
                    "alias_path": str(alias),
                    "failed_steps": failed_steps,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception as e:
        log_line("WARN", f"PIPELINE ALIAS FAIL {e}", err=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
