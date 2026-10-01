from __future__ import annotations

import json
import uuid

from sqlalchemy.orm import Session

from db.models import AuditEvent, User
from db.repos.common import safe_id

def ensure_pilot_user(session: Session) -> User:
    user = session.get(User, "pilot")
    if user:
        return user
    user = User(
        id="pilot",
        username="pilot",
        display_name="Pilot",
        role="reviewer",
        password_hash=None,
    )
    session.add(user)
    session.flush()
    return user


def add_audit(
    session: Session,
    *,
    event_type: str,
    message: str = "",
    actor_user_id: str | None = None,
    payload: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        id=uuid.uuid4().hex,
        actor_user_id=actor_user_id,
        event_type=event_type,
        message=message,
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
    )
    session.add(event)
    return event

