from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from domain.export import validate_official_export

router = APIRouter(tags=["export"])


@router.post("/api/export/check")
async def api_export_check(payload: dict) -> JSONResponse:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")
    form_obj = payload.get("form") if isinstance(payload.get("form"), dict) else payload
    return JSONResponse(validate_official_export(form_obj))
