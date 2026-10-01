from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from db.repository import add_audit, delete_library, get_library_detail, list_libraries
from review_app.deps import db_session, request_has_pilot_session, session_from_request
from review_app.paths import ROOT, TERMINAL_EVAL_STATUSES
from auth.pilot import (
    COOKIE_NAME as PILOT_COOKIE_NAME,
)
from auth.pilot import (
    parse_session_value,
    pilot_code_enabled,
    role_can_write,
    user_auth_enabled,
)

router = APIRouter(tags=["libraries"])

@router.get("/api/libraries")
async def api_list_libraries(request: Request) -> JSONResponse:
    q = str(request.query_params.get("q") or "").strip()
    status = str(request.query_params.get("status") or "all").strip()
    role = str(request.query_params.get("role") or "").strip().lower()
    viewer_mode = role == "viewer"
    public_catalog = False
    if pilot_code_enabled(ROOT) or user_auth_enabled(ROOT):
        session_info = parse_session_value(request.cookies.get(PILOT_COOKIE_NAME), ROOT)
        if not session_info:
            viewer_mode = True
            public_catalog = True
        elif str(getattr(session_info, "role", "") or "").lower() == "viewer":
            viewer_mode = True
    session = db_session()
    try:
        items = list_libraries(session, q=q, status=status, viewer_mode=viewer_mode)
        return JSONResponse(
            {
                "libraries": items,
                "q": q,
                "status": status,
                "viewer_mode": viewer_mode,
                "public_catalog": public_catalog,
            }
        )
    finally:
        session.close()


@router.get("/api/libraries/{library_id}")
async def api_get_library(library_id: str, request: Request) -> JSONResponse:
    public = pilot_code_enabled(ROOT) and not request_has_pilot_session(request)
    session = db_session()
    try:
        detail = get_library_detail(session, library_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Knihovna nenalezena")
        if public:
            evals = [
                e
                for e in (detail.get("evaluations") or [])
                if e.get("status") in TERMINAL_EVAL_STATUSES
            ]
            detail = {**detail, "evaluations": evals}
            if not evals:
                raise HTTPException(
                    status_code=401,
                    detail={
                        "code": "auth_required",
                        "message": "Tato knihovna ještě nemá veřejný výsledek. Zadej přístupový kód.",
                    },
                )
            detail["catalog_status"] = evals[0].get("status") or detail.get("catalog_status")
            detail["catalog_status_label"] = evals[0].get("status_label") or detail.get(
                "catalog_status_label"
            )
        return JSONResponse(detail)
    finally:
        session.close()


@router.delete("/api/libraries/{library_id}")
async def api_delete_library(library_id: str, request: Request) -> JSONResponse:
    sess = session_from_request(request)
    if sess and not role_can_write(sess.role):
        raise HTTPException(status_code=403, detail="Role viewer nemůže mazat knihovny")
    safe = "".join(ch for ch in library_id if ch.isalnum() or ch in {"-", "_", "/"})
    session = db_session()
    try:
        deleted = delete_library(session, safe)
        add_audit(
            session,
            event_type="library_deleted",
            message=f"Smazána knihovna {deleted.get('repo') or safe}",
            actor_user_id=sess.user_id if sess else None,
            payload=deleted,
        )
        session.commit()
        return JSONResponse({"ok": True, "deleted": deleted})
    except KeyError as e:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    finally:
        session.close()

