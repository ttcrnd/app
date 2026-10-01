from __future__ import annotations

from domain.scoring import calculate_summary
from domain.workflow import RATING_NA, RATING_NEUTRAL, normalize_form_workflow, normalize_rating


def _base_form(*, rating: str, category: str = "must have") -> dict:
    return {
        "rating_options": [
            "nehodnoceno",
            "splňuje",
            "částečně splňuje",
            "nesplňuje",
        ],
        "scoring": {
            "section_weights_percent": {"1": 100},
            "rating_points": {
                "splňuje": 1.0,
                "částečně splňuje": 0.75,
                "nesplňuje": 0.0,
                "nehodnoceno": 0.25,
            },
            "category_weights": {"must have": 1.0, "good to have": 0.95},
            "cutoffs": {"scoring_grades": {"pass_min": 75, "good": 85, "excellent": 92}},
        },
        "sections": [
            {
                "id": "1",
                "title": "Předpoklady",
                "questions": [
                    {
                        "id": "1-x",
                        "category": category,
                        "rating": rating,
                        "note": "",
                        "checked": True,
                    },
                    {
                        "id": "1-y",
                        "category": "good to have",
                        "rating": "splňuje",
                        "note": "",
                        "checked": True,
                    },
                ],
            }
        ],
    }


def test_legacy_na_folds_into_nehodnoceno():
    assert normalize_rating(RATING_NA) == RATING_NEUTRAL


def test_workflow_maps_legacy_na_and_drops_option():
    form = {
        "rating_options": [
            "nehodnoceno",
            "splňuje",
            "částečně splňuje",
            "nesplňuje",
            "nevztahuje se",
        ],
        "sections": [
            {
                "id": "5-sec:api",
                "questions": [
                    {
                        "id": "5-9",
                        "rating": RATING_NA,
                        "heuristic_rating": False,
                        "review_state": "MANUAL",
                    }
                ],
            }
        ],
    }
    out = normalize_form_workflow(form, pipeline_mode=False)
    q = out["sections"][0]["questions"][0]
    assert q["rating"] == RATING_NEUTRAL
    assert RATING_NA not in out["rating_options"]
    assert out["rating_options"] == [
        "nehodnoceno",
        "splňuje",
        "částečně splňuje",
        "nesplňuje",
    ]


def test_nehodnoceno_still_counts_in_average():
    form = _base_form(rating=RATING_NEUTRAL)
    # Force unchecked unresolved semantics for summary path that reads rating only.
    form["sections"][0]["questions"][0]["checked"] = False
    summary = calculate_summary(form)
    # Companion question is splňuje (100); unresolved is 25% → average depends on weights.
    assert summary["section_scores"]["1"] < 100.0
