from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

from _web_js import read_web_js


def _client_with_db(tmp_path, monkeypatch):
    import db.repository as repository
    import server
    from db.session import init_db, reset_engine

    db_path = tmp_path / "review.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(repository, "ARTIFACTS_DIR", tmp_path / "artifacts")
    monkeypatch.setattr("db.repos.common.ARTIFACTS_DIR", tmp_path / "artifacts")
    reset_engine()
    init_db(url=url)
    return TestClient(server.app)


def test_step7_markers_and_docs():
    assert (ROOT / "docs" / "DATABASE.md").exists()
    assert (ROOT / "db" / "models.py").exists()
    assert (ROOT / "alembic" / "versions" / "001_initial.py").exists()
    js = read_web_js(WEB)
    assert "/api/drafts" in js or "/api/evaluations" in js
    docs = (ROOT / "docs" / "DATABASE.md").read_text(encoding="utf-8")
    assert "postgresql+psycopg" in docs
    assert "DATABASE_URL" in docs


def test_step7_evaluations_crud_sqlite(tmp_path, monkeypatch):
    client = _client_with_db(tmp_path, monkeypatch)

    payload = {
        "form": {
            "meta": {"repo": "openssl/openssl", "effective_ref": "openssl-3.3.0"},
            "sections": [{"id": "1", "questions": []}],
        }
    }
    saved = client.post("/api/evaluations", json=payload)
    assert saved.status_code == 200
    body = saved.json()
    assert body["id"]
    assert "openssl/openssl" in body["title"]
    assert body["library"] == "openssl/openssl"

    listed = client.get("/api/evaluations")
    assert listed.status_code == 200
    assert listed.json()["evaluations"][0]["id"] == body["id"]

    assert client.get("/api/drafts").json()["drafts"][0]["id"] == body["id"]

    loaded = client.get(f"/api/evaluations/{body['id']}")
    assert loaded.status_code == 200
    form = loaded.json()["form"]
    assert form["_evaluation_id"] == body["id"]
    assert form["meta"]["repo"] == "openssl/openssl"

    assert (tmp_path / "artifacts" / body["id"] / "form.json").exists()

    libs = client.get("/api/libraries")
    assert libs.status_code == 200
    libraries = libs.json()["libraries"]
    assert libraries
    assert libraries[0]["repo"] == "openssl/openssl"

    detail = client.get(f"/api/libraries/{libraries[0]['id']}")
    assert detail.status_code == 200
    assert detail.json()["evaluations"][0]["id"] == body["id"]

    info = client.get("/api/db/info")
    assert info.status_code == 200
    assert info.json()["postgres_ready"] is True
    assert info.json()["dialect"].startswith("sqlite")


def test_step7_two_evaluations_same_repo(tmp_path, monkeypatch):
    client = _client_with_db(tmp_path, monkeypatch)
    for i, ref in enumerate(("v1", "v2"), start=1):
        resp = client.post(
            "/api/evaluations",
            json={
                "id": f"eval{i}",
                "form": {
                    "meta": {"repo": "example/lib", "effective_ref": ref},
                    "sections": [],
                },
            },
        )
        assert resp.status_code == 200
    items = client.get("/api/evaluations").json()["evaluations"]
    ids = {item["id"] for item in items}
    assert "eval1" in ids and "eval2" in ids
    libs = client.get("/api/libraries").json()["libraries"]
    assert len(libs) == 1
    detail = client.get(f"/api/libraries/{libs[0]['id']}").json()
    assert len(detail["evaluations"]) == 2
    assert len(detail["versions"]) == 2
