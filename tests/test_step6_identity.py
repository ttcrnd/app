from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

from _web_js import read_web_js


def test_step6_identity_banner_and_isolated_runs_markers():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = read_web_js(WEB)
    css = (WEB / "styles.css").read_text(encoding="utf-8")
    run_all = (ROOT / "run_all.py").read_text(encoding="utf-8")

    assert 'id="collectionBanner"' in html
    assert "Technické údaje" in html
    assert 'id="techDetailsPanel"' in html

    assert "buildPendingEvaluation" in js
    assert "Sbírám podklady…" in js
    assert "resolveFormIdentity" in js
    assert "collection_status" in js
    assert "humanStatus" in js
    assert "openDrawer: false" in js or "openDrawer = false" in js

    assert ".collection-banner" in css
    assert ".tech-details" in css

    assert "data/runs" in run_all or "RUNS" in run_all
    assert "--run-id" in run_all
    assert "evaluation_id" in run_all
    assert "collection_status" in run_all


def test_step6_two_runs_do_not_overwrite(tmp_path, monkeypatch):
    import json
    import sys

    import run_all

    monkeypatch.setattr(run_all, "OUT", tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(run_all, "RUNS", runs)

    def fake_run(cmd, env=None):
        args = list(cmd)

        def arg_after(flag):
            if flag in args:
                return args[args.index(flag) + 1]
            return None

        wf = arg_after("--out") or arg_after("--output") or arg_after("--input")
        assert wf
        path = Path(wf)
        data = json.loads(path.read_text(encoding="utf-8"))
        # leave skeleton mostly intact
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    monkeypatch.setattr(run_all, "run", fake_run)

    old = sys.argv
    try:
        sys.argv = [str(ROOT / "run_all.py"), "Example/Repo", "--run-id", "run_aaa"]
        assert run_all.main() == 0
        sys.argv = [str(ROOT / "run_all.py"), "Example/Repo", "--run-id", "run_bbb"]
        assert run_all.main() == 0
    finally:
        sys.argv = old

    assert (runs / "run_aaa" / "form.json").exists()
    assert (runs / "run_bbb" / "form.json").exists()
    a = json.loads((runs / "run_aaa" / "form.json").read_text(encoding="utf-8"))
    b = json.loads((runs / "run_bbb" / "form.json").read_text(encoding="utf-8"))
    assert a["meta"]["evaluation_id"] == "run_aaa"
    assert b["meta"]["evaluation_id"] == "run_bbb"
    aliases = list(tmp_path.glob("form_Example_Repo_*.json"))
    assert len(aliases) == 2
