from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
REVIEW_ROOT = ROOT.parent


def _client_seeded(tmp_path, monkeypatch, *, access_code: str | None = "demo-secret"):
    import db.repository as repository
    import server
    from db.repository import seed_pilot_evaluations, seed_pilot_libraries
    from db.session import get_session_factory, init_db, reset_engine
    from utils import pilotauth

    db_path = tmp_path / "review.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(repository, "ARTIFACTS_DIR", tmp_path / "artifacts")
    monkeypatch.setattr("db.repos.common.ARTIFACTS_DIR", tmp_path / "artifacts")
    if access_code:
        monkeypatch.setenv("PILOT_ACCESS_CODE", access_code)
        monkeypatch.setenv("PILOT_CODE_ENABLED", "true")
        monkeypatch.setenv("PILOT_SESSION_SECRET", "test-secret-step10")
    else:
        monkeypatch.delenv("PILOT_ACCESS_CODE", raising=False)
        monkeypatch.setenv("PILOT_CODE_ENABLED", "false")
    monkeypatch.setattr(pilotauth, "pilot_code_enabled", lambda _root=None: bool(access_code))

    reset_engine()
    init_db(url=url)
    session = get_session_factory()()
    try:
        seed_pilot_libraries(session)
        seed_pilot_evaluations(session, examples_dir=ROOT / "assets" / "example")
        session.commit()
    finally:
        session.close()
    return TestClient(server.app)


def test_step10_deploy_and_demo_docs():
    assert (ROOT / "docs" / "DEPLOY.md").exists()
    assert (ROOT / "docker-compose.prod.yml").exists()
    assert (ROOT / "Caddyfile").exists()
    assert (ROOT / "scripts" / "backup_sqlite.sh").exists()
    assert (REVIEW_ROOT / "demo-skript.md").exists()
    deploy = (ROOT / "docs" / "DEPLOY.md").read_text(encoding="utf-8")
    assert "PILOT_ACCESS_CODE" in deploy
    assert "backup_sqlite" in deploy
    assert "HTTPS" in deploy or "https" in deploy.lower()
    demo = (REVIEW_ROOT / "demo-skript.md").read_text(encoding="utf-8")
    assert "K vyřízení" in demo
    assert "PDF koncept" in demo
    assert "8" in demo
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "Prohlížet katalog bez kódu" in html


def test_step10_public_catalog_completed_only(tmp_path, monkeypatch):
    client = _client_seeded(tmp_path, monkeypatch, access_code="demo-secret")

    # No cookie → public catalog (Hotovo / Nedoporučeno only)
    public = client.get("/api/libraries")
    assert public.status_code == 200
    body = public.json()
    assert body["public_catalog"] is True
    assert body["viewer_mode"] is True
    assert body["libraries"]
    assert all(
        item["catalog_status"] in {"completed", "not_recommended"} for item in body["libraries"]
    )

    openssl = next(item for item in body["libraries"] if item["repo"] == "openssl/openssl")
    detail = client.get(f"/api/libraries/{openssl['id']}")
    assert detail.status_code == 200
    assert detail.json()["evaluations"]
    assert all(
        e["status"] in {"completed", "not_recommended"} for e in detail.json()["evaluations"]
    )

    eval_id = openssl["latest_evaluation"]["id"]
    opened = client.get(f"/api/evaluations/{eval_id}")
    assert opened.status_code == 200
    assert opened.json()["status"] == "completed"

    # In-progress eval must require auth when code enabled
    saved = client.post(
        "/api/evaluations",
        json={
            "form": {
                "meta": {"repo": "openssl/openssl", "effective_ref": "openssl-3.3.0"},
                "sections": [{"id": "1", "questions": []}],
            }
        },
    )
    assert saved.status_code == 401

    entered = client.post("/api/auth/enter", json={"code": "demo-secret"})
    assert entered.status_code == 200
    saved = client.post(
        "/api/evaluations",
        json={
            "form": {
                "meta": {"repo": "openssl/openssl", "effective_ref": "openssl-3.3.0"},
                "sections": [{"id": "1", "questions": []}],
            }
        },
    )
    assert saved.status_code == 200
    draft_id = saved.json()["id"]

    client.cookies.clear()
    blocked = client.get(f"/api/evaluations/{draft_id}")
    assert blocked.status_code == 401


def test_step10_path_auth_helpers():
    from auth.pilot import path_requires_auth

    assert path_requires_auth("GET", "/api/libraries") is False
    assert path_requires_auth("GET", "/api/libraries/abc") is False
    assert path_requires_auth("GET", "/api/pilot/status") is False
    assert path_requires_auth("GET", "/api/evaluations") is True
    assert path_requires_auth("POST", "/api/evaluations") is True
    assert path_requires_auth("GET", "/api/evaluations/pilot-openssl-330") is False
