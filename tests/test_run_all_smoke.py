from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module {module_name} from {file_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


run_all = _load_module("run_all_mod", ROOT / "run_all.py")


def _update_section(form: dict, sec_id: str, updater):
    for s in form.get("sections", []):
        if str(s.get("id")) == sec_id:
            updater(s)
            return


def _write_dummy_section1(form: dict):
    def upd(sec):
        for q in sec.get("questions", []):
            if str(q.get("id")).startswith("1-"):
                q["evidence"] = f"https://example.test/{q.get('id')}"
                q["rating"] = "splňuje"

    _update_section(form, "1", upd)


def _write_dummy_section2(form: dict):
    def upd(sec):
        for q in sec.get("questions", []):
            q["rating"] = "splňuje"
            q["note"] = "dummy"
            q["evidence"] = f"https://example.test/{q.get('id')}"

    _update_section(form, "2", upd)


def _write_dummy_section3(form: dict):
    def upd(sec):
        for q in sec.get("questions", []):
            q["evidence"] = f"https://example.test/{q.get('id')}"
            q["rating"] = "splňuje"
            if not q.get("note"):
                q["note"] = "auto: dummy"

    _update_section(form, "3", upd)


def _write_dummy_section4(form: dict):
    def upd(sec):
        for q in sec.get("questions", []):
            q["rating"] = "splňuje"
            q["note"] = "dummy"
            q["evidence"] = f"https://example.test/{q.get('id')}"

    _update_section(form, "4", upd)


def _write_dummy_section5(form: dict):
    def upd(sec):

        ids = {q.get("id") for q in sec.get("questions", [])}
        for i in range(1, 17):
            qid = f"5-{i}"
            if qid not in ids:
                sec.setdefault("questions", []).append(
                    {
                        "id": qid,
                        "text": "",
                        "rating": None,
                        "note": "",
                        "category": "good to have",
                        "description": "",
                        "evidence": "",
                    }
                )
        for q in sec.get("questions", []):
            q["rating"] = "splňuje"
            q["note"] = "dummy"
            q["evidence"] = f"https://example.test/{q.get('id')}"

    _update_section(form, "5-sec:api", upd)


def _apply_dummy_for_script(script: str, data: dict) -> None:
    aliases = {
        "1.py": "1",
        "2.py": "2",
        "3.py": "3",
        "4.py": "4",
        "5.py": "5",
        "section_01_prerequisites.py": "1",
        "section_02_oss_quality.py": "2",
        "section_03_code_quality.py": "3",
        "section_04_documentation.py": "4",
        "section_05_security_api.py": "5",
    }
    step = aliases.get(script)
    if step == "1":
        _write_dummy_section1(data)
    elif step == "2":
        _write_dummy_section2(data)
    elif step == "3":
        _write_dummy_section3(data)
    elif step == "4":
        _write_dummy_section4(data)
    elif step == "5":
        _write_dummy_section5(data)
    else:
        raise AssertionError(f"Unexpected script call: {script}")


def test_run_all_smoke(monkeypatch, tmp_path):

    monkeypatch.setattr(run_all, "OUT", tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(run_all, "RUNS", runs)

    def fake_run(cmd, env=None):

        args = list(cmd)

        def arg_after(flag):
            if flag in args:
                i = args.index(flag)
                return args[i + 1]
            return None

        wf = (
            arg_after("--out") or arg_after("--output") or arg_after("--in") or arg_after("--input")
        )
        assert wf, f"Working form path not found in args: {args}"
        wfp = Path(wf)
        data = json.loads(wfp.read_text(encoding="utf-8"))

        script = Path(args[1]).name if len(args) > 1 else ""
        _apply_dummy_for_script(script, data)
        wfp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    monkeypatch.setattr(run_all, "run", fake_run)

    owner_repo = "Example/Repo"
    _ = run_all.main.__wrapped__() if hasattr(run_all.main, "__wrapped__") else None

    import sys

    old_argv = sys.argv
    try:
        sys.argv = [str(ROOT / "run_all.py"), owner_repo]
        code = run_all.main()
    finally:
        sys.argv = old_argv

    assert code == 0

    run_dirs = [p for p in runs.iterdir() if p.is_dir()]
    assert len(run_dirs) == 1
    agg = run_dirs[0] / "form.json"
    assert agg.exists()
    result = json.loads(agg.read_text(encoding="utf-8"))
    assert result.get("meta", {}).get("evaluation_id") == run_dirs[0].name
    assert result.get("meta", {}).get("collection_status") == "done"
    aliases = list(tmp_path.glob("form_Example_Repo_*.json"))
    assert aliases
    assert "nehodnoceno" in result.get("rating_options", [])

    sec_ids = {str(s.get("id")) for s in result.get("sections", [])}
    assert "0-supply" not in sec_ids
    assert "1" in sec_ids
    assert "2" in sec_ids
    assert "3" in sec_ids
    assert "4" in sec_ids
    assert "5-sec:api" in sec_ids

    sec5 = next(s for s in result["sections"] if str(s.get("id")) == "5-sec:api")
    ids_5 = {q.get("id") for q in sec5.get("questions", [])}
    assert all(f"5-{i}" in ids_5 for i in range(1, 17))
    for section in result.get("sections", []):
        for q in section.get("questions", []):
            assert q.get("review_state") in ("AUTO", "CONFIRM", "MANUAL")
            assert isinstance(q.get("checked"), bool)
            assert isinstance(q.get("requires_confirmation"), bool)
            assert q.get("checked_source", "") in ("", "auto", "manual")

    summary = result.get("summary")
    assert summary is not None
    assert "gate" not in summary
    assert isinstance(summary.get("cutoffs", {}).get("passed"), bool)
    for sid in ["1", "2", "3", "4", "5-sec:api"]:
        assert sid in summary.get("section_scores", {})

    files = []
    for p in sorted(tmp_path.rglob("*")):
        if p.is_file():
            try:
                rel = p.relative_to(tmp_path)
            except Exception:
                rel = p
            files.append(str(rel))
    print("\n[artifacts] test_run_all_smoke generated:")
    for f in files:
        print(f" - {f}")


def test_parse_owner_repo_tree_ref():
    owner, repo, ref = run_all.parse_owner_repo(
        "https://github.com/openssl/openssl/tree/openssl-3.5.1"
    )
    assert owner == "openssl"
    assert repo == "openssl"
    assert ref == "openssl-3.5.1"


def test_parse_owner_repo_without_ref():
    owner, repo, ref = run_all.parse_owner_repo("openssl/openssl")
    assert owner == "openssl"
    assert repo == "openssl"
    assert ref is None


def test_run_all_tree_ref_passes_ref_to_pipeline(monkeypatch, tmp_path):
    monkeypatch.setattr(run_all, "OUT", tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(run_all, "RUNS", runs)
    expected_ref = "openssl-3.5.1"
    seen_script5_ref = None
    seen_env_ref = None

    def fake_run(cmd, env=None):
        nonlocal seen_script5_ref, seen_env_ref
        args = list(cmd)

        def arg_after(flag):
            if flag in args:
                i = args.index(flag)
                return args[i + 1]
            return None

        wf = (
            arg_after("--out") or arg_after("--output") or arg_after("--in") or arg_after("--input")
        )
        assert wf, f"Working form path not found in args: {args}"
        wfp = Path(wf)
        data = json.loads(wfp.read_text(encoding="utf-8"))
        script = Path(args[1]).name if len(args) > 1 else ""

        _apply_dummy_for_script(script, data)
        if script in {"5.py", "section_05_security_api.py"}:
            seen_script5_ref = arg_after("--ref")

        if env is not None:
            seen_env_ref = env.get("REPO_REF")

        wfp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    monkeypatch.setattr(run_all, "run", fake_run)

    import sys

    old_argv = sys.argv
    try:
        sys.argv = [
            str(ROOT / "run_all.py"),
            f"https://github.com/Example/Repo/tree/{expected_ref}",
        ]
        code = run_all.main()
    finally:
        sys.argv = old_argv

    assert code == 0
    assert seen_script5_ref == expected_ref
    assert seen_env_ref == expected_ref

    agg = next((runs / p.name / "form.json" for p in runs.iterdir() if p.is_dir()), None)
    assert agg and agg.exists()
    result = json.loads(agg.read_text(encoding="utf-8"))
    assert result.get("meta", {}).get("requested_ref") == expected_ref
    assert result.get("meta", {}).get("effective_ref") == expected_ref
    assert result.get("meta", {}).get("evaluated_repo_version") == expected_ref
