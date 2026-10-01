"""Empirie jistoty z pilotních hodnocení (krok 9 / A5)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def iter_questions(form_obj: dict[str, Any]):
    for section in form_obj.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for question in section.get("questions") or []:
            if isinstance(question, dict):
                yield question


def analyze_form_empirie(form_obj: dict[str, Any]) -> dict[str, Any]:
    """Classify AUTO accept vs CONFIRM/MANUAL overrides for one evaluation form."""
    counts: Counter[str] = Counter()
    accepted: list[str] = []
    confirmed: list[str] = []
    manual: list[str] = []
    must_false_positive_risk: list[str] = []

    for question in iter_questions(form_obj):
        qid = str(question.get("id") or "")
        wf = str(question.get("review_state") or "MANUAL").upper()
        rating = str(question.get("rating") or "")
        category = str(question.get("category") or "").lower()
        heuristic = bool(question.get("heuristic_rating"))
        counts["questions"] += 1
        counts[wf] += 1

        if heuristic and wf == "AUTO":
            counts["accepted_auto"] += 1
            accepted.append(qid)
        elif heuristic and wf == "CONFIRM":
            counts["confirm_after_heuristic"] += 1
            confirmed.append(qid)
        elif heuristic:
            counts["overridden_or_manual_heuristic"] += 1
            manual.append(qid)
        else:
            counts["pure_manual"] += 1
            manual.append(qid)

        if heuristic and "must" in category and wf == "AUTO" and rating not in {"splňuje", "pass"}:
            must_false_positive_risk.append(qid)

    total_heuristic = (
        counts["accepted_auto"]
        + counts["confirm_after_heuristic"]
        + counts["overridden_or_manual_heuristic"]
    )
    accept_rate = (
        round(100.0 * counts["accepted_auto"] / total_heuristic, 1) if total_heuristic else 0.0
    )
    return {
        "questions": counts["questions"],
        "workflow": {
            "AUTO": counts["AUTO"],
            "CONFIRM": counts["CONFIRM"],
            "MANUAL": counts["MANUAL"],
        },
        "accepted_auto": counts["accepted_auto"],
        "confirm_after_heuristic": counts["confirm_after_heuristic"],
        "pure_manual": counts["pure_manual"],
        "heuristic_accept_rate_pct": accept_rate,
        "accepted_ids_sample": accepted[:12],
        "confirm_ids_sample": confirmed[:12],
        "must_auto_non_pass_ids": must_false_positive_risk,
    }


def load_form_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Neplatný formulář JSON: {path}")
    return data


def summarize_empirie_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-evaluation empirie into pilot summary."""
    total_q = sum(int(r.get("questions") or 0) for r in rows)
    accepted = sum(int(r.get("accepted_auto") or 0) for r in rows)
    confirm = sum(int(r.get("confirm_after_heuristic") or 0) for r in rows)
    manual = sum(int(r.get("pure_manual") or 0) for r in rows)
    heuristic = accepted + confirm
    return {
        "evaluations": len(rows),
        "questions_total": total_q,
        "accepted_auto_total": accepted,
        "confirm_after_heuristic_total": confirm,
        "pure_manual_total": manual,
        "heuristic_accept_rate_pct": round(100.0 * accepted / heuristic, 1) if heuristic else 0.0,
        "rows": rows,
    }
