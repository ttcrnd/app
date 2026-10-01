from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from db.repository import list_libraries, list_pilot_empirie
from db.session import resolve_database_url
from review_app.deps import db_session
from review_app.paths import ROOT

router = APIRouter(tags=["pilot"])

@router.get("/api/db/info")
async def api_db_info() -> JSONResponse:
    url = resolve_database_url(ROOT)
    dialect = url.split(":", 1)[0]
    return JSONResponse(
        {
            "dialect": dialect,
            "database_url_scheme": dialect,
            "postgres_ready": True,
            "docs": "docs/DATABASE.md",
        }
    )


@router.get("/api/pilot/empirie")
async def api_pilot_empirie() -> JSONResponse:
    session = db_session()
    try:
        return JSONResponse(list_pilot_empirie(session))
    finally:
        session.close()


@router.get("/api/pilot/status")
async def api_pilot_status() -> JSONResponse:
    """D10 readiness: ≥3 libraries, ≥1 Nedoporučeno, empirie available."""
    session = db_session()
    try:
        libs = list_libraries(session, limit=200)
        empirie = list_pilot_empirie(session)
        repos = {item["repo"] for item in libs}
        terminal = [
            item for item in libs if item.get("catalog_status") in {"completed", "not_recommended"}
        ]
        not_rec = [item for item in libs if item.get("catalog_status") == "not_recommended"]
        d10_ok = len(repos) >= 3 and len(not_rec) >= 1 and len(terminal) >= 3
        return JSONResponse(
            {
                "d10_closed": d10_ok,
                "libraries": len(libs),
                "libraries_terminal": len(terminal),
                "not_recommended": len(not_rec),
                "empirie": {
                    "evaluations": empirie.get("evaluations"),
                    "heuristic_accept_rate_pct": empirie.get("heuristic_accept_rate_pct"),
                    "accepted_auto_total": empirie.get("accepted_auto_total"),
                    "confirm_after_heuristic_total": empirie.get("confirm_after_heuristic_total"),
                },
                "docs": {
                    "pilot": "../knihovny-pilot.md",
                    "empirie": "../empirie-pilot.md",
                },
            }
        )
    finally:
        session.close()

