#!/usr/bin/env python3
"""Thin entrypoint — keeps `uvicorn server:app` and `from server import app` working."""
from __future__ import annotations

from review_app import deps as _deps
from review_app.forms import resolve_pdf_identification as _resolve_pdf_identification
from review_app.main import app, create_app
from review_app.paths import ROOT
from review_app.settings import SETTINGS


def _configured_token():
    """Compatibility wrapper — tests may monkeypatch this name on `server`."""
    return _deps.configured_token()


__all__ = [
    "app",
    "create_app",
    "SETTINGS",
    "ROOT",
    "_configured_token",
    "_resolve_pdf_identification",
]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host=SETTINGS.host,
        port=SETTINGS.port,
        reload=SETTINGS.reload,
        log_level=SETTINGS.log_level.lower(),
    )
