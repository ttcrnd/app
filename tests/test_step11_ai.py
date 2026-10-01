from __future__ import annotations

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
    reset_engine()
    init_db(url=db_url)
    return TestClient(server.app)


def test_step11_ui_markers():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = read_web_js(WEB)
    css = (WEB / "styles.css").read_text(encoding="utf-8")
    assert "Navrhnout poznámku (AI)" in js
    assert "proposal_source" in js
    assert "Návrh AI" in js
    assert "q-badge--ai" in css
    assert "/api/ai/suggest-note" in js
    # AI is optional chrome — page still loads without AI block in HTML shell
    assert "viewWork" in html


def test_step11_ai_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("AI_ENABLED", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = _client(tmp_path, monkeypatch)

    status = client.get("/api/ai/status")
    assert status.status_code == 200
    body = status.json()
    assert body["enabled"] is False
    assert body["available"] is False
    assert body["default_off"] is True

    cfg = client.get("/api/config").json()
    assert cfg["ai"]["enabled"] is False

    denied = client.post(
        "/api/ai/suggest-note",
        json={
            "question": {
                "id": "1-1",
                "text": "Kritérium",
                "note": "",
                "evidence": "https://example.com",
                "rating": "částečně splňuje",
            }
        },
    )
    assert denied.status_code == 400
    assert "vypnut" in str(denied.json()["detail"]).lower() or "AI" in str(denied.json()["detail"])


def test_step11_suggest_note_mock_openai(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    client = _client(tmp_path, monkeypatch)

    import services.ai as ai_assist

    class FakeClient(ai_assist.AiAssistClient):
        provider = "openai"

        def suggest_note(self, **kwargs):
            assert "ghp_" not in (kwargs.get("evidence") or "")
            assert "[REDACTED]" in (kwargs.get("evidence") or "")
            return ai_assist.AiSuggestResult(
                text="Navržená poznámka z důkazů bez změny ratingu.",
                model="gpt-test",
                provider="openai",
            )

        def suggest_remaining_summary(self, **kwargs):
            return ai_assist.AiSuggestResult(
                text="Zbývá ověřit must-have.",
                model="gpt-test",
                provider="openai",
            )

    monkeypatch.setattr(ai_assist, "get_ai_client", lambda: FakeClient())

    # Save evaluation so ai_suggest event can attach
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

    ok = client.post(
        "/api/ai/suggest-note",
        json={
            "evaluation_id": eval_id,
            "question": {
                "id": "1-1",
                "text": "Identita knihovny",
                "description": "Ověř repo",
                "evidence": "https://github.com/openssl/openssl\nghp_SHOULD_NOT_LEAK_IN_ASSERT",
                "note": "Stará poznámka",
                "heuristic": "README existuje",
                "rating": "částečně splňuje",
                "category": "must have",
            },
        },
    )
    assert ok.status_code == 200
    data = ok.json()
    assert data["proposal_source"] == "ai"
    assert data["rating_unchanged"] is True
    assert "Navržená poznámka" in data["suggestion"]
    assert data["model"] == "gpt-test"

    # Event logged
    from sqlalchemy import select

    from db.models import EvaluationEvent
    from db.session import get_session_factory

    session = get_session_factory()()
    try:
        events = session.scalars(
            select(EvaluationEvent).where(EvaluationEvent.evaluation_id == eval_id)
        ).all()
        types = [e.event_type for e in events]
        assert "ai_suggest" in types
    finally:
        session.close()


def test_step11_redact_secrets():
    from services.ai import redact_secrets

    raw = "token ghp_abcdefghijklmnopqrstuv123456 and sk-abcDEF1234567890xxxx"
    cleaned = redact_secrets(raw)
    assert "ghp_" not in cleaned
    assert "sk-abc" not in cleaned
    assert "[REDACTED]" in cleaned


def test_step11_path_requires_auth_for_ai():
    from auth.pilot import path_requires_auth

    assert path_requires_auth("POST", "/api/ai/suggest-note") is True
    assert path_requires_auth("GET", "/api/ai/status") is False
