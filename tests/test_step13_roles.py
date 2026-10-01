from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

from _web_js import read_web_js


def _client(tmp_path, monkeypatch, *, user_auth=True, pilot_code=True, code="pilot-secret"):
    import db.repository as repository
    import server
    from db.session import get_session_factory, init_db, reset_engine

    db_url = f"sqlite:///{tmp_path / 'review.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setattr(repository, "ARTIFACTS_DIR", tmp_path / "artifacts")
    monkeypatch.setattr("db.repos.common.ARTIFACTS_DIR", tmp_path / "artifacts")
    monkeypatch.setenv("PILOT_SESSION_SECRET", "test-secret-step13")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-secret")
    monkeypatch.setenv("USER_AUTH_ENABLED", "true" if user_auth else "false")
    if pilot_code:
        monkeypatch.setenv("PILOT_ACCESS_CODE", code)
        monkeypatch.setenv("PILOT_CODE_ENABLED", "true")
    else:
        monkeypatch.setenv("PILOT_ACCESS_CODE", code)
        monkeypatch.setenv("PILOT_CODE_ENABLED", "false")
    monkeypatch.setattr(server, "_configured_token", lambda: None)
    monkeypatch.setattr("review_app.deps.configured_token", lambda: None)
    reset_engine()
    init_db()  # uses DATABASE_URL from env; sets global engine
    session = get_session_factory()()
    try:
        repository.ensure_pilot_user(session)
        repository.ensure_bootstrap_admin(session, server.ROOT)
        session.commit()
    finally:
        session.close()
    return TestClient(server.app)


def test_step13_ui_markers():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = read_web_js(WEB)
    css = (WEB / "styles.css").read_text(encoding="utf-8")

    assert 'id="viewUsers"' in html
    assert 'id="navUsersBtn"' in html
    assert 'id="authLoginForm"' in html
    assert 'id="authRoleBadge"' in html
    assert "handleAuthLogin" in js
    assert "loadUsersAdmin" in js
    assert "canManageUsers" in js
    assert ".auth-gate__tabs" in css
    assert ".users-list__row" in css
    assert (ROOT / "docs" / "ROLES.md").exists()


def test_step13_viewer_cannot_write(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, user_auth=True, pilot_code=False)

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin-secret"},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "admin"

    created = client.post(
        "/api/users",
        json={"username": "looker", "password": "looker1", "role": "viewer"},
    )
    assert created.status_code == 200
    assert created.json()["role"] == "viewer"

    client.post("/api/auth/logout")
    viewer = client.post(
        "/api/auth/login",
        json={"username": "looker", "password": "looker1"},
    )
    assert viewer.status_code == 200
    assert viewer.json()["role"] == "viewer"

    blocked = client.post("/api/run", json={"repo": "openssl/openssl"})
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "forbidden"

    status = client.get("/api/auth/status")
    assert status.json()["can_write"] is False
    assert status.json()["can_manage_users"] is False


def test_step13_admin_creates_reviewer_and_d11(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, user_auth=True, pilot_code=False)

    admin = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin-secret"},
    )
    assert admin.status_code == 200

    rev = client.post(
        "/api/users",
        json={"username": "alice", "password": "alice12", "role": "reviewer"},
    )
    assert rev.status_code == 200
    alice_id = rev.json()["id"]

    saved = client.post(
        "/api/evaluations",
        json={
            "form": {
                "meta": {"repo": "openssl/openssl", "effective_ref": "openssl-3.3.0"},
                "sections": [],
            }
        },
    )
    assert saved.status_code == 200
    eval_id = saved.json()["id"]

    client.post("/api/auth/logout")
    alice = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "alice12"},
    )
    assert alice.status_code == 200
    assert alice.json()["role"] == "reviewer"

    foreign = client.post(
        "/api/evaluations",
        json={
            "id": eval_id,
            "form": {
                "meta": {"repo": "openssl/openssl", "effective_ref": "openssl-3.3.0"},
                "sections": [],
            },
        },
    )
    assert foreign.status_code == 403
    assert "D11" in foreign.json()["detail"]

    own = client.post(
        "/api/evaluations",
        json={
            "form": {
                "meta": {"repo": "rpgp/rpgp", "effective_ref": "v0.19.0"},
                "sections": [],
            }
        },
    )
    assert own.status_code == 200
    assert own.json()["id"]

    users = client.get("/api/users")
    assert users.status_code == 403

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "admin", "password": "admin-secret"})
    patched = client.patch(f"/api/users/{alice_id}", json={"role": "viewer"})
    assert patched.status_code == 200
    assert patched.json()["role"] == "viewer"


def test_step13_code_bootstrap_admin_when_user_auth(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, user_auth=True, pilot_code=True, code="boot-code")

    ok = client.post("/api/auth/enter", json={"code": "boot-code"})
    assert ok.status_code == 200
    assert ok.json()["role"] == "admin"

    created = client.post(
        "/api/users",
        json={"username": "bob", "password": "bobbob1", "role": "reviewer"},
    )
    assert created.status_code == 200

    monkeypatch.setenv("PILOT_CODE_ENABLED", "false")
    import server
    from utils import pilotauth

    assert pilotauth.pilot_code_enabled(server.ROOT) is False
    assert pilotauth.user_auth_enabled(server.ROOT) is True
    assert pilotauth.auth_required(server.ROOT) is True

    denied = client.post("/api/auth/enter", json={"code": "boot-code"})
    assert denied.status_code == 400
    assert denied.json()["detail"]["code"] == "use_password_login"
