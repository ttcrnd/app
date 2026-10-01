from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Artifact, Evaluation, EvaluationEvent, utcnow
from db.repos import common
from db.repos.audit import ensure_pilot_user
from db.repos.common import ROOT, parse_iso, safe_id
from db.repos.libraries import get_or_create_library, get_or_create_library_version
from db.repos.presenters import evaluation_to_list_item, status_label_cs

def delete_evaluation(session: Session, evaluation_id: str) -> None:
    evaluation = session.get(Evaluation, evaluation_id)
    if not evaluation:
        raise KeyError("Hodnocení nenalezeno")
    for art in list(evaluation.artifacts or []):
        session.delete(art)
    for ev in list(evaluation.events or []):
        session.delete(ev)
    session.delete(evaluation)
    session.flush()


def build_evaluation_title(form_obj: dict[str, Any], fallback: str = "") -> str:
    meta = form_obj.get("meta") if isinstance(form_obj.get("meta"), dict) else {}
    repo = str(meta.get("repo") or "").strip() or "hodnocení"
    ref = str(
        meta.get("evaluated_repo_version")
        or meta.get("effective_ref")
        or meta.get("requested_ref")
        or meta.get("default_branch")
        or "aktuální"
    ).strip()
    date_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    explicit = str(form_obj.get("_evaluation_title") or meta.get("title") or fallback or "").strip()
    if explicit and " @ " in explicit:
        head = explicit.split(" · ")[0].strip()
        return f"{head} · {date_stamp}"
    return f"{repo} @ {ref} · {date_stamp}"


def extract_form_identity(form_obj: dict[str, Any]) -> tuple[str, str, str]:
    meta = form_obj.get("meta") if isinstance(form_obj.get("meta"), dict) else {}
    repo = str(meta.get("repo") or "").strip()
    ref = str(
        meta.get("evaluated_repo_version")
        or meta.get("effective_ref")
        or meta.get("requested_ref")
        or meta.get("default_branch")
        or ""
    ).strip()
    sha = str(meta.get("commit_sha") or meta.get("sha") or "").strip()
    if not sha and re.fullmatch(r"[0-9a-fA-F]{7,40}", ref or ""):
        sha = ref.lower()
    return repo, ref, sha


def add_event(
    session: Session,
    evaluation_id: str,
    event_type: str,
    message: str = "",
    payload: dict[str, Any] | None = None,
) -> EvaluationEvent:
    event = EvaluationEvent(
        id=uuid.uuid4().hex,
        evaluation_id=evaluation_id,
        event_type=event_type,
        message=message,
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
    )
    session.add(event)
    return event


