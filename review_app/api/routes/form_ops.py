from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from review_app.forms import calc_summary, validate_and_prepare_form
from domain.workflow import normalize_form_workflow

router = APIRouter(tags=["form"])


@router.post("/api/recalculate")
async def api_recalculate(payload: dict) -> JSONResponse:
    """Recalculate summary for a client-edited form JSON."""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")
    form_obj = json.loads(json.dumps(payload))
    try:
        form_obj = normalize_form_workflow(form_obj, pipeline_mode=False)
        summary = calc_summary(form_obj)
        form_obj["summary"] = summary
        return JSONResponse({"summary": summary, "form": form_obj})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to recalculate: {e}") from e


@router.post("/api/validate-form")
async def api_validate_form(payload: dict) -> JSONResponse:
    try:
        form_obj = validate_and_prepare_form(payload)
        return JSONResponse({"valid": True, "form": form_obj, "summary": form_obj.get("summary")})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Nepodařilo se ověřit soubor: {e}") from e
