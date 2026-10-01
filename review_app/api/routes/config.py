from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from review_app import deps
from review_app.paths import ROOT
from auth.pilot import (
    COOKIE_NAME as PILOT_COOKIE_NAME,
)
from auth.pilot import (
    auth_status as pilot_auth_status,
)

router = APIRouter(tags=["config"])

@router.get("/api/config")
async def api_config(request: Request) -> JSONResponse:
    from services.ai import ai_status

    token = deps.configured_token()
    auth = pilot_auth_status(ROOT, request.cookies.get(PILOT_COOKIE_NAME))
    return JSONResponse(
        {
            "needs_token": not bool(token),
            "token_present": bool(token),
            "auth": auth,
            "ai": ai_status(),
        }
    )


