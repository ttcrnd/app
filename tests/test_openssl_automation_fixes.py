"""Tests for OpenSSL automation correctness fixes (heuristic flags, signals, FORCE_CONFIRM)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.workflow import FORCE_CONFIRM_IDS, normalize_form_workflow
from pipeline.repo_signals import (
    KNOWN_SECURITY_POLICY_URLS,
    TEST_ROOT_CANDIDATES,
    detect_security_policy,
)


def test_force_confirm_includes_dependency_and_docs_risk_ids():
    assert "2-17" in FORCE_CONFIRM_IDS
    assert "4-2" in FORCE_CONFIRM_IDS
    assert "4-3" in FORCE_CONFIRM_IDS


def test_high_confidence_facts_stay_auto_after_pipeline():
    form = {
        "rating_options": ["nehodnoceno", "splňuje", "částečně splňuje", "nesplňuje"],
        "sections": [
            {
                "id": "2",
                "questions": [
                    {"id": "2-1a", "rating": "splňuje", "heuristic_rating": True},
                    {"id": "2-19", "rating": "splňuje", "heuristic_rating": True},
                    {"id": "2-17", "rating": "splňuje", "heuristic_rating": True},
                    {"id": "4-3", "rating": "splňuje", "heuristic_rating": True},
                    {"id": "5-1", "rating": "splňuje", "heuristic_rating": True},
                ],
            }
        ],
    }
    out = normalize_form_workflow(form, pipeline_mode=True)
    by_id = {q["id"]: q for q in out["sections"][0]["questions"]}
    assert by_id["2-1a"]["review_state"] == "AUTO"
    assert by_id["2-1a"]["rating"] == "splňuje"
    assert by_id["2-19"]["review_state"] == "AUTO"
    assert by_id["2-17"]["review_state"] == "CONFIRM"
    assert by_id["4-3"]["review_state"] == "CONFIRM"
    assert by_id["5-1"]["review_state"] == "AUTO"


def test_questions_json_heuristic_flags_for_facts_and_section5():
    import json

    data = json.loads((ROOT / "assets" / "questions.json").read_text(encoding="utf-8"))
    flags = {}
    for section in data.get("sections") or []:
        for q in section.get("questions") or []:
            flags[q["id"]] = bool(q.get("heuristic_rating"))
    for qid in ("2-1", "2-1a", "2-1d", "2-15", "2-19", "5-1", "5-4", "5-14"):
        assert flags.get(qid) is True, qid


def test_test_root_candidates_include_test_dir():
    assert "test" in TEST_ROOT_CANDIDATES
    assert "tests" in TEST_ROOT_CANDIDATES


def test_openssl_known_security_policy_url():
    assert "openssl/openssl" in KNOWN_SECURITY_POLICY_URLS
    policy = detect_security_policy("openssl", "openssl")
    assert policy["has_policy_signal"] is True
    assert any("openssl.org/policies/security" in u for u in policy["policy_urls"])
