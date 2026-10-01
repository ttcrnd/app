from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Evaluation, Library
from db.repos.common import ROOT
from db.repos.evaluations import complete_evaluation, save_evaluation
from db.repos.libraries import get_or_create_library, get_or_create_library_version

def seed_pilot_libraries(session: Session) -> int:
    """Insert starter libraries from seed_data if catalog is empty of those repos."""
    from db.seed_data import PILOT_LIBRARIES

    created = 0
    for item in PILOT_LIBRARIES:
        repo = item["repo"]
        existing = session.scalar(select(Library).where(Library.repo == repo))
        if existing:
            if item.get("blurb") and not existing.blurb:
                existing.blurb = item["blurb"]
            if item.get("name") and not existing.name:
                existing.name = item["name"]
            continue
        lib = get_or_create_library(session, repo)
        lib.name = item.get("name") or lib.name
        lib.blurb = item.get("blurb") or ""
        ref = item.get("ref") or ""
        if ref:
            get_or_create_library_version(session, lib, ref)
        created += 1
    session.flush()
    return created


def minimal_reject_form(repo: str, ref: str) -> dict[str, Any]:
    """Skeleton form for Nedoporučeno without full pipeline run."""
    return {
        "title": "Formulář v1.0: Hodnocení open-source knihovny (dle metodiky)",
        "version": "2.0",
        "language": "cs",
        "meta": {
            "repo": repo,
            "requested_ref": ref,
            "effective_ref": ref,
            "evaluated_repo_version": ref,
            "pilot_seed": True,
            "pilot_outcome": "not_recommended",
        },
        "sections": [
            {
                "id": 1,
                "title": "Předpoklady",
                "questions": [
                    {
                        "id": "1-1",
                        "text": "Pilotní zkratka — knihovna označena jako nedoporučená v katalogu.",
                        "rating": "nesplňuje",
                        "note": "D10 kandidát na odmítnutí / náhradu vůči OpenSSL.",
                        "category": "must have",
                        "description": "",
                        "evidence": [],
                        "heuristic": "",
                        "review_state": "MANUAL",
                        "heuristic_rating": False,
                    }
                ],
            }
        ],
    }


def synthetic_complete_form(repo: str, ref: str) -> dict[str, Any]:
    """Full template-based form for pilot seed when example JSON files are absent."""
    template_path = ROOT / "assets" / "questions.json"
    if not template_path.exists():
        template_path = ROOT / "questions.json"
    form_obj = json.loads(template_path.read_text(encoding="utf-8"))
    if not isinstance(form_obj, dict):
        raise ValueError("questions.json is not an object")

    auto_budget = 12
    confirm_budget = 25
    for section in form_obj.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for question in section.get("questions") or []:
            if not isinstance(question, dict):
                continue
            heuristic = bool(question.get("heuristic_rating"))
            question["rating"] = "splňuje"
            question["note"] = question.get("note") or "Pilotní seed (syntetický formulář)."
            question["evidence"] = question.get("evidence") or []
            question["checked"] = True
            question["checked_source"] = "auto" if heuristic else "manual"
            if heuristic and auto_budget > 0:
                question["review_state"] = "AUTO"
                auto_budget -= 1
            elif heuristic and confirm_budget > 0:
                question["review_state"] = "CONFIRM"
                confirm_budget -= 1
            else:
                question["review_state"] = "MANUAL"
                question["checked_source"] = "manual"

    meta = form_obj.get("meta") if isinstance(form_obj.get("meta"), dict) else {}
    meta.update(
        {
            "repo": repo,
            "requested_ref": ref,
            "effective_ref": ref,
            "evaluated_repo_version": ref,
            "pilot_seed": True,
            "pilot_outcome": "completed",
            "synthetic_seed": True,
        }
    )
    form_obj["meta"] = meta
    return form_obj


def seed_pilot_evaluations(session: Session, *, examples_dir: Path | None = None) -> int:
    """
    Seed ≥3 pilot evaluations (incl. ≥1 Nedoporučeno) via the same save/complete path as UI.
    Idempotent: skips when evaluation id already exists.
    """
    from db.seed_data import PILOT_EVALUATIONS

    examples = examples_dir or (ROOT / "assets" / "example")
    if not examples.exists():
        examples = ROOT / "example"  # legacy layout
    created = 0
    for item in PILOT_EVALUATIONS:
        eval_id = item["id"]
        if session.get(Evaluation, eval_id):
            continue
        example_name = (item.get("example") or "").strip()
        form_obj: dict[str, Any] | None = None
        if example_name:
            path = examples / example_name
            if path.exists():
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    form_obj = loaded
        if form_obj is None:
            if item.get("outcome") == "not_recommended":
                form_obj = minimal_reject_form(item["repo"], item["ref"])
            else:
                form_obj = synthetic_complete_form(item["repo"], item["ref"])

        if not isinstance(form_obj.get("meta"), dict):
            form_obj["meta"] = {}
        form_obj["meta"]["repo"] = item["repo"]
        form_obj["meta"]["requested_ref"] = item["ref"]
        form_obj["meta"]["effective_ref"] = item["ref"]
        form_obj["meta"]["evaluated_repo_version"] = item["ref"]
        form_obj["meta"]["pilot_seed"] = True
        form_obj["meta"]["pilot_d10"] = True

        save_evaluation(
            session,
            evaluation_id=eval_id,
            form_obj=form_obj,
            title_fallback=f"{item['repo']} @ {item['ref']}",
        )
        complete_evaluation(
            session,
            evaluation_id=eval_id,
            outcome=item["outcome"],
            note=item["note"],
        )
        created += 1
    session.flush()
    return created

