"""Auth sessions: pilot access code + username/password roles (krok 5 + 13)."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

COOKIE_NAME = "nukib_pilot_session"
SESSION_TTL_SEC = 60 * 60 * 24 * 14  # 14 days
ROLES = ("viewer", "reviewer", "admin")
PILOT_DEFAULT_ROLE = "reviewer"
PILOT_USER_ID = "pilot"

PBKDF2_ITERS = 200_000


@dataclass(frozen=True)
class PilotSession:
    role: str
    open_mode: bool = False
    user_id: str = PILOT_USER_ID
    username: str = "pilot"
    auth_method: str = "code"  # code | password | open


def _parse_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        pass
    return env


def _env_value(name: str, root: Path | None = None) -> str:
    raw = os.environ.get(name)
    if raw is not None and raw.strip():
        return raw.strip()
    if root is not None:
        dotenv = root / ".env"
        if dotenv.exists():
            mapped = _parse_dotenv(dotenv).get(name, "")
            if mapped.strip():
                return mapped.strip()
    return ""


def _env_bool(name: str, default: bool, root: Path | None = None) -> bool:
    raw = _env_value(name, root)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def configured_access_codes(root: Path) -> list[str]:
    multi = _env_value("PILOT_ACCESS_CODES", root)
    single = _env_value("PILOT_ACCESS_CODE", root)
    raw = multi or single
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def pilot_code_enabled(root: Path) -> bool:
    codes = configured_access_codes(root)
    if not codes:
        return False
    return _env_bool("PILOT_CODE_ENABLED", True, root)


def user_auth_enabled(root: Path) -> bool:
    """Username/password accounts (krok 13)."""
    return _env_bool("USER_AUTH_ENABLED", False, root)


def auth_required(root: Path) -> bool:
    """Write APIs need a session when pilot code and/or user auth is on."""
    return pilot_code_enabled(root) or user_auth_enabled(root)


def session_secret(root: Path) -> bytes:
    explicit = _env_value("PILOT_SESSION_SECRET", root)
    if explicit:
        return hashlib.sha256(explicit.encode("utf-8")).digest()
    codes = configured_access_codes(root)
    material = "|".join(codes) if codes else "nukib-open-mode"
    return hashlib.sha256(f"nukib-pilot|{material}".encode()).digest()


def verify_access_code(code: str, root: Path) -> bool:
    needle = (code or "").strip()
    if not needle:
        return False
    for allowed in configured_access_codes(root):
        if hmac.compare_digest(needle, allowed):
            return True
    return False


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, PBKDF2_ITERS)
    return f"pbkdf2_sha256${PBKDF2_ITERS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash or not isinstance(password_hash, str):
        return False
    try:
        algo, iters_s, salt_hex, hash_hex = password_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iters = int(iters_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except Exception:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, iters)
    return hmac.compare_digest(dk, expected)


def issue_session_value(
    *,
    role: str = PILOT_DEFAULT_ROLE,
    root: Path,
    user_id: str = PILOT_USER_ID,
    username: str = "pilot",
    auth_method: str = "code",
) -> str:
    if role not in ROLES:
        role = PILOT_DEFAULT_ROLE
    safe_uid = "".join(ch for ch in (user_id or PILOT_USER_ID) if ch.isalnum() or ch in "-_")
    safe_user = (
        "".join(ch for ch in (username or "pilot") if ch.isalnum() or ch in "-_@.") or "pilot"
    )
    method = auth_method if auth_method in {"code", "password", "open"} else "code"
    exp = int(time.time()) + SESSION_TTL_SEC
    # v2: user_id + username + role + method + exp
    payload = f"v2.{safe_uid}.{safe_user}.{role}.{method}.{exp}"
    sig = hmac.new(session_secret(root), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def parse_session_value(raw: str | None, root: Path) -> PilotSession | None:
    if not raw or not isinstance(raw, str):
        return None
    parts = raw.strip().split(".")
    # v1: v1.role.exp.sig (4 parts)
    if len(parts) == 4 and parts[0] == "v1":
        version, role, exp_s, sig = parts
        if role not in ROLES:
            return None
        try:
            exp = int(exp_s)
        except ValueError:
            return None
        if exp < int(time.time()):
            return None
        payload = f"{version}.{role}.{exp_s}"
        expected = hmac.new(
            session_secret(root), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        return PilotSession(
            role=role,
            open_mode=False,
            user_id=PILOT_USER_ID,
            username="pilot",
            auth_method="code",
        )

    # v2: v2.uid.username.role.method.exp.sig (7 parts)
    if len(parts) == 7 and parts[0] == "v2":
        version, user_id, username, role, method, exp_s, sig = parts
        if role not in ROLES:
            return None
        try:
            exp = int(exp_s)
        except ValueError:
            return None
        if exp < int(time.time()):
            return None
        payload = f"{version}.{user_id}.{username}.{role}.{method}.{exp_s}"
        expected = hmac.new(
            session_secret(root), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        return PilotSession(
            role=role,
            open_mode=False,
            user_id=user_id,
            username=username,
            auth_method=method if method in {"code", "password", "open"} else "code",
        )
    return None


def auth_status(root: Path, cookie_value: str | None) -> dict:
    code_on = pilot_code_enabled(root)
    users_on = user_auth_enabled(root)
    gate = code_on or users_on
    if not gate:
        return {
            "enabled": False,
            "authenticated": True,
            "role": PILOT_DEFAULT_ROLE,
            "open_mode": True,
            "roles": list(ROLES),
            "user_id": PILOT_USER_ID,
            "username": "pilot",
            "auth_method": "open",
            "pilot_code_enabled": False,
            "user_auth_enabled": False,
            "can_manage_users": False,
            "can_write": True,
        }
    session = parse_session_value(cookie_value, root)
    role = session.role if session else None
    return {
        "enabled": True,
        "authenticated": bool(session),
        "role": role,
        "open_mode": False,
        "roles": list(ROLES),
        "user_id": session.user_id if session else None,
        "username": session.username if session else None,
        "auth_method": session.auth_method if session else None,
        "pilot_code_enabled": code_on,
        "user_auth_enabled": users_on,
        "can_manage_users": bool(session and session.role == "admin"),
        "can_write": bool(session and session.role in {"reviewer", "admin"}),
    }


def role_can_write(role: str | None) -> bool:
    return role in {"reviewer", "admin"}


def role_can_manage_users(role: str | None) -> bool:
    return role == "admin"


def role_can_access_all_evaluations(role: str | None) -> bool:
    return role == "admin"


def path_requires_auth(method: str, path: str) -> bool:
    """Write/run and private evaluation APIs require a session when auth gate is on."""
    m = method.upper()
    p = path.rstrip("/") or "/"

    if p.startswith("/api/auth"):
        return False
    if p in {"/health", "/healthz", "/api/config", "/api/db/info", "/api/signing/public-key"}:
        return False
    if p.startswith("/api/examples"):
        return False
    if m == "GET" and (
        p in {"/api/libraries", "/api/pilot/status", "/api/pilot/empirie"}
        or p.startswith("/api/libraries/")
        or p.startswith("/api/pilot/")
    ):
        return False

    if m == "GET" and p.startswith("/api/users"):
        return True
    if m in {"POST", "PATCH", "DELETE"} and p.startswith("/api/users"):
        return True

    if m == "POST" and p in {
        "/api/run",
        "/api/drafts",
        "/api/evaluations",
        "/api/pdf",
        "/api/recalculate",
        "/api/validate-form",
        "/api/export/check",
        "/api/ai/suggest-note",
        "/api/ai/suggest-remaining",
        "/api/evaluations/verify",
    }:
        return True
    if m == "POST" and p.startswith("/api/ai/"):
        return True
    if (
        m == "POST"
        and (p.endswith("/complete") or p.endswith("/sign"))
        and (p.startswith("/api/drafts/") or p.startswith("/api/evaluations/"))
    ):
        return True
    if m == "DELETE" and (
        p.startswith("/api/drafts/")
        or p.startswith("/api/evaluations/")
        or p.startswith("/api/libraries/")
    ):
        return True

    if m == "GET" and (p in {"/api/drafts", "/api/evaluations"}):
        return True
    if m == "GET" and (p.startswith("/api/drafts/") or p.startswith("/api/evaluations/")):
        return False

    return False
