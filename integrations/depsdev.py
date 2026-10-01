"""deps.dev API helpers (package-centric advisories / dependents)."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from integrations.http import http_get

UA = "oss-review-suite/1.0 (+https://github.com)"
DEPSDEV_API = "https://api.deps.dev/v3alpha"


def _get_json(url: str) -> tuple[int, Any]:
    status, data, _ = http_get(url, headers={"User-Agent": UA, "Accept": "application/json"})
    if status != 200 or not data:
        return status, None
    try:
        return status, json.loads(data.decode("utf-8"))
    except Exception:
        return status, None


def fetch_package(system: str, name: str) -> dict[str, Any]:
    """Best-effort package metadata. system e.g. cargo, pypi, npm, maven."""
    sys_q = quote(system, safe="")
    name_q = quote(name, safe="")
    status, data = _get_json(f"{DEPSDEV_API}/systems/{sys_q}/packages/{name_q}")
    return {"status": status, "data": data}


def fetch_version(system: str, name: str, version: str) -> dict[str, Any]:
    sys_q = quote(system, safe="")
    name_q = quote(name, safe="")
    ver_q = quote(version, safe="")
    status, data = _get_json(f"{DEPSDEV_API}/systems/{sys_q}/packages/{name_q}/versions/{ver_q}")
    return {"status": status, "data": data}


def fetch_dependents(system: str, name: str, version: str) -> dict[str, Any]:
    """GetDependents — distinct packages known to depend on this version."""
    sys_q = quote(system, safe="")
    name_q = quote(name, safe="")
    ver_q = quote(version, safe="")
    status, data = _get_json(
        f"{DEPSDEV_API}/systems/{sys_q}/packages/{name_q}/versions/{ver_q}:dependents"
    )
    return {"status": status, "data": data}


def advisory_count(version_payload: dict[str, Any]) -> int:
    data = version_payload.get("data") if isinstance(version_payload, dict) else None
    if not isinstance(data, dict):
        return 0
    adv = data.get("advisoryKeys") or data.get("advisories") or []
    return len(adv) if isinstance(adv, list) else 0


def dependent_count(dependents_payload: dict[str, Any]) -> int | None:
    data = dependents_payload.get("data") if isinstance(dependents_payload, dict) else None
    if not isinstance(data, dict):
        return None
    for key in ("dependentCount", "dependent_count", "count"):
        raw = data.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def fetch_registry_downloads(system: str, name: str) -> dict[str, Any]:
    """
    Best-effort download counts from public registries.
    Returns {status, downloads, source, url}.
    """
    system_l = (system or "").strip().lower()
    name_s = (name or "").strip()
    if not system_l or not name_s:
        return {"status": 0, "downloads": None, "source": "", "url": ""}

    if system_l in {"cargo", "crates"}:
        url = f"https://crates.io/api/v1/crates/{quote(name_s, safe='')}"
        status, data = _get_json(url)
        crate = data.get("crate") if isinstance(data, dict) else None
        downloads = None
        if isinstance(crate, dict):
            for key in ("recent_downloads", "downloads"):
                if crate.get(key) is not None:
                    try:
                        downloads = int(crate[key])
                        break
                    except (TypeError, ValueError):
                        pass
        return {
            "status": status,
            "downloads": downloads,
            "source": "crates.io",
            "url": f"https://crates.io/crates/{name_s}",
        }

    if system_l == "npm":
        url = f"https://api.npmjs.org/downloads/point/last-month/{quote(name_s, safe='')}"
        status, data = _get_json(url)
        downloads = None
        if isinstance(data, dict) and data.get("downloads") is not None:
            try:
                downloads = int(data["downloads"])
            except (TypeError, ValueError):
                downloads = None
        return {
            "status": status,
            "downloads": downloads,
            "source": "npm last-month",
            "url": f"https://www.npmjs.com/package/{name_s}",
        }

    if system_l == "pypi":
        url = f"https://pypistats.org/api/packages/{quote(name_s, safe='')}/recent"
        status, data = _get_json(url)
        downloads = None
        if isinstance(data, dict):
            inner = data.get("data") if isinstance(data.get("data"), dict) else data
            for key in ("last_month", "last_week", "last_day"):
                if isinstance(inner, dict) and inner.get(key) is not None:
                    try:
                        downloads = int(inner[key])
                        break
                    except (TypeError, ValueError):
                        pass
        return {
            "status": status,
            "downloads": downloads,
            "source": "pypistats recent",
            "url": f"https://pypi.org/project/{name_s}/",
        }

    return {"status": 0, "downloads": None, "source": "", "url": ""}
