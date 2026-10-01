from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from db.repository import add_audit, authenticate_user, ensure_pilot_user
from review_app.deps import db_session, set_auth_cookie
from review_app.paths import ROOT
from auth.pilot import (
    COOKIE_NAME as PILOT_COOKIE_NAME,
)
from auth.pilot import (
    PILOT_DEFAULT_ROLE,
    PILOT_USER_ID,
    issue_session_value,
    pilot_code_enabled,
    user_auth_enabled,
    verify_access_code,
)
from auth.pilot import (
    auth_status as pilot_auth_status,
)

router = APIRouter(tags=["auth"])

@router.get("/api/auth/status")
async def api_auth_status(request: Request) -> JSONResponse:
    return JSONResponse(pilot_auth_status(ROOT, request.cookies.get(PILOT_COOKIE_NAME)))


@router.post("/api/auth/enter")
async def api_auth_enter(payload: dict) -> Response:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not pilot_code_enabled(ROOT):
        if user_auth_enabled(ROOT):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "use_password_login",
                    "message": "Přístupový kód je vypnutý — přihlas se jménem a heslem.",
                },
            )
        return JSONResponse(
            {
                "ok": True,
                "authenticated": True,
                "role": PILOT_DEFAULT_ROLE,
                "open_mode": True,
                "message": "Přístupový kód není vyžadován (otevřený režim).",
            }
        )
    code = str(payload.get("code") or "")
    if not verify_access_code(code, ROOT):
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_code", "message": "Neplatný přístupový kód."},
        )
    # Bootstrap: shared code → reviewer; with USER_AUTH on → emergency admin.
    role = "admin" if user_auth_enabled(ROOT) else PILOT_DEFAULT_ROLE
    token = issue_session_value(
        role=role,
        root=ROOT,
        user_id=PILOT_USER_ID,
        username="pilot",
        auth_method="code",
    )
    session = db_session()
    try:
        ensure_pilot_user(session)
        add_audit(
            session,
            event_type="login",
            message="Vstup přístupovým kódem",
            actor_user_id=PILOT_USER_ID,
            payload={"method": "code", "role": role},
        )
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()
    response = JSONResponse(
        {
            "ok": True,
            "authenticated": True,
            "role": role,
            "user_id": PILOT_USER_ID,
            "username": "pilot",
            "open_mode": False,
            "message": "Vstup povolen.",
        }
    )
    set_auth_cookie(response, token)
    return response


@router.post("/api/auth/login")
async def api_auth_login(payload: dict) -> Response:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not user_auth_enabled(ROOT) and not pilot_code_enabled(ROOT):
        # Allow login even in open mode if accounts exist / for tests when USER_AUTH on
        pass
    if not user_auth_enabled(ROOT):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "user_auth_disabled",
                "message": "Přihlášení heslem je vypnuté (USER_AUTH_ENABLED=false).",
            },
        )
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    session = db_session()
    try:
        user = authenticate_user(session, username, password)
        if not user:
            add_audit(
                session,
                event_type="login_failed",
                message=f"Neúspěšné přihlášení: {username}",
                payload={"username": username},
            )
            session.commit()
            raise HTTPException(
                status_code=401,
                detail={"code": "invalid_credentials", "message": "Neplatné jméno nebo heslo."},
            )
        add_audit(
            session,
            event_type="login",
            message=f"Přihlášení {user.username}",
            actor_user_id=user.id,
            payload={"method": "password", "role": user.role},
        )
        session.commit()
        token = issue_session_value(
            role=user.role,
            root=ROOT,
            user_id=user.id,
            username=user.username,
            auth_method="password",
        )
        response = JSONResponse(
            {
                "ok": True,
                "authenticated": True,
                "role": user.role,
                "user_id": user.id,
                "username": user.username,
                "open_mode": False,
                "message": "Přihlášení OK.",
            }
        )
        set_auth_cookie(response, token)
        return response
    finally:
        session.close()


@router.post("/api/auth/logout")
async def api_auth_logout() -> Response:
    response = JSONResponse({"ok": True, "authenticated": False})
    response.delete_cookie(PILOT_COOKIE_NAME, path="/")
    return response

