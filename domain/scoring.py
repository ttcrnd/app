from __future__ import annotations

from typing import Any

DEFAULT_RATING_POINTS = {
    "splňuje": 1.0,
    "částečně splňuje": 0.5,
    "nesplňuje": 0.0,
    "nehodnoceno": 0.0,
    "nevztahuje se": 0.0,
}

DEFAULT_CATEGORY_WEIGHTS = {
    "must have": 1.0,
    "good to have": 1.0,
    "nice to have": 1.0,
}

DEFAULT_BENCHMARK_BAND = {
    "reference_min": 70.0,
    "reference_good": 82.0,
    "reference_excellent": 90.0,
}


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_category(raw: Any) -> str:
    return str(raw or "").strip().lower()


def _load_rating_points(scoring: dict[str, Any]) -> dict[str, float]:
    points = dict(DEFAULT_RATING_POINTS)
    cfg = scoring.get("rating_points")
    if not isinstance(cfg, dict):
        return points
    for key in points:
        if key not in cfg:
            continue
        value = _to_float(cfg.get(key), points[key])
        points[key] = max(0.0, min(1.0, value))
    return points


def _load_category_weights(scoring: dict[str, Any]) -> dict[str, float]:
    weights = dict(DEFAULT_CATEGORY_WEIGHTS)
    cfg = scoring.get("category_weights")
    if not isinstance(cfg, dict):
        return weights
    for key in list(weights):
        if key not in cfg:
            continue
        value = _to_float(cfg.get(key), weights[key])
        weights[key] = max(0.1, value)
    return weights


def _load_benchmark_band(scoring: dict[str, Any]) -> dict[str, float]:
    band = dict(DEFAULT_BENCHMARK_BAND)
    cfg = scoring.get("benchmark_reference_band")
    if not isinstance(cfg, dict):
        return band
    for key in band:
        if key not in cfg:
            continue
        band[key] = _to_float(cfg.get(key), band[key])
    if band["reference_good"] < band["reference_min"]:
        band["reference_good"] = band["reference_min"]
    if band["reference_excellent"] < band["reference_good"]:
        band["reference_excellent"] = band["reference_good"]
    return band


def _rating_fraction(rating: Any, rating_points: dict[str, float]) -> float:
    if rating is None:
        return rating_points["nehodnoceno"]
    key = str(rating).strip().lower()
    if not key:
        key = "nehodnoceno"
    return rating_points.get(key, rating_points["nehodnoceno"])


def _reference_position(overall_score: float, band: dict[str, float]) -> str:
    if overall_score >= band["reference_excellent"]:
        return "reference-excellent"
    if overall_score >= band["reference_good"]:
        return "reference-good"
    if overall_score >= band["reference_min"]:
        return "reference-min"
    return "below-reference"


def _has_timeline(note: str) -> bool:
    s = (note or "").lower()
    return ("mitig" in s or "plán" in s or "plan" in s) and (
        "30" in s or "≤ 30" in s or "30d" in s or "30 days" in s or "30 dní" in s or "do 30" in s
    )


def calculate_summary(form_sc: dict[str, Any]) -> dict[str, Any]:
    scoring = form_sc.get("scoring", {}) if isinstance(form_sc.get("scoring"), dict) else {}
    section_weights = {
        str(k): _to_float(v, 0.0) / 100.0
        for k, v in (scoring.get("section_weights_percent", {}) or {}).items()
    }
    rating_points = _load_rating_points(scoring)
    category_weights = _load_category_weights(scoring)
    benchmark_band = _load_benchmark_band(scoring)
    benchmark_profile = str(scoring.get("benchmark_profile") or "mature-oss-v1")

    section_scores: dict[str, float] = {}
    overall_score = 0.0
    for sec in form_sc.get("sections", []) or []:
        sid = str(sec.get("id"))
        qs = sec.get("questions", []) if isinstance(sec.get("questions", []), list) else []
        if not qs:
            section_scores[sid] = 0.0
            continue

        weighted_sum = 0.0
        weighted_count = 0.0
        for q in qs:
            rating_key = str(q.get("rating") or "").strip().lower()
            if rating_key == "nevztahuje se":
                rating_key = "nehodnoceno"
            category = _normalize_category(q.get("category"))
            cat_weight = category_weights.get(category, 1.0)
            weighted_sum += _rating_fraction(rating_key, rating_points) * cat_weight
            weighted_count += cat_weight

        avg = weighted_sum / weighted_count if weighted_count > 0 else 0.0
        section_scores[sid] = round(avg * 100.0, 2)
        if sid in section_weights:
            overall_score += section_weights[sid] * avg * 100.0
    overall_score = round(overall_score, 2)

    # Methodology-only: sections 6.1–6.5 (ids 1…5). No supply-chain gate.
    cutoff_pass = True
    cutoff_reasons: list[str] = []
    tolerated_section = None
    tolerated_used = False
    for sid in ("1", "2", "3", "4", "5-sec:api"):
        sec = next((s for s in form_sc.get("sections", []) if str(s.get("id")) == sid), None)
        if not sec:
            continue
        must = [
            q
            for q in sec.get("questions", [])
            if str(q.get("category", "")).lower().startswith("must")
        ]
        if not must:
            continue
        not_ok = [
            q
            for q in must
            if str(q.get("rating") or "").strip().lower() not in {"splňuje"}
        ]
        if not not_ok:
            continue
        if (
            len(not_ok) == 1
            and not_ok[0].get("rating") == "částečně splňuje"
            and not tolerated_used
            and _has_timeline(str(not_ok[0].get("note", "")))
        ):
            tolerated_used = True
            tolerated_section = sid
            continue
        cutoff_pass = False
        cutoff_reasons.append(f"Sekce {sid}: {len(not_ok)} 'must have' není ve stavu 'splňuje'.")

    cutoffs = scoring.get("cutoffs", {}) if isinstance(scoring.get("cutoffs"), dict) else {}
    grade_cfg = (
        cutoffs.get("scoring_grades", {}) if isinstance(cutoffs.get("scoring_grades"), dict) else {}
    )
    pass_min = _to_float(grade_cfg.get("pass_min"), 75.0)
    good_min = _to_float(grade_cfg.get("good"), 85.0)
    excellent_min = _to_float(grade_cfg.get("excellent"), 92.0)

    grade = "fail"
    if not cutoff_pass:
        grade = "cutoff-fail"
    elif overall_score >= excellent_min:
        grade = "excellent"
    elif overall_score >= good_min:
        grade = "good"
    elif overall_score >= pass_min:
        grade = "pass"

    return {
        "cutoffs": {
            "passed": cutoff_pass,
            "tolerated_section": tolerated_section,
            "reasons": cutoff_reasons,
        },
        "section_scores": section_scores,
        "overall_score": overall_score,
        "grade": grade,
        "calibration": {
            "profile": benchmark_profile,
            "rating_points": rating_points,
            "category_weights": category_weights,
            "reference_band": benchmark_band,
            "reference_position": _reference_position(overall_score, benchmark_band),
        },
    }