def upsert_form_artifact(
    session: Session, evaluation: Evaluation, form_obj: dict[str, Any]
) -> Artifact:
    common.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    eval_dir = common.ARTIFACTS_DIR / evaluation.id
    eval_dir.mkdir(parents=True, exist_ok=True)
    path = eval_dir / "form.json"
    path.write_text(json.dumps(form_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        rel = str(path.relative_to(ROOT))
    except ValueError:
        rel = str(path)

    existing = session.scalar(
        select(Artifact).where(
            Artifact.evaluation_id == evaluation.id,
            Artifact.kind == "form",
        )
    )
    if existing:
        existing.path = rel
        existing.content_type = "application/json"
        return existing
    artifact = Artifact(
        id=uuid.uuid4().hex,
        evaluation_id=evaluation.id,
        kind="form",
        path=rel,
        content_type="application/json",
    )
    session.add(artifact)
    return artifact

def complete_evaluation(
    session: Session,
    *,
    evaluation_id: str,
    outcome: str,
    note: str,
) -> Evaluation:
    outcome_key = (outcome or "").strip().lower()
    if outcome_key in {"hotovo", "done", "complete"}:
        outcome_key = "completed"
    if outcome_key in {"nedoporučeno", "nedoporuceno", "reject"}:
        outcome_key = "not_recommended"
    if outcome_key not in {"completed", "not_recommended"}:
        raise ValueError("outcome musí být completed nebo not_recommended")
    note_clean = (note or "").strip()
    if len(note_clean) < 3:
        raise ValueError("Poznámka je povinná (alespoň pár slov).")

    evaluation = session.get(Evaluation, evaluation_id)
    if not evaluation:
        raise KeyError("Hodnocení nenalezeno")

    try:
        form_obj = json.loads(evaluation.form_json or "{}")
    except Exception:
        form_obj = {}
    if not isinstance(form_obj, dict):
        form_obj = {}
    if not isinstance(form_obj.get("meta"), dict):
        form_obj["meta"] = {}
    form_obj["meta"]["completion_status"] = outcome_key
    form_obj["meta"]["completion_note"] = note_clean
    form_obj["meta"]["completion_label"] = status_label_cs(outcome_key)

    now = utcnow()
    evaluation.status = outcome_key
    evaluation.completed_at = now
    evaluation.updated_at = now
    evaluation.form_json = json.dumps(form_obj, ensure_ascii=False)
    upsert_form_artifact(session, evaluation, form_obj)
    add_event(
        session,
        evaluation.id,
        "evaluation_completed",
        message=note_clean,
        payload={"outcome": outcome_key},
    )
    session.flush()
    return evaluation


def sign_evaluation(session: Session, *, evaluation_id: str) -> dict[str, Any]:
    """Create Ed25519 signed export for a terminal evaluation. Never deletes the evaluation."""
    from services.signing import sign_payload

    evaluation = session.get(Evaluation, evaluation_id)
    if not evaluation:
        raise KeyError("Hodnocení nenalezeno")
    if evaluation.status not in {"completed", "not_recommended"}:
        raise ValueError("Podpis je jen pro Hotovo / Nedoporučeno.")

    try:
        form_obj = json.loads(evaluation.form_json or "{}")
    except Exception:
        form_obj = {}
    if not isinstance(form_obj, dict):
        form_obj = {}
    if not isinstance(form_obj.get("meta"), dict):
        form_obj["meta"] = {}

    # Preserve human approval text (Schválil) alongside crypto.
    note = str(form_obj["meta"].get("completion_note") or "").strip()
    if note and not form_obj["meta"].get("approved_label"):
        form_obj["meta"]["approved_label"] = f"Schválil: {note}"

    form_for_sign = json.loads(json.dumps(form_obj))
    if isinstance(form_for_sign.get("meta"), dict):
        form_for_sign["meta"].pop("signature", None)
        form_for_sign["meta"].pop("signed", None)

    wrapper = sign_payload(form_for_sign)
    sig = wrapper["sig"]
    form_obj["meta"]["signature"] = sig
    form_obj["meta"]["signed"] = True
    evaluation.form_json = json.dumps(form_obj, ensure_ascii=False)
    evaluation.updated_at = utcnow()
    upsert_form_artifact(session, evaluation, form_obj)

    common.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    eval_dir = common.ARTIFACTS_DIR / evaluation.id
    eval_dir.mkdir(parents=True, exist_ok=True)
    signed_path = eval_dir / "signed_export.json"
    signed_path.write_text(
        json.dumps(wrapper, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        rel = str(signed_path.relative_to(ROOT))
    except ValueError:
        rel = str(signed_path)

    existing = session.scalar(
        select(Artifact).where(
            Artifact.evaluation_id == evaluation.id,
            Artifact.kind == "signed_export",
        )
    )
    if existing:
        existing.path = rel
        existing.content_type = "application/json"
    else:
        session.add(
            Artifact(
                id=uuid.uuid4().hex,
                evaluation_id=evaluation.id,
                kind="signed_export",
                path=rel,
                content_type="application/json",
            )
        )

    add_event(
        session,
        evaluation.id,
        "evaluation_signed",
        message=sig.get("key_id") or "ed25519",
        payload={
            "alg": sig.get("alg"),
            "key_id": sig.get("key_id"),
            "signed_at": sig.get("signed_at"),
        },
    )
    session.flush()
    return {
        "id": evaluation.id,
        "signed": True,
        "sig": sig,
        "path": rel,
        "wrapper": wrapper,
    }

def list_pilot_empirie(session: Session) -> dict[str, Any]:
    """Empirie summary for completed/not_recommended pilot evaluations."""
    from services.empirie import analyze_form_empirie, summarize_empirie_rows

    rows_out: list[dict[str, Any]] = []
    evaluations = session.scalars(
        select(Evaluation)
        .where(Evaluation.status.in_(("completed", "not_recommended")))
        .order_by(Evaluation.updated_at.desc())
    ).all()
    for evaluation in evaluations:
        try:
            form_obj = json.loads(evaluation.form_json or "{}")
        except Exception:
            continue
        if not isinstance(form_obj, dict):
            continue
        stats = analyze_form_empirie(form_obj)
        rows_out.append(
            {
                "evaluation_id": evaluation.id,
                "repo": evaluation.repo,
                "ref": evaluation.ref,
                "status": evaluation.status,
                "status_label": status_label_cs(evaluation.status or ""),
                "title": evaluation.title,
                **stats,
            }
        )
    summary = summarize_empirie_rows(rows_out)
    summary["d10"] = {
        "libraries_required": 3,
        "not_recommended_required": 1,
        "libraries_with_terminal_status": len({r["repo"] for r in rows_out if r.get("repo")}),
        "not_recommended_count": sum(1 for r in rows_out if r.get("status") == "not_recommended"),
    }
    return summary


def find_previous_terminal_form(
    session: Session,
    *,
    evaluation_id: str,
    library_id: str | None,
) -> tuple[str | None, dict[str, Any] | None]:
    """Return (prev_id, prev_form) for the same library, excluding current evaluation."""
    if not library_id:
        return None, None
    rows = session.scalars(
        select(Evaluation)
        .where(
            Evaluation.library_id == library_id,
            Evaluation.id != evaluation_id,
            Evaluation.status.in_(("completed", "not_recommended")),
        )
        .order_by(Evaluation.completed_at.desc(), Evaluation.updated_at.desc())
        .limit(1)
    ).all()
    if not rows:
        return None, None
    prev = rows[0]
    try:
        form_obj = json.loads(prev.form_json or "{}")
    except Exception:
        form_obj = {}
    if not isinstance(form_obj, dict):
        return prev.id, None
    return prev.id, form_obj


def rating_diff_against_previous(
    session: Session,
    *,
    evaluation_id: str,
) -> dict[str, Any]:
    from domain.meta_enrichment import diff_form_ratings

    evaluation = session.get(Evaluation, evaluation_id)
    if not evaluation:
        raise KeyError("Hodnocení nenalezeno")
    try:
        current = json.loads(evaluation.form_json or "{}")
    except Exception:
        current = {}
    if not isinstance(current, dict):
        current = {}
    prev_id, previous = find_previous_terminal_form(
        session,
        evaluation_id=evaluation.id,
        library_id=evaluation.library_id,
    )
    if not previous:
        return {
            "previous_id": prev_id,
            "changes": [],
            "has_previous": False,
        }
    return {
        "previous_id": prev_id,
        "has_previous": True,
        "changes": diff_form_ratings(current, previous)[:40],
    }


def list_evaluations(
    session: Session,
    *,
    limit: int = 50,
    owner_user_id: str | None = None,
    include_all: bool = False,
) -> list[dict[str, Any]]:
    stmt = select(Evaluation).order_by(Evaluation.updated_at.desc())
    # D11: reviewer vidí jen vlastní; admin include_all; completed lze veřejně jinde.
    if not include_all and owner_user_id:
        stmt = stmt.where(Evaluation.owner_user_id == owner_user_id)
    rows = session.scalars(stmt.limit(limit)).all()
    return [evaluation_to_list_item(row) for row in rows]


def get_evaluation(session: Session, evaluation_id: str) -> Evaluation | None:
    return session.get(Evaluation, evaluation_id)


def can_edit_evaluation(
    evaluation: Evaluation,
    *,
    user_id: str | None,
    role: str | None,
) -> bool:
    from auth.pilot import role_can_access_all_evaluations, role_can_write

    if not role_can_write(role):
        return False
    if role_can_access_all_evaluations(role):
        return True
    owner = evaluation.owner_user_id or "pilot"
    return bool(user_id) and owner == user_id


def save_evaluation(
    session: Session,
    *,
    evaluation_id: str | None,
    form_obj: dict[str, Any],
    title_fallback: str = "",
    owner_user_id: str | None = None,
) -> tuple[Evaluation, dict[str, Any]]:
    ensure_pilot_user(session)
    safe = safe_id(evaluation_id)
    title = build_evaluation_title(form_obj, fallback=title_fallback)
    repo, ref, sha = extract_form_identity(form_obj)
    owner = (owner_user_id or "pilot").strip() or "pilot"

    form_copy = json.loads(json.dumps(form_obj))
    if not isinstance(form_copy.get("meta"), dict):
        form_copy["meta"] = {}
    try:
        from domain.meta_enrichment import enrich_form_meta

        enrich_form_meta(form_copy)
    except Exception:
        pass
    form_copy["meta"]["title"] = title
    form_copy["meta"]["evaluation_id"] = safe
    form_copy["meta"]["owner_user_id"] = owner
    form_copy["_draft_id"] = safe
    form_copy["_evaluation_id"] = safe
    form_copy["_evaluation_title"] = title
    now = utcnow()
    now_iso = now.isoformat()
    form_copy["_draft_updated_at"] = now_iso
    form_copy["_evaluation_updated_at"] = now_iso

    library = get_or_create_library(session, repo) if repo else None
    version = (
        get_or_create_library_version(session, library, ref, commit_sha=sha) if library else None
    )

    evaluation = session.get(Evaluation, safe)
    created = evaluation is None
    if created:
        evaluation = Evaluation(id=safe)
        session.add(evaluation)

    assert evaluation is not None
    evaluation.title = title
    evaluation.repo = repo
    evaluation.ref = ref
    evaluation.library_id = library.id if library else None
    evaluation.library_version_id = version.id if version else None
    if created or not evaluation.owner_user_id:
        evaluation.owner_user_id = owner
    evaluation.form_json = json.dumps(form_copy, ensure_ascii=False)
    evaluation.updated_at = now
    if not evaluation.started_at:
        started = parse_iso(str(form_copy.get("meta", {}).get("started_at") or ""))
        evaluation.started_at = started or now
    if evaluation.status in {"", "draft"} and form_copy.get("sections"):
        evaluation.status = "in_progress"

    artifact = upsert_form_artifact(session, evaluation, form_copy)
    add_event(
        session,
        evaluation.id,
        "evaluation_created" if created else "evaluation_saved",
        message=title,
        payload={"repo": repo, "ref": ref, "owner_user_id": evaluation.owner_user_id},
    )
    session.flush()

    return evaluation, {
        "id": evaluation.id,
        "title": title,
        "library": repo,
        "ref": ref,
        "status": evaluation.status,
        "status_label": status_label_cs(evaluation.status or "draft"),
        "owner_user_id": evaluation.owner_user_id,
        "path": artifact.path,
        "updated_at": now_iso,
    }


def migrate_file_drafts(session: Session, drafts_dir: Path) -> int:
    """Import legacy out/drafts/*.json into DB once."""
    if not drafts_dir.exists():
        return 0
    imported = 0
    for path in sorted(drafts_dir.glob("*.json")):
        eval_id = path.stem
        if session.get(Evaluation, eval_id):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        save_evaluation(session, evaluation_id=eval_id, form_obj=data)
        imported += 1
    return imported

