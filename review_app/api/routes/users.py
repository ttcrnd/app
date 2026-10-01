from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from db.repository import create_user, delete_user, list_users, update_user, user_to_dict
from review_app.deps import db_session, session_from_request
from auth.pilot import role_can_manage_users

router = APIRouter(tags=["users"])

@router.get("/api/users")
async def api_list_users(request: Request) -> JSONResponse:
    sess = session_from_request(request)
    if not sess or not role_can_manage_users(sess.role):
        raise HTTPException(status_code=403, detail="Jen admin spravuje uživatele")
    session = db_session()
    try:
        return JSONResponse({"users": list_users(session)})
    finally:
        session.close()


@router.post("/api/users")
async def api_create_user(request: Request, payload: dict) -> JSONResponse:
    sess = session_from_request(request)
    if not sess or not role_can_manage_users(sess.role):
        raise HTTPException(status_code=403, detail="Jen admin spravuje uživatele")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")
    session = db_session()
    try:
        user = create_user(
            session,
            username=str(payload.get("username") or ""),
            password=str(payload.get("password") or ""),
            role=str(payload.get("role") or "reviewer"),
            display_name=str(payload.get("display_name") or ""),
            actor_user_id=sess.user_id,
        )
        session.commit()
        return JSONResponse(user_to_dict(user))
    except ValueError as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        session.close()


@router.patch("/api/users/{user_id}")
async def api_patch_user(user_id: str, request: Request, payload: dict) -> JSONResponse:
    sess = session_from_request(request)
    if not sess or not role_can_manage_users(sess.role):
        raise HTTPException(status_code=403, detail="Jen admin spravuje uživatele")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")
    session = db_session()
    try:
        user = update_user(
            session,
            user_id,
            role=str(payload["role"]) if "role" in payload else None,
            password=str(payload["password"]) if payload.get("password") else None,
            display_name=str(payload["display_name"]) if "display_name" in payload else None,
            actor_user_id=sess.user_id,
        )
        session.commit()
        return JSONResponse(user_to_dict(user))
    except KeyError as e:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        session.close()


@router.delete("/api/users/{user_id}")
async def api_delete_user(user_id: str, request: Request) -> JSONResponse:
    sess = session_from_request(request)
    if not sess or not role_can_manage_users(sess.role):
        raise HTTPException(status_code=403, detail="Jen admin spravuje uživatele")
    session = db_session()
    try:
        delete_user(session, user_id, actor_user_id=sess.user_id)
        session.commit()
        return JSONResponse({"ok": True, "deleted": user_id})
    except KeyError as e:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        session.close()

