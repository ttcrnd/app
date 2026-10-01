from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

from _web_js import read_web_js


def _client(tmp_path, monkeypatch):
    import db.repository as repository
    import server
    from db.session import init_db, reset_engine

    db_url = f"sqlite:///{tmp_path / 'review.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setattr(repository, "ARTIFACTS_DIR", tmp_path / "artifacts")
    monkeypatch.setattr("db.repos.common.ARTIFACTS_DIR", tmp_path / "artifacts")
    # Isolate signing keys per test
    monkeypatch.setenv("SIGNING_KEY_PATH", str(tmp_path / "ed25519_private.pem"))
    reset_engine()
    init_db(url=db_url)
    return TestClient(server.app)


def test_step12_ui_and_docs():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = read_web_js(WEB)
    assert 'id="signDialog"' in html
    assert "Podepsat export" in html
    assert "downloadSignedBtn" in html
    assert "/sign" in js
    assert "Podepsáno" in js
    assert (ROOT / "docs" / "SIGNING.md").exists()
    assert (ROOT / "scripts" / "verify_signed_export.py").exists()


def test_step12_sign_verify_tamper(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    pub = client.get("/api/signing/public-key")
    assert pub.status_code == 200
    assert pub.json()["alg"] == "ed25519"
    assert "BEGIN PUBLIC KEY" in pub.json()["public_key_pem"]

    saved = client.post(
        "/api/evaluations",
        json={
            "form": {
                "meta": {"repo": "openssl/openssl", "effective_ref": "openssl-3.3.0"},
                "sections": [
                    {
                        "id": 1,
                        "questions": [
                            {
                                "id": "1-1",
                                "text": "Identita",
                                "rating": "splňuje",
                                "note": "ok",
                                "category": "must have",
                                "description": "",
                                "evidence": [],
                                "heuristic": "",
                            }
                        ],
                    }
                ],
            }
        },
    )
    assert saved.status_code == 200
    eval_id = saved.json()["id"]

    # Must complete before sign
    bad = client.post(f"/api/evaluations/{eval_id}/sign")
    assert bad.status_code == 400

    done = client.post(
        f"/api/evaluations/{eval_id}/complete",
        json={"outcome": "completed", "note": "Schváleno pro podpis."},
    )
    assert done.status_code == 200

    signed = client.post(f"/api/evaluations/{eval_id}/sign")
    assert signed.status_code == 200
    assert signed.json()["signed"] is True
    assert signed.json()["sig"]["alg"] == "ed25519"

    export = client.get(f"/api/evaluations/{eval_id}/signed-export")
    assert export.status_code == 200
    wrapper = export.json()
    assert "payload" in wrapper and "sig" in wrapper
    assert wrapper["payload"]["meta"].get("approved_label", "").startswith("Schválil:")

    ok = client.post("/api/evaluations/verify", json=wrapper)
    assert ok.status_code == 200
    assert ok.json()["valid"] is True

    # Tamper one rating → verify fails
    tampered = json.loads(json.dumps(wrapper))
    tampered["payload"]["sections"][0]["questions"][0]["rating"] = "nesplňuje"
    fail = client.post("/api/evaluations/verify", json=tampered)
    assert fail.status_code == 200
    assert fail.json()["valid"] is False

    libs = client.get("/api/libraries").json()["libraries"]
    openssl = next(item for item in libs if item["repo"] == "openssl/openssl")
    assert openssl["latest_evaluation"]["signed"] is True


def test_step12_canonical_utils():
    from services.signing import (
        canonical_json_bytes,
        sign_payload,
        strip_volatile,
        verify_signed_export,
    )

    form = {
        "_draft_id": "x",
        "meta": {"repo": "a/b", "completion_note": "ok", "_ui": 1},
        "sections": [{"id": 1, "questions": [{"id": "1-1", "rating": "splňuje"}]}],
    }
    cleaned = strip_volatile(form)
    assert "_draft_id" not in cleaned
    assert "_ui" not in cleaned["meta"]
    a = canonical_json_bytes(form)
    b = canonical_json_bytes(form)
    assert a == b

    wrapper = sign_payload(form, root=ROOT)
    assert verify_signed_export(wrapper, root=ROOT)["valid"] is True
