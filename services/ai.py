"""AI note assistance (krok 11 / D12) — OpenAI or Anthropic, default off."""

from __future__ import annotations

import os
import re
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import requests

# Redact secrets before they ever reach a prompt.
_SECRET_RE = re.compile(
    r"(?i)(\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}"
    r"|\bsk-[A-Za-z0-9_-]{20,}"
    r"|\bBearer\s+[A-Za-z0-9._\-]+"
    r"|\bxox[baprs]-[A-Za-z0-9-]+)"
)


def redact_secrets(text: str) -> str:
    return _SECRET_RE.sub("[REDACTED]", text or "")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AiSuggestResult:
    text: str
    model: str
    provider: str
    proposal_source: str = "ai"


class AiAssistClient(ABC):
    provider: str

    @abstractmethod
    def suggest_note(
        self,
        *,
        question_text: str,
        description: str,
        evidence: str,
        current_note: str,
        heuristic: str,
        rating: str,
        category: str,
    ) -> AiSuggestResult:
        raise NotImplementedError

    @abstractmethod
    def suggest_remaining_summary(
        self, *, section_title: str, remaining: list[str]
    ) -> AiSuggestResult:
        raise NotImplementedError


class DisabledAiClient(AiAssistClient):
    provider = "disabled"

    def suggest_note(self, **_kwargs: Any) -> AiSuggestResult:
        raise RuntimeError("AI asistence je vypnutá (AI_ENABLED=false).")

    def suggest_remaining_summary(self, **_kwargs: Any) -> AiSuggestResult:
        raise RuntimeError("AI asistence je vypnutá (AI_ENABLED=false).")


class OpenAiAssistClient(AiAssistClient):
    provider = "openai"

    def __init__(self, api_key: str, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = (model or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini").strip()

    def _chat(self, system: str, user: str) -> str:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=60,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"OpenAI chyba {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return str(data["choices"][0]["message"]["content"]).strip()

    def suggest_note(self, **kwargs: Any) -> AiSuggestResult:
        text = self._chat(_NOTE_SYSTEM, _build_note_user(**kwargs))
        return AiSuggestResult(text=text, model=self.model, provider=self.provider)

    def suggest_remaining_summary(
        self, *, section_title: str, remaining: list[str]
    ) -> AiSuggestResult:
        text = self._chat(_REMAINING_SYSTEM, _build_remaining_user(section_title, remaining))
        return AiSuggestResult(text=text, model=self.model, provider=self.provider)


class AnthropicAssistClient(AiAssistClient):
    provider = "anthropic"

    def __init__(self, api_key: str, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = (
            model or os.environ.get("ANTHROPIC_MODEL") or "claude-3-5-haiku-latest"
        ).strip()

    def _chat(self, system: str, user: str) -> str:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 600,
                "temperature": 0.3,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=60,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Anthropic chyba {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        parts = data.get("content") or []
        texts = [str(p.get("text") or "") for p in parts if isinstance(p, dict)]
        return "\n".join(t for t in texts if t).strip()

    def suggest_note(self, **kwargs: Any) -> AiSuggestResult:
        text = self._chat(_NOTE_SYSTEM, _build_note_user(**kwargs))
        return AiSuggestResult(text=text, model=self.model, provider=self.provider)

    def suggest_remaining_summary(
        self, *, section_title: str, remaining: list[str]
    ) -> AiSuggestResult:
        text = self._chat(_REMAINING_SYSTEM, _build_remaining_user(section_title, remaining))
        return AiSuggestResult(text=text, model=self.model, provider=self.provider)


_NOTE_SYSTEM = (
    "Jsi asistent hodnotitele open-source knihoven podle metodiky NÚKIB. "
    "Navrhni stručnou českou poznámku (2–5 vět) z kritéria, důkazů a stávající poznámky. "
    "Nesmím měnit rating ani tvrdit, že je kritérium splněno, pokud to důkazy jasně neříkají. "
    "Neuváděj tajné tokeny. Vrať jen text poznámky, bez uvozovek a bez nadpisu."
)

_REMAINING_SYSTEM = (
    "Jsi asistent hodnotitele. Shrň česky v 2–4 větách, co zbývá v sekci hodnocení. "
    "Nehodnoť automaticky jako splňuje. Vrať jen shrnutí."
)


def _build_note_user(
    *,
    question_text: str,
    description: str,
    evidence: str,
    current_note: str,
    heuristic: str,
    rating: str,
    category: str,
) -> str:
    parts = [
        f"Kritérium: {redact_secrets(question_text)}",
        f"Kategorie: {redact_secrets(category)}",
        f"Aktuální výsledek (neměň): {redact_secrets(rating)}",
        f"Popis: {redact_secrets(description)}",
        f"Podklady automatu: {redact_secrets(heuristic)}",
        f"Důkazy:\n{redact_secrets(evidence)}",
        f"Stávající poznámka:\n{redact_secrets(current_note)}",
    ]
    return "\n\n".join(parts)


def _build_remaining_user(section_title: str, remaining: list[str]) -> str:
    lines = "\n".join(f"- {redact_secrets(item)}" for item in remaining[:40])
    return f"Sekce: {redact_secrets(section_title)}\n\nZbývá:\n{lines}"


def ai_enabled() -> bool:
    return _env_bool("AI_ENABLED", False)


def resolve_provider_name() -> str:
    raw = (os.environ.get("AI_PROVIDER") or "").strip().lower()
    if raw in {"openai", "anthropic"}:
        return raw
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "openai"


def get_ai_client() -> AiAssistClient:
    if not ai_enabled():
        return DisabledAiClient()
    provider = resolve_provider_name()
    if provider == "anthropic":
        key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY chybí.")
        return AnthropicAssistClient(key)
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY chybí.")
    return OpenAiAssistClient(key)


def ai_status() -> dict[str, Any]:
    enabled = ai_enabled()
    provider = resolve_provider_name()
    has_openai = bool((os.environ.get("OPENAI_API_KEY") or "").strip())
    has_anthropic = bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip())
    available = enabled and (
        (provider == "openai" and has_openai) or (provider == "anthropic" and has_anthropic)
    )
    return {
        "enabled": enabled,
        "available": available,
        "provider": provider if enabled else None,
        "has_openai_key": has_openai,
        "has_anthropic_key": has_anthropic,
        "default_off": True,
    }


class RateLimiter:
    """Simple in-memory sliding window rate limit (per key)."""

    def __init__(self, limit: int = 10, window_sec: int = 60) -> None:
        self.limit = limit
        self.window_sec = window_sec
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            bucket = [t for t in self._hits.get(key, []) if now - t < self.window_sec]
            if len(bucket) >= self.limit:
                self._hits[key] = bucket
                return False
            bucket.append(now)
            self._hits[key] = bucket
            return True


AI_RATE_LIMITER = RateLimiter(
    limit=int(os.environ.get("AI_RATE_LIMIT_PER_MIN") or "10"),
    window_sec=60,
)
