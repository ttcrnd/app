from __future__ import annotations

import re
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import User, utcnow
from db.repos.audit import add_audit
from db.repos.common import ROOT

def user_to_dict(user: User, *, include_sensitive: bool = False) -> dict:
    body = {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name or user.username,
        "role": user.role,
        "has_password": bool(user.password_hash),
        "created_at": user.created_at.isoformat() if user.created_at else "",
        "updated_at": user.updated_at.isoformat() if user.updated_at else "",
    }
    if include_sensitive:
        body["password_hash_set"] = bool(user.password_hash)
    return body


def list_users(session: Session) -> list[dict]:
    rows = session.scalars(select(User).order_by(User.username.asc())).all()
    return [user_to_dict(u) for u in rows]


def get_user_by_username(session: Session, username: str) -> User | None:
    uname = (username or "").strip().lower()
    if not uname:
        return None
    return session.scalar(select(User).where(User.username == uname))


def create_user(
    session: Session,
    *,
    username: str,
    password: str,
    role: str = "reviewer",
    display_name: str = "",
    actor_user_id: str | None = None,
) -> User:
    from auth.pilot import ROLES, hash_password

    uname = (username or "").strip().lower()
    if not uname or not re.fullmatch(r"[a-z0-9._@-]{2,64}", uname):
        raise ValueError("Neplatné uživatelské jméno")
    if role not in ROLES:
        raise ValueError("Neplatná role")
    if len(password or "") < 6:
        raise ValueError("Heslo musí mít alespoň 6 znaků")
    if get_user_by_username(session, uname):
        raise ValueError("Uživatel už existuje")
    user = User(
        id=uuid.uuid4().hex[:16],
        username=uname,
        display_name=(display_name or uname).strip(),
        role=role,
        password_hash=hash_password(password),
    )
    session.add(user)
    add_audit(
        session,
        event_type="user_created",
        message=f"Vytvořen uživatel {uname} ({role})",
        actor_user_id=actor_user_id,
        payload={"user_id": user.id, "username": uname, "role": role},
    )
    session.flush()
    return user


def update_user(
    session: Session,
    user_id: str,
    *,
    role: str | None = None,
    password: str | None = None,
    display_name: str | None = None,
    actor_user_id: str | None = None,
) -> User:
    from auth.pilot import ROLES, hash_password

    user = session.get(User, user_id)
    if not user:
        raise KeyError("Uživatel nenalezen")
    changed: dict = {}
    if role is not None:
        if role not in ROLES:
            raise ValueError("Neplatná role")
        if user.role != role:
            changed["role"] = {"from": user.role, "to": role}
            user.role = role
    if display_name is not None:
        user.display_name = display_name.strip()
        changed["display_name"] = user.display_name
    if password is not None and password != "":
        if len(password) < 6:
            raise ValueError("Heslo musí mít alespoň 6 znaků")
        user.password_hash = hash_password(password)
        changed["password"] = "updated"
    user.updated_at = utcnow()
    add_audit(
        session,
        event_type="user_updated",
        message=f"Upraven uživatel {user.username}",
        actor_user_id=actor_user_id,
        payload={"user_id": user.id, "changes": changed},
    )
    session.flush()
    return user


def delete_user(
    session: Session,
    user_id: str,
    *,
    actor_user_id: str | None = None,
) -> None:
    user = session.get(User, user_id)
    if not user:
        raise KeyError("Uživatel nenalezen")
    if user.id == "pilot":
        raise ValueError("Účet pilot nelze smazat")
    if actor_user_id and user.id == actor_user_id:
        raise ValueError("Nelze smazat vlastní účet")
    add_audit(
        session,
        event_type="user_deleted",
        message=f"Smazán uživatel {user.username}",
        actor_user_id=actor_user_id,
        payload={"user_id": user.id, "username": user.username, "role": user.role},
    )
    session.delete(user)
    session.flush()


def authenticate_user(session: Session, username: str, password: str) -> User | None:
    from auth.pilot import verify_password

    user = get_user_by_username(session, username)
    if not user or not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def ensure_bootstrap_admin(session: Session, root: Path | None = None) -> User | None:
    """Create admin from ADMIN_USERNAME / ADMIN_PASSWORD env if missing."""
    from auth.pilot import _env_value, hash_password

    base = root or ROOT
    username = _env_value("ADMIN_USERNAME", base).strip().lower()
    password = _env_value("ADMIN_PASSWORD", base)
    if not username or not password:
        return None
    existing = get_user_by_username(session, username)
    if existing:
        if not existing.password_hash:
            existing.password_hash = hash_password(password)
            existing.role = "admin"
            session.flush()
        return existing
    return create_user(
        session,
        username=username,
        password=password,
        role="admin",
        display_name="Admin",
        actor_user_id=None,
    )

