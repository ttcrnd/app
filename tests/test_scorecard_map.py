"""Unit tests for Scorecard mapping and workflow force-confirm (task-automatizace E1/E2)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.workflow import FORCE_CONFIRM_IDS, normalize_form_workflow
from integrations.scorecard import build_scorecard_map, check_score, score_meets
from pipeline.misuse_scan import scan_text
from pipeline.security_md import parse_security_md


def _sample_scorecard():
    return {
        "status": 200,
        "data": {
            "repo": {"name": "github.com/example/lib"},
            "checks": [
                {"name": "Code-Review", "score": 8, "detailsUrl": "https://example.com/cr"},
                {"name": "Branch-Protection", "score": 6},
                {"name": "CI-Tests", "score": 9},
                {"name": "Fuzzing", "score": 5},
                {"name": "Dependency-Update-Tool", "score": 7},
                {"name": "Pinned-Dependencies", "score": 8},
                {"name": "Binary-Artifacts", "score": 9},
                {"name": "Dangerous-Workflow", "score": 10},
                {"name": "Token-Permissions", "score": 4},
                {"name": "Secret-Scanning", "score": 6},
            ],
        },
    }


def test_scorecard_check_score_and_map():
    payload = _sample_scorecard()
    assert check_score(payload, "Code-Review") == 8.0
    assert score_meets(check_score(payload, "CI-Tests"), 7)
    mapped = build_scorecard_map(payload)
    assert mapped["checks"]["Code-Review"] == 8.0
    assert mapped["checks"]["Fuzzing"] == 5.0
    assert mapped["checks"]["Pinned-Dependencies"] == 8.0
    assert mapped["checks"]["Token-Permissions"] == 4.0
    assert "Code-Review" in mapped["urls"]


def test_force_confirm_ids_block_auto():
    form = {
        "rating_options": ["nehodnoceno", "splňuje", "částečně splňuje", "nesplňuje"],
        "sections": [
            {
                "id": "1",
                "questions": [
                    {
                        "id": "1-2",
                        "rating": "splňuje",
                        "heuristic_rating": True,
                    },
                    {
                        "id": "2-1a",
                        "rating": "splňuje",
                        "heuristic_rating": True,
                    },
                ],
            }
        ],
    }
    out = normalize_form_workflow(form, pipeline_mode=True)
    q_by_id = {q["id"]: q for q in out["sections"][0]["questions"]}
    assert "1-2" in FORCE_CONFIRM_IDS
    assert q_by_id["1-2"]["review_state"] == "CONFIRM"
    assert q_by_id["2-1a"]["review_state"] == "AUTO"


def test_security_md_parse_process_like():
    body = """
    # Security
    Report to security@example.org via PGP.
    We aim to respond within 5 business days.
    Supported versions and backport policy below.
    """
    parsed = parse_security_md(body)
    assert parsed["process_like"] is True
    assert parsed["signals"]["has_security_email"]


def test_misuse_scan_detects_ecb():
    hits = scan_text('cipher = AES.new(key, AES.MODE_ECB)', source="examples/bad.py")
    assert any(h["pattern"] == "ECB" for h in hits)
