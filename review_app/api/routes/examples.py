from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from review_app.paths import EXAMPLE_DIR
from domain.workflow import normalize_form_workflow

router = APIRouter(tags=["examples"])


def secure_example_path(name: str) -> Path:
    if "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    p = (EXAMPLE_DIR / name).resolve()
    try:
        p.relative_to(EXAMPLE_DIR.resolve())
    except ValueError as err:
        raise HTTPException(status_code=400, detail="Invalid filename") from err
    return p


@router.get("/api/examples")
async def api_examples_list() -> JSONResponse:
    if not EXAMPLE_DIR.exists():
        return JSONResponse({"files": []})
    files = [p.name for p in sorted(EXAMPLE_DIR.glob("*.json")) if p.is_file()]
    return JSONResponse({"files": files})


@router.get("/api/examples/{name}")
async def api_example_detail(name: str) -> JSONResponse:
    p = secure_example_path(name)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        data = normalize_form_workflow(data, pipeline_mode=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read example: {e}") from e
    return JSONResponse(data)
