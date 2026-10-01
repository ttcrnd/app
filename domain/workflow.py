from __future__ import annotations

from typing import Any

RATING_NEUTRAL = "nehodnoceno"
RATING_MEETS = "splňuje"
RATING_PARTIAL = "částečně splňuje"
RATING_FAIL = "nesplňuje"
RATING_NA = "nevztahuje se"

RATING_VALUES = {
    RATING_NEUTRAL,
    RATING_MEETS,
    RATING_PARTIAL,
    RATING_FAIL,
}

# Legacy alias — folded into RATING_NEUTRAL („Nehodnoceno“ covers pending + not-applicable).
RATING_VALUES_LEGACY = RATING_VALUES | {RATING_NA}

REVIEW_STATE_AUTO = "AUTO"
REVIEW_STATE_CONFIRM = "CONFIRM"
REVIEW_STATE_MANUAL = "MANUAL"

REVIEW_STATE_VALUES = {
    REVIEW_STATE_AUTO,
    REVIEW_STATE_CONFIRM,
    REVIEW_STATE_MANUAL,
}

# Must never become AUTO from pipeline heuristics (metodika / false confidence).
FORCE_CONFIRM_IDS = frozenset(
    {
        "1-2",
        "1-3",
        "2-2",
        "2-9",
        "2-16",
        "2-17",
        "4-2",
        "4-3",
    }
)

FORCE_MANUAL_IDS = frozenset()


def normalize_rating(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == RATING_NA:
        return RATING_NEUTRAL
    if normalized in RATING_VALUES:
        return normalized
    return RATING_NEUTRAL


def normalize_form_workflow(
    form_obj: dict[str, Any],
    *,
    pipeline_mode: bool,
) -> dict[str, Any]:
    if not isinstance(form_obj, dict):
        return form_obj

    source_options = form_obj.get("rating_options")
    options = []
    if isinstance(source_options, list):
        for option in source_options:
            normalized = normalize_rating(option)
            if normalized not in options:
                options.append(normalized)
    if not options:
        options = [RATING_NEUTRAL, RATING_MEETS, RATING_PARTIAL, RATING_FAIL]
    if RATING_NEUTRAL not in options:
        options.insert(0, RATING_NEUTRAL)
    # Drop legacy N/A option from the form chrome.
    options = [opt for opt in options if opt != RATING_NA]
    form_obj["rating_options"] = options

    sections = form_obj.get("sections")
    if not isinstance(sections, list):
        return form_obj

    for section in sections:
        if not isinstance(section, dict):
            continue
        questions = section.get("questions")
        if not isinstance(questions, list):
            continue
        for question in questions:
            if not isinstance(question, dict):
                continue
            _normalize_question_workflow(question, pipeline_mode=pipeline_mode)
    return form_obj


def _normalize_question_workflow(question: dict[str, Any], *, pipeline_mode: bool) -> None:
    rating = normalize_rating(question.get("rating"))
    suggested = normalize_rating(question.get("auto_suggested_rating"))
    explicit_state = str(question.get("review_state") or "").strip().upper()
    qid = str(question.get("id") or "").strip()

    if qid in FORCE_MANUAL_IDS:
        review_state = REVIEW_STATE_MANUAL
    elif qid in FORCE_CONFIRM_IDS:
        review_state = REVIEW_STATE_CONFIRM
    elif explicit_state in REVIEW_STATE_VALUES:
        review_state = explicit_state
    else:
        heuristic = bool(question.get("heuristic_rating"))
        if not heuristic:
            review_state = REVIEW_STATE_MANUAL
        elif rating == RATING_MEETS:
            review_state = REVIEW_STATE_AUTO
        else:
            review_state = REVIEW_STATE_CONFIRM

    has_checked = "checked" in question
    checked = bool(question.get("checked")) if has_checked else False
    checked_source = str(question.get("checked_source") or "").strip().lower()

    if review_state == REVIEW_STATE_AUTO:
        if rating == RATING_NEUTRAL:
            rating = RATING_MEETS
        checked = True
        checked_source = "auto"
        requires_confirmation = False
    elif review_state == REVIEW_STATE_CONFIRM:
        if suggested == RATING_NEUTRAL and rating != RATING_NEUTRAL:
            suggested = rating
        if pipeline_mode:
            # Pipeline output is pending until a human confirms it.
            checked = False
            checked_source = ""
        else:
            if rating != RATING_NEUTRAL and (checked or not has_checked):
                checked = True
                checked_source = "manual"
            elif not checked:
                checked_source = ""
        requires_confirmation = not checked
    else:
        if suggested == RATING_NEUTRAL and rating != RATING_NEUTRAL:
            suggested = rating
        if pipeline_mode:
            # Manual questions must start unresolved after pipeline.
            rating = RATING_NEUTRAL
            checked = False
            checked_source = ""
        else:
            if rating != RATING_NEUTRAL and (checked or not has_checked):
                checked = True
                checked_source = "manual"
            elif not checked:
                checked_source = ""
        requires_confirmation = not checked

    question["rating"] = rating
    question["review_state"] = review_state
    question["requires_confirmation"] = requires_confirmation
    question["checked"] = bool(checked)
    question["checked_source"] = checked_source
    if suggested != RATING_NEUTRAL:
        question["auto_suggested_rating"] = suggested
