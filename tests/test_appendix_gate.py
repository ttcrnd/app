from __future__ import annotations

from domain.scoring import calculate_summary


def test_no_gate_fail_without_supply_section():
    form = {
        "scoring": {
            "section_weights_percent": {"1": 100},
            "rating_points": {
                "splňuje": 1.0,
                "částečně splňuje": 0.75,
                "nesplňuje": 0.0,
                "nehodnoceno": 0.25,
            },
            "category_weights": {
                "must have": 1.0,
                "good to have": 0.95,
                "nice to have": 0.85,
            },
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
            },
        ],
    }
    summary = calculate_summary(form)
    assert "gate" not in summary
    assert summary["grade"] != "gate-fail"
    assert summary["cutoffs"]["passed"] is True
