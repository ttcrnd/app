from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("httpx2")

from fastapi.testclient import TestClient

from server import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def _load_questions() -> dict:
    return json.loads((ROOT / "assets" / "questions.json").read_text(encoding="utf-8"))


def test_validate_form_accepts_valid_payload() -> None:
    payload = _load_questions()
    response = client.post("/api/validate-form", json={"form": payload})
    assert response.status_code == 200
    body = response.json()
    assert body.get("valid") is True
    assert isinstance(body.get("form"), dict)
    assert isinstance(body.get("summary"), dict)
    assert "grade" in body["summary"]


def test_validate_form_rejects_schema_mismatch() -> None:
    response = client.post("/api/validate-form", json={"form": {"title": "only-title"}})
    assert response.status_code == 422
    detail = response.json().get("detail", {})
    assert detail.get("message")
    assert detail.get("path") == "$"
    assert detail.get("reason")
    assert detail.get("hint")


def test_validate_form_rejects_non_object_form() -> None:
    response = client.post("/api/validate-form", json={"form": ["invalid"]})
    assert response.status_code == 400
    assert "form" in response.json().get("detail", "").lower()
