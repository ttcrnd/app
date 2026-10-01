from __future__ import annotations

from typing import Any

OFFICIAL_RATING_VALUES = {"splňuje", "částečně splňuje", "nesplňuje"}


def is_appendix_section(section: dict[str, Any]) -> bool:
    stype = str(section.get("type") or "").strip().lower()
    return stype in {"appendix", "informational", "info"}


def iter_official_questions(form_obj: dict[str, Any]):
    sections = form_obj.get("sections") if isinstance(form_obj.get("sections"), list) else []
    for section in sections:
        if not isinstance(section, dict) or is_appendix_section(section):
            continue
        questions = section.get("questions") if isinstance(section.get("questions"), list) else []
        for question in questions:
            if isinstance(question, dict):
                yield section, question


def find_unevaluated_official_questions(form_obj: dict[str, Any]) -> list[dict[str, str]]:
    """Return official (v1.0) questions that are still nehodnoceno / empty (D5)."""
    missing: list[dict[str, str]] = []
    for section, question in iter_official_questions(form_obj):
        rating = str(question.get("rating") or "").strip().lower()
        if rating in OFFICIAL_RATING_VALUES:
            continue
        missing.append(
            {
                "section_id": str(section.get("id") or ""),
                "section_title": str(section.get("title") or ""),
                "question_id": str(question.get("id") or ""),
                "rating": rating or "nehodnoceno",
            }
        )
    return missing


def validate_official_export(form_obj: dict[str, Any]) -> dict[str, Any]:
    missing = find_unevaluated_official_questions(form_obj)
    return {
        "ok": len(missing) == 0,
        "missing_count": len(missing),
        "missing": missing,
        "message": (
            "Oficiální export je připraven."
            if not missing
            else (
                f"Oficiální export blokován (D5): {len(missing)} otázek oficiálního formuláře "
                "je stále 'nehodnoceno'. Doplň hodnocení nebo použij koncept (draft)."
            )
        ),
    }
