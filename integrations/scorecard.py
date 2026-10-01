"""OpenSSF Scorecard fetch + check mapping (not methodology grade)."""

from __future__ import annotations

from typing import Any

from integrations.http import get_json

UA = "oss-review-suite/1.0 (+https://github.com)"


def fetch_scorecard(owner: str, repo: str) -> dict[str, Any]:
    """Return raw API envelope: {status, data}. Never raises."""
    proj = f"github.com/{owner}/{repo}"
    url = f"https://api.securityscorecards.dev/projects/{proj}"
    status, data, _ = get_json(url, headers={"User-Agent": UA}, timeout=45)
    return {"status": status, "data": data if isinstance(data, dict) else None}


def _checks(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") if "data" in payload else payload
    if not isinstance(data, dict):
        return []
    checks = data.get("checks")
    return checks if isinstance(checks, list) else []


def check_entry(payload: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    target = (name or "").strip().lower()
    for check in _checks(payload):
        if not isinstance(check, dict):
            continue
        if str(check.get("name") or "").strip().lower() == target:
            return check
    return None


def check_score(payload: dict[str, Any] | None, name: str) -> float | None:
    entry = check_entry(payload, name)
    if not entry:
        return None
    raw = entry.get("score")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def check_evidence_url(payload: dict[str, Any] | None, name: str) -> str | None:
    entry = check_entry(payload, name)
    if not entry:
        return None
    for key in ("detailsUrl", "documentation", "reason"):
        val = entry.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
    repo = None
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        repo = data.get("repo")
        if isinstance(repo, dict):
            name_url = repo.get("name")
            if isinstance(name_url, str) and name_url.startswith("github.com/"):
                return f"https://{name_url}"
    return f"https://api.securityscorecards.dev/projects/github.com/{name}" if name else None


def build_scorecard_map(payload: dict[str, Any] | None) -> dict[str, Any]:
    """
    Normalized signals for section 2/3 evaluators.
    Overall Scorecard score is intentionally omitted from ratings.
    """
    names = (
        "Code-Review",
        "Branch-Protection",
        "CI-Tests",
        "Fuzzing",
        "Dependency-Update-Tool",
        "Maintained",
        "Binary-Artifacts",
        "Dangerous-Workflow",
        "Token-Permissions",
        "Pinned-Dependencies",
        "Secret-Scanning",
    )
    out: dict[str, Any] = {"checks": {}, "urls": {}}
    for name in names:
        score = check_score(payload, name)
        out["checks"][name] = score
        url = check_evidence_url(payload, name)
        if url:
            out["urls"][name] = url
    return out


def score_meets(score: float | None, threshold: float) -> bool:
    return score is not None and score >= threshold
