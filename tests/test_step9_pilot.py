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
    from db.repository import seed_pilot_evaluations, seed_pilot_libraries
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
        seed_pilot_evaluations(session, examples_dir=ROOT / "assets" / "example")
        session.commit()
    finally:
        session.close()
    return TestClient(server.app)


def test_step9_docs_and_ui_markers():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = read_web_js(WEB)
    assert 'id="pilotStatusBanner"' in html
    assert "loadPilotStatus" in js
    assert "/api/pilot/status" in js or "pilot/status" in js

    pilot = (REVIEW_ROOT / "knihovny-pilot.md").read_text(encoding="utf-8")
    assert "Nedoporučeno" in pilot
    assert "Dokončit hodnocení" in pilot
    empirie = (REVIEW_ROOT / "empirie-pilot.md").read_text(encoding="utf-8")
    assert "AUTO" in empirie
    assert "openssl/openssl" in empirie


def test_step9_pilot_seed_empirie_d10(tmp_path, monkeypatch):
    client = _client_with_db(tmp_path, monkeypatch)

    status = client.get("/api/pilot/status")
    assert status.status_code == 200
    body = status.json()
    assert body["libraries"] >= 3
    assert body["not_recommended"] >= 1
    assert body["libraries_terminal"] >= 3
    assert body["d10_closed"] is True
    assert body["empirie"]["evaluations"] >= 2

    empirie = client.get("/api/pilot/empirie")
    assert empirie.status_code == 200
    data = empirie.json()
    assert data["evaluations"] >= 2
    assert data["accepted_auto_total"] >= 10
    assert data["confirm_after_heuristic_total"] >= 20
    assert data["heuristic_accept_rate_pct"] > 0

    libs = client.get("/api/libraries").json()["libraries"]
    by_repo = {item["repo"]: item for item in libs}
    assert by_repo["openssl/openssl"]["catalog_status"] == "completed"
    assert by_repo["rpgp/rpgp"]["catalog_status"] == "completed"
    assert by_repo["jedisct1/libsodium"]["catalog_status"] == "not_recommended"

    # Idempotent re-seed
    from db.repository import seed_pilot_evaluations
    from db.session import get_session_factory

    session = get_session_factory()()
    try:
        again = seed_pilot_evaluations(session, examples_dir=ROOT / "assets" / "example")
        session.commit()
        assert again == 0
    finally:
        session.close()
