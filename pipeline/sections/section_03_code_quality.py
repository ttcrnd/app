#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import re
import sys
import time
from typing import Any

try:
    from pipeline.localization import boolean_text, text
except ModuleNotFoundError:  # pragma: no cover
    try:
        from localization import boolean_text, text
    except ModuleNotFoundError:  # pragma: no cover
        from scripts.localization import boolean_text, text  # type: ignore

from domain.docs import extract_links_from_markdown as _extract_md_links
from integrations.github import get as _gh_get
from integrations.github import paginate as _gh_paginate
from integrations.http import http_get as _http_get


def http_get(
    url: str, headers: dict[str, str] | None = None, timeout: int = 30
) -> tuple[int, dict[str, Any], bytes]:
    status, data, _ = _http_get(url, headers=headers or {}, timeout=timeout)
    js: dict[str, Any] = {}
    try:
        if data:
            js = json.loads(data.decode("utf-8"))
    except Exception:
        js = {}
    return status, js, data


REPO = os.environ.get("REPO", "").strip()
OWNER, REPO_NAME = REPO.split("/", 1) if "/" in REPO else ("", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
TARGET_REF = os.environ.get("REPO_REF", "").strip() or None
UA = "oss-code-quality-audit/1.0 (+https://github.com)"

HDRS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": UA,
}
if GITHUB_TOKEN:
    HDRS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

OUTDIR = pathlib.Path("./data")
RAWDIR = OUTDIR / "raw"
OUTDIR.mkdir(parents=True, exist_ok=True)
RAWDIR.mkdir(parents=True, exist_ok=True)

RATING_MEETS = text("common", "ratings", "meets")
RATING_PARTIAL = text("common", "ratings", "partial")
RATING_NOT_MET = text("common", "ratings", "not_met")
ERROR_FETCH_NOTE = text("common", "errors", "fetching")


def save_raw(name: str, content: Any) -> str:
    p = RAWDIR / f"{name}.json"
    with p.open("w", encoding="utf-8") as f:
        if isinstance(content, (dict, list)):
            json.dump(content, f, ensure_ascii=False, indent=2)
        else:
            f.write(str(content))
    return str(p.resolve())


def save_bytes(name: str, data: bytes) -> str:
    p = RAWDIR / name
    with open(p, "wb") as f:
        f.write(data)
    return str(p.resolve())


