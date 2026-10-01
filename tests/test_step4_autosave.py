from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

from _web_js import read_web_js


def test_step4_autosave_markers_in_ui():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = read_web_js(WEB)
    css = (WEB / "styles.css").read_text(encoding="utf-8")

    assert 'id="saveStatus"' in html
    assert "Uložit teď" in html
    assert "Obnovit zálohu prohlížeče" in html
    assert "pojmenuj koncept" not in html.lower()

    assert "scheduleAutosave" in js
    assert "saveToServerNow" in js
    assert "restoreLastOpenEvaluation" in js
    assert "buildEvaluationTitle" in js
    assert "Uloženo" in js
    assert "Ukládám…" in js
    assert "beforeunload" in js

    assert ".save-status" in css


def test_step4_evaluations_api_shape(tmp_path, monkeypatch):
    import db.repository as repository
    import server
    from db.session import init_db, reset_engine

    db_url = f"sqlite:///{tmp_path / 'review.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setattr(repository, "ARTIFACTS_DIR", tmp_path / "artifacts")
    monkeypatch.setattr("db.repos.common.ARTIFACTS_DIR", tmp_path / "artifacts")
    reset_engine()
    init_db(url=db_url)

    client = TestClient(server.app)
    payload = {
        "form": {
            "meta": {"repo": "openssl/openssl", "effective_ref": "openssl-3.3.0"},
            "sections": [],
        }
    }
    saved = client.post("/api/evaluations", json=payload)
    assert saved.status_code == 200
    body = saved.json()
    assert body["id"]
    assert "openssl/openssl @ openssl-3.3.0" in body["title"]
    assert body["library"] == "openssl/openssl"
    assert "updated_at" in body

    listed = client.get("/api/evaluations")
    assert listed.status_code == 200
    items = listed.json()["evaluations"]
    assert items
    assert items[0]["title"]
    assert items[0]["id"] == body["id"]

    # Alias still works
    listed_drafts = client.get("/api/drafts")
    assert listed_drafts.status_code == 200
    assert listed_drafts.json()["drafts"][0]["id"] == body["id"]

    loaded = client.get(f"/api/evaluations/{body['id']}")
    assert loaded.status_code == 200
    form = loaded.json()["form"]
    assert form["_evaluation_id"] == body["id"]
    assert form["_evaluation_title"]

    artifact = tmp_path / "artifacts" / body["id"] / "form.json"
    assert artifact.exists()
    on_disk = json.loads(artifact.read_text(encoding="utf-8"))
    assert on_disk["meta"]["title"]
