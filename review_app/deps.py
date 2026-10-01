from __future__ import annotations

from pathlib import Path

from fastapi import Request, Response

from db.session import get_session_factory
from review_app.paths import ROOT
from review_app.settings import pilot_cookie_secure
from auth.pilot import (
    COOKIE_NAME as PILOT_COOKIE_NAME,
)
from auth.pilot import (
    SESSION_TTL_SEC,
    parse_session_value,
    pilot_code_enabled,
)


def parse_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return env


def configured_token() -> str | None:
    from review_app.settings import SETTINGS, env_str

    tok = (SETTINGS.github_token or env_str("GITHUB_TOKEN") or env_str("GH_TOKEN")).strip()
    if tok:
        return tok
    dotenv = ROOT / ".env"
    if dotenv.exists():
        env_map = parse_dotenv(dotenv)
        tok = (env_map.get("GITHUB_TOKEN") or env_map.get("GH_TOKEN") or "").strip()
        if tok:
            return tok
    return None


def request_has_pilot_session(request: Request) -> bool:
    if not pilot_code_enabled(ROOT):
        return True
    return bool(parse_session_value(request.cookies.get(PILOT_COOKIE_NAME), ROOT))


def session_from_request(request: Request):
    return parse_session_value(request.cookies.get(PILOT_COOKIE_NAME), ROOT)


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=PILOT_COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SEC,
        httponly=True,
        samesite="lax",
        secure=pilot_cookie_secure(),
        path="/",
    )


def db_session():
    return get_session_factory()()


def ensure_drafts_dir() -> Path:
    from review_app.paths import DRAFTS_DIR

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    return DRAFTS_DIR


def api_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def safe_id(value: str) -> str:
    safe = "".join(ch for ch in value if ch.isalnum() or ch in {"-", "_"})
    return safe if safe == value else ""
