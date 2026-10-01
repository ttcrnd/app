from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

from utils import httputils

GITHUB_API = os.environ.get("GITHUB_API", "https://api.github.com")
UA = "oss-review-suite/1.0 (+https://github.com)"


def _token_or_env(token: str | None) -> str | None:
    if token:
        return token
    env_tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    return env_tok.strip() if env_tok else None


def default_headers(
    token: str | None = None,
    accept_preview: bool = False,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    h: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "User-Agent": UA,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    tok = _token_or_env(token)
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    if accept_preview:
        h["Accept"] = "application/vnd.github.text-match+json"
    if extra:
        h.update(extra)
    return h


def get(
    path_or_url: str,
    params: dict[str, Any] | None = None,
    token: str | None = None,
    accept_preview: bool = False,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, Any, dict[str, str]]:
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        url = path_or_url
    else:
        url = f"{GITHUB_API}{path_or_url}"
        if params:
            url += "?" + urlencode(params)
    headers = default_headers(token, accept_preview, extra_headers)
    return httputils.get_json(url, headers=headers)


def paginate(
    path: str,
    params: dict[str, Any] | None = None,
    token: str | None = None,
    per_page: int = 100,
    max_pages: int = 10,
    accept_preview: bool = False,
) -> list[Any]:
    items: list[Any] = []
    page = 1
    params = dict(params or {})
    while page <= max_pages:
        params.update({"per_page": str(per_page), "page": str(page)})
        status, data, _ = get(path, params=params, token=token, accept_preview=accept_preview)
        if status != 200:
            break
        if not isinstance(data, list) or not data:
            if isinstance(data, list):
                items.extend(data)
            break
        items.extend(data)
        if len(data) < per_page:
            break
        page += 1
    return items


def get_full_url_json(
    url: str, token: str | None = None, accept: str | None = None
) -> tuple[int, Any, dict[str, str]]:
    headers = default_headers(token)
    if accept:
        headers["Accept"] = accept
    return httputils.get_json(url, headers=headers)


def http_get_full(
    url: str, token: str | None = None, accept: str | None = None
) -> tuple[int, bytes, dict[str, str]]:
    headers = default_headers(token)
    if accept:
        headers["Accept"] = accept
    status, data, hdrs = httputils.http_get(url, headers=headers)
    return status, data, hdrs


def search_code(
    owner: str,
    repo: str,
    query: str,
    per_page: int = 10,
    token: str | None = None,
    accept_preview: bool = True,
) -> Any:
    q = f"{query} repo:{owner}/{repo}"
    status, data, _ = get(
        "/search/code",
        params={"q": q, "per_page": per_page},
        token=token,
        accept_preview=accept_preview,
    )
    return data


def repo_file_exists(owner: str, repo: str, path: str, token: str | None = None) -> bool:
    status, data, _ = get(f"/repos/{owner}/{repo}/contents/{path}", token=token)
    return (
        status == 200 and isinstance(data, dict) and ("download_url" in data or "content" in data)
    )


def list_dir(
    owner: str, repo: str, path: str, ref: str | None = None, token: str | None = None
) -> list[dict[str, Any]]:
    params = {"ref": ref} if ref else None
    status, data, _ = get(f"/repos/{owner}/{repo}/contents/{path}", params=params, token=token)
    if status == 200:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    return []


def get_file(
    owner: str, repo: str, path: str, ref: str | None = None, token: str | None = None
) -> dict[str, Any] | None:
    params = {"ref": ref} if ref else None
    status, data, _ = get(f"/repos/{owner}/{repo}/contents/{path}", params=params, token=token)
    if status == 200 and isinstance(data, dict):
        return data
    return None


def actions_exists(owner: str, repo: str, token: str | None = None) -> bool:
    status, data, _ = get(
        f"/repos/{owner}/{repo}/actions/runs", params={"per_page": 1}, token=token
    )
    if isinstance(data, dict) and ("workflow_runs" in data or int(data.get("total_count", 0)) >= 0):
        return True

    items = search_code(owner, repo, "path:.github/workflows", per_page=1, token=token)
    try:
        return bool((items or {}).get("items"))
    except Exception:
        return False


def get_branch_protection(
    owner: str, repo: str, branch: str, token: str | None = None
) -> dict[str, Any]:
    """Return {status, data}. 404/403 → data None (graceful)."""
    status, data, _ = get(
        f"/repos/{owner}/{repo}/branches/{quote_path(branch)}/protection",
        token=token,
    )
    if status == 200 and isinstance(data, dict):
        return {"status": status, "data": data}
    return {"status": status, "data": None}


def quote_path(segment: str) -> str:
    from urllib.parse import quote

    return quote(segment, safe="")


def normalize_branch_protection(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = (payload or {}).get("data") if isinstance(payload, dict) else None
    out: dict[str, Any] = {
        "available": False,
        "required_approving_review_count": None,
        "require_code_owner_reviews": None,
        "required_status_checks": None,
        "allow_force_pushes": None,
    }
    if not isinstance(data, dict):
        return out
    out["available"] = True
    pr = data.get("required_pull_request_reviews") or {}
    if isinstance(pr, dict):
        out["required_approving_review_count"] = pr.get("required_approving_review_count")
        out["require_code_owner_reviews"] = pr.get("require_code_owner_reviews")
    checks = data.get("required_status_checks") or {}
    if isinstance(checks, dict):
        contexts = checks.get("contexts") or checks.get("checks") or []
        out["required_status_checks"] = list(contexts) if isinstance(contexts, list) else []
    afp = data.get("allow_force_pushes")
    if isinstance(afp, dict):
        out["allow_force_pushes"] = afp.get("enabled")
    elif isinstance(afp, bool):
        out["allow_force_pushes"] = afp
    return out
