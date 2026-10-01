from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_str(name: str, default: str = "") -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip()


def load_dotenv(path: Path) -> dict[str, str]:
    """Load KEY=VALUE pairs into os.environ (does not override existing)."""
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            value = value.strip().strip('"').strip("'")
            loaded[key] = value
            if key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass
    return loaded


def pilot_cookie_secure() -> bool:
    return env_bool("PILOT_COOKIE_SECURE", False)


@dataclass(frozen=True)
class AppSettings:
    """Central runtime settings (env / .env). Prefer this over ad-hoc os.environ."""

    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = True
    log_level: str = "INFO"
    database_url: str = ""
    github_token: str = ""
    pilot_cookie_secure: bool = False
    public_base_url: str = ""
    ai_enabled: bool = False
    dotenv_path: Path | None = None
    extras: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_environ(cls, *, root: Path | None = None) -> AppSettings:
        base = root or Path(__file__).resolve().parent.parent
        dotenv_path = base / ".env"
        load_dotenv(dotenv_path)
        token = env_str("GITHUB_TOKEN") or env_str("GH_TOKEN")
        return cls(
            host=env_str("REVIEW_SERVICE_HOST", "127.0.0.1") or "127.0.0.1",
            port=env_int("REVIEW_SERVICE_PORT", 8000),
            reload=env_bool("REVIEW_SERVER_RELOAD", True),
            log_level=(env_str("REVIEW_LOG_LEVEL", "INFO") or "INFO").upper(),
            database_url=env_str("DATABASE_URL"),
            github_token=token,
            pilot_cookie_secure=env_bool("PILOT_COOKIE_SECURE", False),
            public_base_url=env_str("PUBLIC_BASE_URL"),
            ai_enabled=env_bool("AI_ENABLED", False),
            dotenv_path=dotenv_path if dotenv_path.exists() else None,
        )


# Back-compat alias used by server.py / uvicorn __main__
ServerSettings = AppSettings


def configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


SETTINGS = AppSettings.from_environ()
configure_logging(SETTINGS.log_level)
