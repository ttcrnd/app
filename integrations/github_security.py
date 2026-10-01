"""GitHub Security features collector (E15) — graceful without token."""

from __future__ import annotations

from typing import Any

from integrations.github import get as gh_get


def collect_github_security(owner: str, repo: str) -> dict[str, Any]:
    """
    Best-effort: private vulnerability reporting, published advisories,
    Dependabot alerts summary. Never raises; 403/404 → degraded notes.
    """
    out: dict[str, Any] = {
        "available": False,
        "private_reporting": None,
        "advisories_count": None,
        "advisories_status": 0,
        "dependabot_open": None,
        "dependabot_by_severity": {},
        "dependabot_status": 0,
        "notes": [],
        "urls": [
            f"https://github.com/{owner}/{repo}/security",
            f"https://github.com/{owner}/{repo}/security/advisories",
        ],
    }

    # Repo payload may expose private_vulnerability_reporting_enabled (newer API).
    st_repo, repo_data, _ = gh_get(f"/repos/{owner}/{repo}")
    if st_repo == 200 and isinstance(repo_data, dict):
        out["available"] = True
        if "private_vulnerability_reporting_enabled" in repo_data:
            out["private_reporting"] = bool(repo_data.get("private_vulnerability_reporting_enabled"))
        security = repo_data.get("security_and_analysis")
        if isinstance(security, dict):
            out["available"] = True
            for key in ("dependabot_security_updates", "secret_scanning", "secret_scanning_push_protection"):
                entry = security.get(key)
                if isinstance(entry, dict) and entry.get("status"):
                    out["notes"].append(f"{key}={entry.get('status')}")

    st_pvr, pvr_data, _ = gh_get(f"/repos/{owner}/{repo}/private-vulnerability-reporting")
    if st_pvr == 200 and isinstance(pvr_data, dict):
        out["private_reporting"] = bool(pvr_data.get("enabled"))
        out["available"] = True
    elif st_pvr in (401, 403, 404):
        out["notes"].append(f"private-vulnerability-reporting status={st_pvr}")

    st_adv, adv_data, _ = gh_get(
        f"/repos/{owner}/{repo}/security-advisories",
        params={"per_page": 30, "state": "published"},
    )
    out["advisories_status"] = st_adv
    if st_adv == 200 and isinstance(adv_data, list):
        out["advisories_count"] = len(adv_data)
        out["available"] = True
    elif st_adv in (401, 403, 404):
        out["notes"].append(f"security-advisories status={st_adv}")

    st_dep, dep_data, _ = gh_get(
        f"/repos/{owner}/{repo}/dependabot/alerts",
        params={"state": "open", "per_page": 50},
    )
    out["dependabot_status"] = st_dep
    if st_dep == 200 and isinstance(dep_data, list):
        out["dependabot_open"] = len(dep_data)
        by_sev: dict[str, int] = {}
        for alert in dep_data:
            if not isinstance(alert, dict):
                continue
            sev = str(
                ((alert.get("security_advisory") or {}) or {}).get("severity")
                or alert.get("severity")
                or "unknown"
            ).lower()
            by_sev[sev] = by_sev.get(sev, 0) + 1
        out["dependabot_by_severity"] = by_sev
        out["available"] = True
        out["urls"].append(f"https://github.com/{owner}/{repo}/security/dependabot")
    elif st_dep in (401, 403, 404):
        out["notes"].append(f"dependabot/alerts status={st_dep} (token/perm)")

    return out


def security_features_note(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    if payload.get("private_reporting") is True:
        parts.append("Private vulnerability reporting: zapnuto.")
    elif payload.get("private_reporting") is False:
        parts.append("Private vulnerability reporting: vypnuto.")
    if isinstance(payload.get("advisories_count"), int):
        parts.append(f"Published advisories: {payload['advisories_count']}.")
    if isinstance(payload.get("dependabot_open"), int):
        sev = payload.get("dependabot_by_severity") or {}
        sev_txt = ", ".join(f"{k}={v}" for k, v in sorted(sev.items())) if sev else "none"
        parts.append(f"Open Dependabot alerts: {payload['dependabot_open']} ({sev_txt}).")
    elif payload.get("dependabot_status") in (401, 403):
        parts.append("Dependabot alerts nedostupné (token/oprávnění).")
    return " ".join(parts)
