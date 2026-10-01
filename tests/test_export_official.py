from __future__ import annotations

from domain.export import (
    find_unevaluated_official_questions,
    is_appendix_section,
    validate_official_export,
)
from domain.scoring import calculate_summary


def test_methodology_form_has_no_supply_gate():
    form = {
        "scoring": {
            "section_weights_percent": {"1": 100},
            "rating_points": {
                "splňuje": 1.0,
                "částečně splňuje": 0.75,
                "nesplňuje": 0.0,
                "nehodnoceno": 0.25,
            },
            "category_weights": {"must have": 1.0},
            "cutoffs": {"scoring_grades": {"pass_min": 75, "good": 85, "excellent": 92}},
        },
        "sections": [
            {
                "id": "1",
                "questions": [
                    {"id": "1-1", "rating": "splňuje", "category": "must have", "note": ""},
                    {"id": "1-2", "rating": "splňuje", "category": "must have", "note": ""},
                    {"id": "1-3", "rating": "splňuje", "category": "must have", "note": ""},
                ],
            }
        ],
    }
    summary = calculate_summary(form)
    assert "gate" not in summary
    assert summary["grade"] in {"pass", "good", "excellent"}
    assert summary["grade"] != "gate-fail"


def test_appendix_questions_ignored_for_official_export():
    form = {
        "sections": [
            {
                "id": "extra",
                "type": "appendix",
                "questions": [{"id": "x-1", "rating": "nehodnoceno"}],
            },
            {
                "id": "1",
                "title": "Předpoklady",
                "questions": [
                    {"id": "1-1", "rating": "splňuje"},
                    {"id": "1-2", "rating": "částečně splňuje"},
                    {"id": "1-3", "rating": "nesplňuje"},
                ],
            },
        ]
    }
    assert validate_official_export(form)["ok"] is True
    assert find_unevaluated_official_questions(form) == []


def test_unevaluated_official_blocks_export():
    form = {
        "sections": [
            {
                "id": "1",
                "questions": [
                    {"id": "1-1", "rating": "splňuje"},
                    {"id": "1-2", "rating": None},
                    {"id": "1-3", "rating": "nehodnoceno"},
                ],
            }
        ]
    }
    result = validate_official_export(form)
    assert result["ok"] is False
    assert result["missing_count"] == 2
    ids = {item["question_id"] for item in result["missing"]}
    assert ids == {"1-2", "1-3"}


def test_is_appendix_section():
    assert is_appendix_section({"id": "extra", "type": "appendix"}) is True
    assert is_appendix_section({"id": "1", "title": "Předpoklady"}) is False
