from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

from _web_js import read_web_js
REVIEW_ROOT = ROOT.parent


def _client_with_db(tmp_path, monkeypatch):
    import db.repository as repository
    import server
    from db.repository import seed_pilot_libraries
    from db.session import get_session_factory, init_db, reset_engine

    db_path = tmp_path / "review.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(repository, "ARTIFACTS_DIR", tmp_path / "artifacts")
    monkeypatch.setattr("db.repos.common.ARTIFACTS_DIR", tmp_path / "artifacts")
    reset_engine()
    init_db(url=url)
    session = get_session_factory()()
    try:
        seed_pilot_libraries(session)
        session.commit()
    finally:
        session.close()
    return TestClient(server.app)


def test_step8_ui_markers():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = read_web_js(WEB)
    assert 'id="catalogSearch"' in html
    assert 'id="catalogStatusFilter"' in html
    assert 'id="libraryDetail"' in html
    assert 'id="completeDialog"' in html
    assert 'id="completeEvalBtn"' in html
    assert "/api/libraries" in js
    assert "complete" in js
    assert "loadLibrariesList" in js
    assert "Nedoporučit k použití" in html or "Nedoporučit" in html
    pilot = (REVIEW_ROOT / "knihovny-pilot.md").read_text(encoding="utf-8")
    assert "openssl/openssl" in pilot
    assert "rpgp/rpgp" in pilot


def test_step8_catalog_seed_search_complete(tmp_path, monkeypatch):
    client = _client_with_db(tmp_path, monkeypatch)

    # Startup seeds pilot libraries
    libs = client.get("/api/libraries").json()["libraries"]
    repos = {item["repo"] for item in libs}
    assert "openssl/openssl" in repos
    assert "rpgp/rpgp" in repos
    assert "jedisct1/libsodium" in repos

    filtered = client.get("/api/libraries", params={"q": "rpgp"}).json()["libraries"]
    assert filtered
    assert all(
        "rpgp" in item["repo"].lower() or "rpgp" in (item["name"] or "").lower()
        for item in filtered
    )

    none_status = client.get("/api/libraries", params={"status": "none"}).json()["libraries"]
    assert none_status
    assert all(item["catalog_status"] == "none" for item in none_status)

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
    eval_id = saved.json()["id"]

    in_progress = client.get("/api/libraries", params={"status": "in_progress"}).json()["libraries"]
    assert any(item["repo"] == "openssl/openssl" for item in in_progress)
    assert in_progress[0]["catalog_status"] in {"in_progress", "draft"}

    bad = client.post(
        f"/api/evaluations/{eval_id}/complete",
        json={"outcome": "completed", "note": "x"},
    )
    assert bad.status_code == 400

    done = client.post(
        f"/api/evaluations/{eval_id}/complete",
        json={"outcome": "completed", "note": "Pilotní hodnocení pro pilot."},
    )
    assert done.status_code == 200
    assert done.json()["status"] == "completed"
    assert done.json()["status_label"] == "Hotovo"

    completed = client.get("/api/libraries", params={"status": "completed"}).json()["libraries"]
    assert any(item["repo"] == "openssl/openssl" for item in completed)

    detail = client.get(f"/api/libraries/{completed[0]['id']}").json()
    assert detail["evaluations"]
    assert detail["evaluations"][0]["status"] == "completed"

    rejected = client.post(
        "/api/evaluations",
        json={
            "form": {
                "meta": {"repo": "jedisct1/libsodium", "effective_ref": "1.0.20-RELEASE"},
                "sections": [{"id": "1", "questions": []}],
            }
        },
    )
    assert rejected.status_code == 200
    rej_id = rejected.json()["id"]
    mark = client.post(
        f"/api/evaluations/{rej_id}/complete",
        json={"outcome": "not_recommended", "note": "Pro pilot raději OpenSSL."},
    )
    assert mark.status_code == 200
    assert mark.json()["status"] == "not_recommended"

    viewer = client.get("/api/libraries", params={"role": "viewer"}).json()["libraries"]
    assert viewer
    assert all(item["catalog_status"] in {"completed", "not_recommended"} for item in viewer)

    lib_id = completed[0]["id"]
    deleted = client.delete(f"/api/libraries/{lib_id}")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    assert client.get(f"/api/libraries/{lib_id}").status_code == 404
    remaining = {item["repo"] for item in client.get("/api/libraries").json()["libraries"]}
    assert "openssl/openssl" not in remaining


def test_step8_ui_delete_marker():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = read_web_js(WEB)
    assert 'id="libraryDetailDelete"' in html
    assert "deleteLibraryById" in js
    assert "Smazat knihovnu" in html
    assert "syncWorkToSelectedLibrary" in js
    assert "syncSelectedLibraryFromForm" in js
