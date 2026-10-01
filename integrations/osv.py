"""
Vulnerability helpers (OSV.dev integration).
"""

from __future__ import annotations

import json
from typing import Any

from integrations.http import http_post_json

OSV_API = "https://api.osv.dev/v1/query"


def osv_query_repo(repo_html_url: str) -> dict[str, Any]:
    payload = {"repo": repo_html_url}
    status, data, _ = http_post_json(
        OSV_API, payload, headers={"User-Agent": "oss-review-suite/1.0"}
    )
    if status == 200 and data:
        try:
            return json.loads(data.decode("utf-8"))
        except Exception:
            return {}
    return {}
