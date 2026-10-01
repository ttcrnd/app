from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

from _web_js import read_web_js


def test_step5_auth_gate_markers():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = read_web_js(WEB)
    css = (WEB / "styles.css").read_text(encoding="utf-8")

    assert 'id="authGate"' in html
    assert "Vstoupit" in html
    assert "Prohlížet katalog bez kódu" in html
    assert 'id="tokenRow"' in html
    assert "hidden" in html.split('id="tokenRow"', 1)[1].split(">", 1)[0]

    assert "openAuthGate" in js
    assert "refreshAuthStatus" in js
    assert "token_required" in js
    assert "revealTokenRow" in js
    assert "browseExamplesWithoutCode" in js
    assert "/api/auth/enter" in js

    assert ".auth-gate" in css


def test_step5_pilot_auth_flow(tmp_path, monkeypatch):
    import db.repository as repository
    import server
    from db.session import init_db, reset_engine
    from utils import pilotauth

    db_url = f"sqlite:///{tmp_path / 'review.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setattr(repository, "ARTIFACTS_DIR", tmp_path / "artifacts")
    monkeypatch.setattr("db.repos.common.ARTIFACTS_DIR", tmp_path / "artifacts")
    reset_engine()
    init_db(url=db_url)

    monkeypatch.setenv("PILOT_ACCESS_CODE", "pilot-secret")
    monkeypatch.setenv("PILOT_CODE_ENABLED", "true")
    monkeypatch.setenv("PILOT_SESSION_SECRET", "test-secret")
    monkeypatch.setattr(server, "_configured_token", lambda: None)
    monkeypatch.setattr("review_app.deps.configured_token", lambda: None)

    client = TestClient(server.app)

    status = client.get("/api/auth/status")
    assert status.status_code == 200
    body = status.json()
    assert body["enabled"] is True
    assert body["authenticated"] is False
    assert "reviewer" in body["roles"]

    # Examples stay public
    examples = client.get("/api/examples")
    assert examples.status_code == 200

    # Writes blocked
    blocked = client.post("/api/run", json={"repo": "openssl/openssl"})
    assert blocked.status_code == 401
    assert blocked.json()["detail"]["code"] == "auth_required"

    bad = client.post("/api/auth/enter", json={"code": "wrong"})
    assert bad.status_code == 401

    ok = client.post("/api/auth/enter", json={"code": "pilot-secret"})
    assert ok.status_code == 200
    assert ok.json()["authenticated"] is True

    # Still no GitHub token → structured token_required (not auth)
    run = client.post("/api/run", json={"repo": "openssl/openssl"})
    assert run.status_code == 400
    assert run.json()["detail"]["code"] == "token_required"

    saved = client.post(
        "/api/evaluations",
        json={"form": {"meta": {"repo": "openssl/openssl"}, "sections": []}},
    )
    assert saved.status_code == 200

    roles_path = ROOT / "schema" / "roles.json"
    assert roles_path.exists()
    assert "viewer" in roles_path.read_text(encoding="utf-8")

    # open mode when code disabled
    monkeypatch.setenv("PILOT_CODE_ENABLED", "false")
    assert pilotauth.pilot_code_enabled(server.ROOT) is False