def gh(url_path: str, query: dict[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    status, j, _ = _gh_get(url_path, params=query)
    return status, (j if isinstance(j, dict) else {})


def gh_paged(url_path: str, per_page: int = 100, max_pages: int = 10) -> list[dict[str, Any]]:
    items = _gh_paginate(url_path, per_page=per_page, max_pages=max_pages)
    return [it for it in items if isinstance(it, dict)]


def repo_contents(path: str = "") -> list[dict[str, Any]]:
    params = {"ref": TARGET_REF} if TARGET_REF else None
    s, j = gh(f"/repos/{OWNER}/{REPO_NAME}/contents/{path}", params)
    if s == 200:
        if isinstance(j, list):
            return j
        elif isinstance(j, dict):
            return [j]
    return []


def get_file_text(path: str) -> str | None:
    params = {"ref": TARGET_REF} if TARGET_REF else None
    s, j = gh(f"/repos/{OWNER}/{REPO_NAME}/contents/{path}", params)
    if s == 200 and isinstance(j, dict) and j.get("encoding") == "base64":
        try:
            return base64.b64decode(j["content"].encode("utf-8")).decode("utf-8", errors="ignore")
        except Exception:
            return None
    return None


def link(path: str) -> str:
    ref = TARGET_REF or "HEAD"
    return f"https://github.com/{OWNER}/{REPO_NAME}/blob/{ref}/{path}"


def has_workflow_keyword(text: str, *keywords: str) -> bool:
    t = text.lower()
    return any(k.lower() in t for k in keywords)


def collect_repo_meta() -> dict[str, Any]:
    status, info = gh(f"/repos/{OWNER}/{REPO_NAME}")
    save_raw("repo_meta", info)
    status_lang, langs = gh(f"/repos/{OWNER}/{REPO_NAME}/languages")
    save_raw("languages", langs)
    default_branch = info.get("default_branch", "development")
    return {
        "default_branch": default_branch,
        "license": (info.get("license") or {}).get("spdx_id"),
        "topics": info.get("topics", []),
        "archived": info.get("archived", False),
        "languages": langs,
        "size_kb": info.get("size"),
        "forks": info.get("forks_count"),
        "stars": info.get("stargazers_count"),
        "watchers": info.get("subscribers_count"),
        "open_issues": info.get("open_issues_count"),
        "pushed_at": info.get("pushed_at"),
        "updated_at": info.get("updated_at"),
        "html_url": info.get("html_url"),
        "requested_ref": TARGET_REF,
        "effective_ref": TARGET_REF or default_branch,
    }


def collect_presence_files() -> dict[str, Any]:
    from pipeline.repo_signals import TEST_ROOT_CANDIDATES

    candidates = [
        "CONTRIBUTING.md",
        "CONTRIBUTING.rst",
        "CONTRIBUTING.txt",
        "CODE_OF_CONDUCT.md",
        ".clang-format",
        ".clang-tidy",
        ".editorconfig",
        ".gitattributes",
        "README.md",
        "README.rst",
        "SECURITY.md",
        "LICENSE",
        "Makefile",
        *TEST_ROOT_CANDIDATES,
        "Testing.cmake",
        "CTestConfig.cmake",
        "programs/fuzz",
        "fuzz",
        "oss-fuzz",
        ".github/workflows",
        "scripts",
        "scripts/clang-format",
        "cmake/",
        "psa/",
        "library/",
        "include/",
    ]
    found = {}
    root = repo_contents("")
    names = {e.get("name"): e for e in root}
    for c in candidates:
        if "/" not in c and c in names:
            found[c] = names[c]["html_url"]
        else:
            s, j = gh(f"/repos/{OWNER}/{REPO_NAME}/contents/{c}")
            if s == 200:
                if isinstance(j, list):
                    found[c] = f"https://github.com/{OWNER}/{REPO_NAME}/tree/HEAD/{c.rstrip('/')}"
                elif isinstance(j, dict):
                    found[c] = j.get("html_url") or link(c)
    save_raw("presence_files", found)
    return found


def collect_readme_badges() -> dict[str, Any]:
    s, j = gh(f"/repos/{OWNER}/{REPO_NAME}/readme")
    result = {"coverage_mentions": [], "ci_mentions": [], "links": []}
    if s == 200 and isinstance(j, dict):
        if j.get("download_url"):
            st, _, data = http_get(j["download_url"], headers={"User-Agent": UA})
            text = data.decode("utf-8", errors="ignore") if data else ""
        elif j.get("content") and j.get("encoding") == "base64":
            text = base64.b64decode(j["content"].encode("utf-8")).decode("utf-8", errors="ignore")
        else:
            text = ""
        if text:
            for pat in [r"coverage", r"coveralls", r"codecov", r"gcov", r"lcov"]:
                if re.search(pat, text, re.I):
                    result["coverage_mentions"].append(pat)
            for pat in [r"github actions", r"build", r"ci", r"workflow"]:
                if re.search(pat, text, re.I):
                    result["ci_mentions"].append(pat)
            result["links"] = _extract_md_links(text)[:50]
    save_raw("readme_scan", result)
    return result


def collect_actions_and_checks() -> dict[str, Any]:
    workflows = gh_paged(f"/repos/{OWNER}/{REPO_NAME}/actions/workflows", per_page=100)
    save_raw("actions_workflows", workflows)
    out = {
        "workflows": [],
        "signals": {
            "lint": False,
            "sast": False,
            "tests": False,
            "coverage": False,
            "fuzz": False,
            "sanitizers": False,
            "strict": False,
        },
    }
    for wf in workflows:
        path = wf.get("path")
        if not path:
            continue
        yml = get_file_text(path)
        entry = {
            "name": wf.get("name"),
            "state": wf.get("state"),
            "path": path,
            "url": f"https://github.com/{OWNER}/{REPO_NAME}/blob/HEAD/{path}",
            "hints": [],
        }
        if yml:
            lowered = yml.lower()
            if has_workflow_keyword(
                lowered,
                "clang-tidy",
                "clang-format",
                "pylint",
                "flake8",
                "eslint",
                "golangci-lint",
                "cmakelint",
                "codespell",
            ):
                out["signals"]["lint"] = True
                entry["hints"].append("lint")
            if has_workflow_keyword(
                lowered, "codeql", "semgrep", "staticcheck", "cppcheck", "bandit", "trivy", "grype"
            ):
                out["signals"]["sast"] = True
                entry["hints"].append("sast")
            if has_workflow_keyword(
                lowered,
                "ctest",
                "cmake --build",
                "make test",
                "pytest",
                "ctest --output-on-failure",
                "ninja test",
                "cargo test",
                "go test",
                "meson test",
            ):
                out["signals"]["tests"] = True
                entry["hints"].append("tests")
            if has_workflow_keyword(lowered, "coverage", "codecov", "lcov", "gcov", "llvm-cov"):
                out["signals"]["coverage"] = True
                entry["hints"].append("coverage")
            if has_workflow_keyword(lowered, "oss-fuzz", "fuzz", "libfuzzer", "afl", "honggfuzz"):
                out["signals"]["fuzz"] = True
                entry["hints"].append("fuzz")
            if has_workflow_keyword(
                lowered,
                "asan",
                "ubsan",
                "msan",
                "tsan",
                "sanitize=address",
                "sanitize=undefined",
                "sanitize=thread",
                "sanitize=memory",
            ):
                out["signals"]["sanitizers"] = True
                entry["hints"].append("sanitizers")
            if (
                ("-werror" in lowered)
                or ("warnings-as-errors" in lowered)
                or ("treat warnings as errors" in lowered)
                or ("-d warnings" in lowered)
            ):
                out["signals"]["strict"] = True
                entry["hints"].append("strict")
        out["workflows"].append(entry)
    return out


def collect_code_scanning() -> dict[str, Any]:
    s, alerts = gh(f"/repos/{OWNER}/{REPO_NAME}/code-scanning/alerts")
    payload = {"status": s, "count": 0, "alerts_sample": []}
    if s == 200 and isinstance(alerts, list):
        payload["count"] = len(alerts)
        payload["alerts_sample"] = alerts[:10]
    save_raw("code_scanning_alerts", payload)
    return payload


def collect_scorecard() -> dict[str, Any]:
    from integrations.scorecard import build_scorecard_map, fetch_scorecard

    payload = fetch_scorecard(OWNER, REPO_NAME)
    payload["map"] = build_scorecard_map(payload)
    save_raw("openssf_scorecard", payload)
    return payload


def collect_oss_fuzz() -> dict[str, Any]:
    from pipeline.repo_signals import detect_oss_fuzz_project

    detected = detect_oss_fuzz_project(OWNER, REPO_NAME)
    out = {
        "overview_hit": bool(detected.get("overview_hit")),
        "oss_fuzz_dir": bool(detected.get("oss_fuzz_dir")),
        "project_report_url": detected.get("project_report_url"),
        "overview_row": detected.get("overview_row"),
        "present": bool(detected.get("present")),
        "notes": list(detected.get("notes") or []),
        "urls": list(detected.get("urls") or []),
    }
    save_raw("oss_fuzz_introspector", out)
    return out


def collect_search_for_fuzz_dirs() -> dict[str, Any]:
    suspects = ["programs/fuzz", "tests/fuzz", "fuzz", "scripts/fuzz", "test/fuzz", "fuzzers"]
    hits = {}
    for path in suspects:
        s, j = gh(f"/repos/{OWNER}/{REPO_NAME}/contents/{path}")
        if s == 200:
            hits[path] = f"https://github.com/{OWNER}/{REPO_NAME}/tree/HEAD/{path}"
    save_raw("fuzz_dirs", hits)
    return hits


def q3_1(evidence: dict[str, Any]) -> dict[str, Any]:
    """
    3-1: Style guide and lint enforcement.
    Collects style files (.clang-format/.clang-tidy/.editorconfig/CONTRIBUTING) and lint signals in CI,
    evaluates the combination of findings, and returns the question payload.
    """
    presence = evidence.get("presence_files", {})
    signals = (evidence.get("actions", {}) or {}).get("signals", {})
    dukaz = [
        presence.get("CONTRIBUTING.md")
        or presence.get("CONTRIBUTING.rst")
        or presence.get("CONTRIBUTING.txt"),
        presence.get(".clang-format"),
        presence.get(".clang-tidy"),
        presence.get(".editorconfig"),
    ]
    dukaz = [d for d in dukaz if d]
    has_style = any(
        presence.get(p)
        for p in [
            ".clang-format",
            ".clang-tidy",
            ".editorconfig",
            "CONTRIBUTING.md",
            "CONTRIBUTING.rst",
            "CONTRIBUTING.txt",
        ]
    )
    if has_style and signals.get("lint"):
        rate, note = (
            RATING_MEETS,
            text("script3", "q3_1", "note_full"),
        )
    elif has_style or signals.get("lint"):
        rate, note = (
            RATING_PARTIAL,
            text("script3", "q3_1", "note_partial"),
        )
    else:
        rate, note = RATING_NOT_MET, text("script3", "q3_1", "note_none")
    auto_msg = text(
        "script3",
        "q3_1",
        "auto",
        lint=boolean_text(bool(signals.get("lint"))),
        files=", ".join(
            [
                p.split("/")[-1]
                for p in [".clang-format", ".clang-tidy", ".editorconfig"]
                if presence.get(p)
            ]
        )
        or "-",
    )
    return {
        "id": "3-1",
        "dukaz": dukaz,
        "auto_nalez": auto_msg,
        "hodnoceni": rate,
        "poznamka": note,
    }


def q3_2(evidence: dict[str, Any]) -> dict[str, Any]:
    """
    3-2: SAST and tests in CI.
    Collects workflow links and inspects CI for tests/SAST/coverage signals.
    """
    from integrations.scorecard import score_meets

    presence = evidence.get("presence_files", {})
    _actions = evidence.get("actions", {})
    signals = _actions.get("signals", {})
    sc_map = (evidence.get("scorecard") or {}).get("map") or {}
    checks = sc_map.get("checks") or {}
    urls_map = sc_map.get("urls") or {}
    ci_score = checks.get("CI-Tests")
    dangerous = checks.get("Dangerous-Workflow")
    token_perms = checks.get("Token-Permissions")
    binary_artifacts = checks.get("Binary-Artifacts")
    secret_scanning = checks.get("Secret-Scanning")
    dukazy = [presence.get(".github/workflows")]
    if _actions.get("workflows"):
        dukazy += [w.get("url") for w in _actions["workflows"] if w.get("url")]
    if urls_map.get("CI-Tests"):
        dukazy.append(urls_map["CI-Tests"])
    for key in ("Dangerous-Workflow", "Token-Permissions", "Binary-Artifacts", "Secret-Scanning"):
        if urls_map.get(key):
            dukazy.append(urls_map[key])
    from pipeline.repo_signals import TEST_ROOT_CANDIDATES

    has_test_tree = any(presence.get(root) for root in TEST_ROOT_CANDIDATES)
    has_workflows = bool(_actions.get("workflows"))
    tests_detected = bool(
        signals.get("tests")
        or has_test_tree
        or (has_workflows and (signals.get("sanitizers") or signals.get("lint") or signals.get("fuzz")))
        or score_meets(ci_score, 5)
    )
    extra_bits = []
    if dangerous is not None:
        extra_bits.append(f"Dangerous-Workflow={dangerous}")
    if token_perms is not None:
        extra_bits.append(f"Token-Permissions={token_perms}")
    if binary_artifacts is not None:
        extra_bits.append(f"Binary-Artifacts={binary_artifacts}")
    if secret_scanning is not None:
        extra_bits.append(f"Secret-Scanning={secret_scanning}")
    extra = ("; " + "; ".join(extra_bits)) if extra_bits else ""

    risk_flags = []
    if dangerous is not None and dangerous < 5:
        risk_flags.append("Dangerous-Workflow")
    if token_perms is not None and token_perms < 5:
        risk_flags.append("Token-Permissions")
    if binary_artifacts is not None and binary_artifacts < 5:
        risk_flags.append("Binary-Artifacts")

    if tests_detected and (signals.get("sast") or signals.get("coverage") or score_meets(ci_score, 7)):
        rate, note = RATING_MEETS, text("script3", "q3_2", "note_full")
    elif tests_detected or signals.get("sast") or signals.get("coverage"):
        rate, note = (
            RATING_PARTIAL,
            text("script3", "q3_2", "note_partial"),
        )
    else:
        rate, note = RATING_NOT_MET, text("script3", "q3_2", "note_none")
    if risk_flags and rate == RATING_MEETS:
        rate = RATING_PARTIAL
        note = f"{note} Scorecard rizikové signály: {', '.join(risk_flags)} (CONFIRM)."
    elif extra:
        note = f"{note}{extra}."
    return {
        "id": "3-2",
        "dukaz": [d for d in dukazy if d],
        "auto_nalez": text(
            "script3",
            "q3_2",
            "auto",
            sast=boolean_text(bool(signals.get("sast"))),
            tests=boolean_text(bool(tests_detected)),
            coverage=boolean_text(bool(signals.get("coverage"))),
        ),
        "hodnoceni": rate,
        "poznamka": note,
    }


def q3_3(evidence: dict[str, Any]) -> dict[str, Any]:
    """
    3-3: Static analysis severe warnings (proxy via Code Scanning API).
    Rates based on API availability and alert counts, linking back to the Code Scanning UI.
    """
    code_scanning = evidence.get("code_scanning", {})
    cs_status = int(code_scanning.get("status") or 0)
    cs_count = int(code_scanning.get("count") or 0)
    if cs_status == 200 and cs_count == 0:
        rate, note = RATING_MEETS, text("script3", "q3_3", "note_no_alerts")
    elif cs_status in (401, 403, 404, 0):
        rate, note = (
            RATING_PARTIAL,
            text("script3", "q3_3", "note_limited"),
        )
    else:
        rate, note = (
            RATING_PARTIAL,
            text("script3", "q3_3", "note_alerts"),
        )
    return {
        "id": "3-3",
        "dukaz": [f"https://github.com/{OWNER}/{REPO_NAME}/security/code-scanning"]
        + (
            [f"https://github.com/{OWNER}/{REPO_NAME}/security/code-scanning?query=is%3Aopen"]
            if code_scanning.get("status") == 200
            else []
        ),
        "auto_nalez": text(
            "script3",
            "q3_3",
            "auto",
            status=code_scanning.get("status"),
            count=code_scanning.get("count"),
        ),
        "hodnoceni": rate,
        "poznamka": note,
    }


def q3_4(evidence: dict[str, Any]) -> dict[str, Any]:
    """
    3-4: Memory-safe languages - heuristic derived from repository language stats.
    """
    langs = list((evidence.get("repo_meta", {}).get("languages") or {}).keys())
    memsafe_langs = {"python", "java", "javascript", "typescript", "rust", "c#", "kotlin", "go"}
    memsafe_any = any(lang.lower() in memsafe_langs for lang in langs)
    uses_c_cpp = any(lang.lower() in {"c", "c++"} for lang in langs)
    if memsafe_any and not uses_c_cpp:
        rate, note = RATING_MEETS, text("script3", "q3_4", "note_safe")
    elif memsafe_any and uses_c_cpp:
        rate, note = (
            RATING_PARTIAL,
            text("script3", "q3_4", "note_mixed"),
        )
    else:
        rate, note = RATING_NOT_MET, text("script3", "q3_4", "note_risky")
    return {
        "id": "3-4",
        "dukaz": [f"https://github.com/{OWNER}/{REPO_NAME}"],
        "auto_nalez": text(
            "script3",
            "q3_4",
            "auto",
            languages=", ".join(langs) or "-",
            memory_safe=boolean_text(bool(memsafe_any)),
        ),
        "hodnoceni": rate,
        "poznamka": note,
    }


def q3_5(evidence: dict[str, Any]) -> dict[str, Any]:
    """
    3-5: Strict build flags / warnings-as-errors.
    Scans workflows and build scripts for strictness hints and records supporting links.
    """
    presence = evidence.get("presence_files", {})
    _actions = evidence.get("actions", {})
    signals = _actions.get("signals", {})
    hints = []
    for w in _actions.get("workflows", []):
        if any(k in (w.get("hints") or []) for k in ["lint", "tests"]):
            hints.append(w.get("url"))
    for path in ["scripts", "cmake/", "Makefile", "library/"]:
        if presence.get(path):
            hints.append(presence[path])
    strict_ci = bool(_actions.get("signals", {}).get("strict"))
    if strict_ci:
        rate, note = RATING_MEETS, text("script3", "q3_5", "note_full")
    elif signals.get("lint") or signals.get("tests"):
        rate, note = (
            RATING_PARTIAL,
            text("script3", "q3_5", "note_partial"),
        )
    else:
        rate, note = RATING_NOT_MET, text("script3", "q3_5", "note_none")
    return {
        "id": "3-5",
        "dukaz": list(dict.fromkeys(hints)),
        "auto_nalez": text("script3", "q3_5", "auto"),
        "hodnoceni": rate,
        "poznamka": note,
    }


def q3_6(evidence: dict[str, Any]) -> dict[str, Any]:
    """
    3-6: Fuzz testing evidence from OSS-Fuzz, in-repo directories, and optional CI signals.
    """
    from integrations.scorecard import score_meets

    signals = (evidence.get("actions", {}) or {}).get("signals", {})
    fuzz_dirs = evidence.get("fuzz_dirs", {})
    ossf = evidence.get("oss_fuzz", {})
    sc_map = (evidence.get("scorecard") or {}).get("map") or {}
    fuzz_score = (sc_map.get("checks") or {}).get("Fuzzing")
    dukazy = list(fuzz_dirs.values())
    if ossf.get("project_report_url"):
        dukazy.append(ossf["project_report_url"])
    if sc_map.get("urls", {}).get("Fuzzing"):
        dukazy.append(sc_map["urls"]["Fuzzing"])
    dukazy.append("https://google.github.io/oss-fuzz/")
    has_fuzz = bool(
        ossf.get("present")
        or ossf.get("project_report_url")
        or ossf.get("overview_hit")
        or ossf.get("oss_fuzz_dir")
        or fuzz_dirs
        or score_meets(fuzz_score, 5)
    )
    if has_fuzz:
        rate, note = RATING_MEETS, text("script3", "q3_6", "note_full")
    elif signals.get("fuzz") or signals.get("sanitizers"):
        rate, note = RATING_PARTIAL, text("script3", "q3_6", "note_partial")
    else:
        rate, note = RATING_NOT_MET, text("script3", "q3_6", "note_none")
    return {
        "id": "3-6",
        "dukaz": dukazy,
        "auto_nalez": text(
            "script3",
            "q3_6",
            "auto",
            has_oss_fuzz=boolean_text(
                bool(
                    ossf.get("present")
                    or ossf.get("project_report_url")
                    or ossf.get("overview_hit")
                    or ossf.get("oss_fuzz_dir")
                )
            ),
            fuzz_dirs=", ".join(fuzz_dirs.keys()) or "-",
        ),
        "hodnoceni": rate,
        "poznamka": note,
    }


def q3_7(evidence: dict[str, Any]) -> dict[str, Any]:
    """
    3-7: Readability/complexity - indirect indicators from modular structure and style files.
    """
    presence = evidence.get("presence_files", {})
    _actions = evidence.get("actions", {})
    has_style = any(
        presence.get(p)
        for p in [
            ".clang-format",
            ".clang-tidy",
            ".editorconfig",
            "CONTRIBUTING.md",
            "CONTRIBUTING.rst",
            "CONTRIBUTING.txt",
        ]
    )
    dukaz = [
        presence.get("CONTRIBUTING.md")
        or presence.get("CONTRIBUTING.rst")
        or presence.get("CONTRIBUTING.txt"),
        presence.get(".clang-format"),
        presence.get(".clang-tidy"),
        presence.get("cmake/"),
        presence.get("library/"),
    ]
    dukaz = [d for d in dukaz if d]
    modular_signals = sum(1 for p in ["cmake/", "library/", "include/"] if presence.get(p))
    if has_style and modular_signals >= 2:
        rate, note = (
            RATING_MEETS,
            text("script3", "q3_7", "note_full"),
        )
    elif has_style or modular_signals >= 1:
        rate, note = (
            RATING_PARTIAL,
            text("script3", "q3_7", "note_partial"),
        )
    else:
        rate, note = RATING_NOT_MET, text("script3", "q3_7", "note_none")
    return {
        "id": "3-7",
        "dukaz": dukaz,
        "auto_nalez": text("script3", "q3_7", "auto"),
        "hodnoceni": rate,
        "poznamka": note,
    }


def assess_section_3(evidence: dict[str, Any]) -> dict[str, Any]:
    """
    Section 3 orchestrator that invokes the per-question evaluators q3_1 .. q3_7.
    Keeps data collection and heuristics per question in one place with clear inputs and outputs.
    If an evaluator fails, the question falls back to a conservative 'not met' result instead of raising.
    """

    def safe(callable_fn, qid: str) -> dict[str, Any]:
        try:
            return callable_fn(evidence)
        except Exception:
            return {
                "id": qid,
                "dukaz": [],
                "auto_nalez": "",
                "hodnoceni": RATING_NOT_MET,
                "poznamka": ERROR_FETCH_NOTE,
            }

    q = [
        safe(q3_1, "3-1"),
        safe(q3_2, "3-2"),
        safe(q3_3, "3-3"),
        safe(q3_4, "3-4"),
        safe(q3_5, "3-5"),
        safe(q3_6, "3-6"),
        safe(q3_7, "3-7"),
    ]
    return {"sekce_id": 3, "nazev": text("script3", "section", "title"), "otazky": q}


def _merge_section3_into_form(input_path: str, output_path: str, section3: dict[str, Any]) -> None:
    with open(input_path, encoding="utf-8") as f:
        form = json.load(f)

    auto_index = {q.get("id"): q for q in section3.get("otazky", [])}

    target_idx = None
    for i, s in enumerate(form.get("sections", [])):
        if str(s.get("id")) == "3":
            target_idx = i
            break

    if target_idx is None:
        form.setdefault("sections", []).append(
            {
                "id": 3,
                "title": text("script3", "section", "title"),
                "questions": [],
            }
        )
        target_idx = len(form["sections"]) - 1

    existing_qs = form["sections"][target_idx].setdefault("questions", [])
    section_meta = form["sections"][target_idx].setdefault("meta", {})
    if isinstance(section_meta, dict):
        section_meta["requested_ref"] = TARGET_REF
        section_meta["effective_ref"] = TARGET_REF or section_meta.get("default_branch")
    ex_index = {q.get("id"): q for q in existing_qs}
    for qid, auto in auto_index.items():
        dq = ex_index.get(qid)
        if dq is None:
            dq = {
                "id": qid,
                "text": "",
                "rating": None,
                "note": "",
                "category": text("script3", "section", "category"),
                "description": "",
                "evidence": "",
            }
            existing_qs.append(dq)
        proof_list = auto.get("dukaz") or []
        if isinstance(proof_list, list):
            proof_str = "\n".join([p for p in proof_list if p])
        else:
            proof_str = str(proof_list)
        dq["evidence"] = proof_str
        auto_note = auto.get("auto_nalez") or auto.get("poznamka")
        if auto_note:
            if dq.get("note"):
                dq["note"] = "\n".join(
                    [
                        dq["note"],
                        text("script3", "section", "auto_prefix", message=auto_note),
                    ]
                )
            else:
                dq["note"] = str(auto_note)
        if not dq.get("rating") and auto.get("hodnoceni"):
            dq["rating"] = auto.get("hodnoceni")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(form, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=text("script3", "cli", "description"))
    parser.add_argument("--repo", help=text("script3", "cli", "help_repo"))
    parser.add_argument("--out", help=text("script3", "cli", "help_out"))
    parser.add_argument("--input", help=text("script3", "cli", "help_input"))
    parser.add_argument("--output", help=text("script3", "cli", "help_output"))
    args = parser.parse_args()

    global REPO, OWNER, REPO_NAME
    if args.repo:
        REPO = args.repo.strip()
        if "/" not in REPO:
            print(text("script3", "cli", "error_repo_format"), file=sys.stderr)
            sys.exit(2)
        OWNER, REPO_NAME = REPO.split("/", 1)
    elif not (OWNER and REPO_NAME):
        print(text("script3", "cli", "error_repo_required"), file=sys.stderr)
        sys.exit(2)

    print(f"[START] [3.py] Zahajuji vyhodnocení sekce 3 pro {OWNER}/{REPO_NAME}", flush=True)
    print(text("script3", "cli", "audit_repo", owner=OWNER, repo=REPO_NAME))
    print(
        "[INFO] [3.py] Sbírám metadata repozitáře, workflow, code scanning a scorecard signály.",
        flush=True,
    )
    evidence: dict[str, Any] = {}
    evidence["repo_meta"] = collect_repo_meta()
    evidence["presence_files"] = collect_presence_files()
    evidence["readme"] = collect_readme_badges()
    evidence["actions"] = collect_actions_and_checks()
    evidence["code_scanning"] = collect_code_scanning()
    evidence["scorecard"] = collect_scorecard()
    evidence["oss_fuzz"] = collect_oss_fuzz()
    evidence["fuzz_dirs"] = collect_search_for_fuzz_dirs()
    print("[INFO] [3.py] Přepočítávám otázky sekce 3 na základě sesbíraných důkazů.", flush=True)

    section3 = assess_section_3(evidence)

    if args.input and args.output:
        _merge_section3_into_form(args.input, args.output, section3)
        print(text("script3", "cli", "merged", path=pathlib.Path(args.output).resolve()))
        print(text("script3", "cli", "raw_written"))
        print(
            f"[DONE] [3.py] Sekce 3 byla zapsána do {pathlib.Path(args.output).resolve()}",
            flush=True,
        )
    else:
        result = {
            "formular_verze": "2.0",
            "repo": f"{OWNER}/{REPO_NAME}",
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sekce": [section3],
            "zdroje": {
                "github_repo": evidence["repo_meta"].get("html_url"),
                "github_api": "https://api.github.com",
                "openssf_scorecard_api": "https://api.securityscorecards.dev/",
                "oss_fuzz_introspector": "https://oss-fuzz-introspector.storage.googleapis.com/",
                "project_docs_fuzzing": "https://google.github.io/oss-fuzz/",
            },
            "raw_evidence_refs": {
                k: f"./data/raw/{k}.json"
                for k in [
                    "repo_meta",
                    "languages",
                    "presence_files",
                    "readme_scan",
                    "actions_workflows",
                    "code_scanning_alerts",
                    "openssf_scorecard",
                    "oss_fuzz_introspector",
                    "fuzz_dirs",
                ]
                if (RAWDIR / f"{k}.json").exists()
            },
        }

        if args.out:
            out_path = pathlib.Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            out_path = OUTDIR / f"{REPO_NAME}_code_quality_evidence.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(text("script3", "cli", "wrote", path=out_path.resolve()))
        print(text("script3", "cli", "api_note"))
        print(text("script3", "cli", "token_note"))
        print(f"[DONE] [3.py] Výstup sekce 3 byl uložen do {out_path.resolve()}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(text("script3", "cli", "interrupted"), file=sys.stderr)
        sys.exit(130)
