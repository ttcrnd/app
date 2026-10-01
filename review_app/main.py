from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from db.repository import (
    ensure_bootstrap_admin,
    ensure_pilot_user,
    migrate_file_drafts,
    seed_pilot_evaluations,
    seed_pilot_libraries,
)
from db.session import get_session_factory, init_db
from review_app.api.routes import (
    ai,
    auth,
    config,
    evaluations,
    examples,
    export_check,
    form_ops,
    health,
    libraries,
    pdf,
    pilot,
    pipeline,
    users,
)
from review_app.paths import DRAFTS_DIR, LEGACY_DRAFTS_DIR, ROOT, WEB_DIR
from review_app.settings import SETTINGS  # noqa: F401 — configure logging side effect
from auth.pilot import (
    COOKIE_NAME as PILOT_COOKIE_NAME,
)
from auth.pilot import (
    auth_required,
    parse_session_value,
    path_requires_auth,
)


def _run_startup_db() -> None:
    import logging
    import os

    logger = logging.getLogger("review.pdf")
    init_db()
    factory = get_session_factory()
    session = factory()
    try:
        seed_enabled = os.environ.get("REVIEW_SEED_PILOT", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        seeded = seed_pilot_libraries(session) if seed_enabled else 0
        seeded_evals = seed_pilot_evaluations(session) if seed_enabled else 0
        imported = migrate_file_drafts(session, DRAFTS_DIR)
        imported += migrate_file_drafts(session, LEGACY_DRAFTS_DIR)
        ensure_pilot_user(session)
        ensure_bootstrap_admin(session, ROOT)
        session.commit()
        if seeded:
            logger.info("[db] seeded %s pilot libraries", seeded)
        if seeded_evals:
            logger.info("[db] seeded %s pilot evaluations", seeded_evals)
        if imported:
            logger.info("[db] migrated %s file drafts into SQLite", imported)
    except Exception:
        session.rollback()
        logger.exception("[db] startup migration failed")
    finally:
        session.close()


@asynccontextmanager
async def _lifespan(_application: FastAPI):
    _run_startup_db()
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="Review Pipeline Server",
        version="0.1.0",
        lifespan=_lifespan,
    )

    @application.middleware("http")
    async def pilot_auth_middleware(request: Request, call_next):
        path = request.url.path
        if auth_required(ROOT) and path_requires_auth(request.method, path):
            session = parse_session_value(request.cookies.get(PILOT_COOKIE_NAME), ROOT)
            if not session:
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": {
                            "code": "auth_required",
                            "message": "Pro tuto akci se přihlas (kód nebo účet).",
                        }
                    },
                )
            if session.role == "viewer" and request.method.upper() != "GET":
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": {
                            "code": "forbidden",
                            "message": "Role viewer nemá právo zapisovat.",
                        }
                    },
                )
            request.state.pilot_session = session
        return await call_next(request)

    for module in (
        health,
        auth,
        users,
        pipeline,
        examples,
        config,
        ai,
        form_ops,
        pdf,
        libraries,
        evaluations,
        pilot,
        export_check,
    ):
        application.include_router(module.router)

    web_dir = WEB_DIR
    web_dir.mkdir(exist_ok=True)
    # Static mount last so /api/* wins.
    application.mount("/", StaticFiles(directory=str(web_dir), html=True), name="static")
    return application


app = create_app()
