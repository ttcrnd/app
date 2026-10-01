"""OpenSSF Best Practices Badge lookup (evidence only, not methodology grade)."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from integrations.http import http_get

UA = "oss-review-suite/1.0 (+https://github.com)"


def lookup_badge(owner: str, repo: str) -> dict[str, Any]:
    """
    Best-effort: query projects.json filtered by repo URL.
    Returns {status, tier, url, data}.
    """
    repo_url = f"https://github.com/{owner}/{repo}"
    # Public JSON endpoint used by bestpractices.dev
    url = (
        "https://www.bestpractices.dev/projects.json"
        f"?pq={quote(repo_url)}"
    )
    status, raw, _ = http_get(url, headers={"User-Agent": UA, "Accept": "application/json"})
    tier = None
    project_url = None
    data = None
    if status == 200 and raw:
        try:
            data = json.loads(raw.decode("utf-8"))
            items = data if isinstance(data, list) else (data.get("projects") or [])
            for item in items or []:
                if not isinstance(item, dict):
                    continue
                homepage = str(item.get("repo_url") or item.get("homepage_url") or "")
                if owner.lower() in homepage.lower() and repo.lower() in homepage.lower():
                    tier = item.get("badge_level") or item.get("achieved_status")
                    pid = item.get("id")
                    if pid is not None:
                        project_url = f"https://www.bestpractices.dev/projects/{pid}"
                    break
        except Exception:
            data = None
    return {"status": status, "tier": tier, "url": project_url, "data": data}
