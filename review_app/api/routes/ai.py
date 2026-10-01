from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from review_app.deps import db_session
from review_app.paths import ROOT
from auth.pilot import (
    COOKIE_NAME as PILOT_COOKIE_NAME,
)
from auth.pilot import (
    parse_session_value,
    pilot_code_enabled,
    role_can_write,
)
from auth.pilot import (
    auth_status as pilot_auth_status,
)

logger = logging.getLogger("review.ai")
router = APIRouter(tags=["ai"])

@router.get("/api/ai/status")
async def api_ai_status() -> JSONResponse:
    from services.ai import ai_status

    return JSONResponse(ai_status())


@router.post("/api/ai/suggest-note")
async def api_ai_suggest_note(request: Request, payload: dict) -> JSONResponse:
    from services.ai import AI_RATE_LIMITER, get_ai_client, redact_secrets

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")
    rate_key = request.client.host if request.client else "anon"
    if pilot_code_enabled(ROOT):
        session = parse_session_value(request.cookies.get(PILOT_COOKIE_NAME), ROOT)
        if session:
            rate_key = f"role:{session.role}:{rate_key}"
    if not AI_RATE_LIMITER.allow(rate_key):
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "AI limit — zkus to za chvíli."},
        )

    question = payload.get("question") if isinstance(payload.get("question"), dict) else payload
    evaluation_id = str(payload.get("evaluation_id") or "").strip()
    try:
        client = get_ai_client()
        result = client.suggest_note(
            question_text=redact_secrets(
                str(question.get("text") or question.get("question_text") or "")
            ),
            description=redact_secrets(str(question.get("description") or "")),
            evidence=redact_secrets(str(question.get("evidence") or "")),
            current_note=redact_secrets(
                str(question.get("note") or question.get("current_note") or "")
            ),
            heuristic=redact_secrets(str(question.get("heuristic") or "")),
            rating=redact_secrets(str(question.get("rating") or "nehodnoceno")),
            category=redact_secrets(str(question.get("category") or "")),
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI poskytovatel selhal: {e}") from e

    if evaluation_id:
        session = db_session()
        try:
            from db.repository import add_event, get_evaluation

            if get_evaluation(session, evaluation_id):
                add_event(
                    session,
                    evaluation_id,
                    "ai_suggest",
                    message=result.text[:500],
                    payload={
                        "kind": "note",
                        "provider": result.provider,
                        "model": result.model,
                        "proposal_source": result.proposal_source,
                        "question_id": str(question.get("id") or ""),
                    },
                )
                session.commit()
        except Exception:
            session.rollback()
            logger.exception("[ai] failed to log ai_suggest event")
        finally:
            session.close()

    from datetime import datetime, timezone

    return JSONResponse(
        {
            "suggestion": result.text,
            "proposal_source": result.proposal_source,
            "provider": result.provider,
            "model": result.model,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rating_unchanged": True,
        }
    )


@router.post("/api/ai/suggest-remaining")
async def api_ai_suggest_remaining(request: Request, payload: dict) -> JSONResponse:
    from services.ai import AI_RATE_LIMITER, get_ai_client

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")
    rate_key = request.client.host if request.client else "anon"
    if not AI_RATE_LIMITER.allow(rate_key):
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "AI limit — zkus to za chvíli."},
        )
    remaining = payload.get("remaining") or []
    if not isinstance(remaining, list):
        raise HTTPException(status_code=400, detail="remaining musí být seznam")
    try:
        client = get_ai_client()
        result = client.suggest_remaining_summary(
            section_title=str(payload.get("section_title") or "Sekce"),
            remaining=[str(x) for x in remaining],
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI poskytovatel selhal: {e}") from e
    from datetime import datetime, timezone

    return JSONResponse(
        {
            "suggestion": result.text,
            "proposal_source": result.proposal_source,
            "provider": result.provider,
            "model": result.model,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

