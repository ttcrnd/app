from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import (
    Artifact,
    AuditEvent,
    Evaluation,
    EvaluationEvent,
    Library,
    LibraryVersion,
    User,
    utcnow,
)

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = ROOT / "data" / "artifacts"


def safe_id(value: str | None) -> str:
    raw = "".join(ch for ch in (value or "") if ch.isalnum() or ch in {"-", "_"})
    return raw or uuid.uuid4().hex


def library_name(repo: str) -> str:
    parts = [p for p in (repo or "").split("/") if p]
    return parts[-1] if parts else (repo or "knihovna")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# Back-compat private aliases
_safe_id = safe_id
_library_name = library_name
_parse_iso = parse_iso
