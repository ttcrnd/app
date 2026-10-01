from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Evaluation, Library, LibraryVersion
from db.repos.common import library_name, safe_id
from db.repos.presenters import evaluation_to_list_item, status_label_cs

def get_or_create_library(session: Session, repo: str) -> Library:
    repo_key = (repo or "").strip() or "unknown/unknown"
    existing = session.scalar(select(Library).where(Library.repo == repo_key))
    if existing:
        return existing
    lib = Library(
        id=safe_id(repo_key.replace("/", "-")),
        repo=repo_key,
        name=library_name(repo_key),
    )
    # Ensure unique id if collision
    if session.get(Library, lib.id):
        lib.id = safe_id(f"{lib.id}-{uuid.uuid4().hex[:8]}")
    session.add(lib)
    session.flush()
    return lib


def get_or_create_library_version(
    session: Session, library: Library, ref: str, commit_sha: str = ""
) -> LibraryVersion:
    ref_key = (ref or "").strip() or "aktuální"
    existing = session.scalar(
        select(LibraryVersion).where(
            LibraryVersion.library_id == library.id,
            LibraryVersion.ref == ref_key,
        )
    )
    if existing:
        if commit_sha and not existing.commit_sha:
            existing.commit_sha = commit_sha
        return existing
    version = LibraryVersion(
        id=safe_id(f"{library.id}-{ref_key}")[:64],
        library_id=library.id,
        ref=ref_key,
        commit_sha=(commit_sha or "").strip(),
    )
    if session.get(LibraryVersion, version.id):
        version.id = safe_id(uuid.uuid4().hex)
    session.add(version)
    session.flush()
    return version


def _catalog_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    latest = item.get("latest_evaluation") or {}
    status = (latest.get("status") if latest else None) or "none"
    # Rozpracováno nahoře, pak Nedoporučeno, Hotovo, bez hodnocení
    order = {
        "in_progress": 0,
        "draft": 0,
        "not_recommended": 1,
        "completed": 2,
        "none": 3,
    }.get(status, 3)
    updated = latest.get("updated_at") if latest else item.get("updated_at") or ""
    # Negate ISO via reverse lexicographic pad so newer sorts first within group
    return (order, updated)


def list_libraries(
    session: Session,
    *,
    limit: int = 100,
    q: str = "",
    status: str = "all",
    viewer_mode: bool = False,
) -> list[dict[str, Any]]:
    libs = session.scalars(select(Library).order_by(Library.updated_at.desc()).limit(500)).all()
    needle = (q or "").strip().lower()
    status_filter = (status or "all").strip().lower()
    items: list[dict[str, Any]] = []
    for lib in libs:
        latest = session.scalar(
            select(Evaluation)
            .where(Evaluation.library_id == lib.id)
            .order_by(Evaluation.updated_at.desc())
            .limit(1)
        )
        latest_item = evaluation_to_list_item(latest) if latest else None
        catalog_status = latest_item["status"] if latest_item else "none"
        if viewer_mode and catalog_status not in {"completed", "not_recommended"}:
            continue
        if status_filter not in {"", "all", "none"}:
            if status_filter in {"in_progress", "draft", "rozpracovano"}:
                if catalog_status not in {"in_progress", "draft"}:
                    continue
            elif status_filter != catalog_status:
                continue
        elif status_filter == "none" and latest_item is not None:
            continue
        hay = f"{lib.name} {lib.repo} {lib.blurb}".lower()
        if needle and needle not in hay:
            continue
        items.append(
            {
                "id": lib.id,
                "repo": lib.repo,
                "name": lib.name or library_name(lib.repo),
                "blurb": lib.blurb,
                "catalog_status": catalog_status,
                "catalog_status_label": (
                    status_label_cs(catalog_status) if catalog_status != "none" else "Bez hodnocení"
                ),
                "latest_evaluation": latest_item,
                "updated_at": lib.updated_at.isoformat() if lib.updated_at else "",
            }
        )
    # Newest within status group first (stable: date desc, then status order)
    items.sort(
        key=lambda it: (it.get("latest_evaluation") or {}).get("updated_at")
        or it.get("updated_at")
        or "",
        reverse=True,
    )
    items.sort(key=lambda it: _catalog_sort_key(it)[0])
    return items[:limit]


def get_library_detail(session: Session, library_id: str) -> dict[str, Any] | None:
    lib = session.get(Library, library_id)
    if not lib:
        # allow lookup by repo
        lib = session.scalar(select(Library).where(Library.repo == library_id))
    if not lib:
        return None
    evaluations = session.scalars(
        select(Evaluation)
        .where(Evaluation.library_id == lib.id)
        .order_by(Evaluation.updated_at.desc())
    ).all()
    versions = session.scalars(
        select(LibraryVersion)
        .where(LibraryVersion.library_id == lib.id)
        .order_by(LibraryVersion.created_at.desc())
    ).all()
    latest = evaluations[0] if evaluations else None
    return {
        "id": lib.id,
        "repo": lib.repo,
        "name": lib.name or library_name(lib.repo),
        "blurb": lib.blurb,
        "catalog_status": latest.status if latest else "none",
        "catalog_status_label": status_label_cs(latest.status) if latest else "Bez hodnocení",
        "versions": [{"id": v.id, "ref": v.ref, "commit_sha": v.commit_sha} for v in versions],
        "evaluations": [evaluation_to_list_item(e) for e in evaluations],
    }


def delete_library(session: Session, library_id: str) -> dict[str, Any]:
    """Delete a library and cascade its evaluations, artifacts, events, and versions."""
    from db.repos.evaluations import delete_evaluation

    lib = session.get(Library, library_id)
    if not lib:
        lib = session.scalar(select(Library).where(Library.repo == library_id))
    if not lib:
        raise KeyError("Knihovna nenalezena")

    evaluations = session.scalars(
        select(Evaluation).where(Evaluation.library_id == lib.id)
    ).all()
    for evaluation in evaluations:
        delete_evaluation(session, evaluation.id)

    versions = session.scalars(
        select(LibraryVersion).where(LibraryVersion.library_id == lib.id)
    ).all()
    for version in versions:
        session.delete(version)

    deleted = {
        "id": lib.id,
        "repo": lib.repo,
        "name": lib.name or library_name(lib.repo),
        "evaluations_deleted": len(evaluations),
    }
    session.delete(lib)
    session.flush()
    return deleted


