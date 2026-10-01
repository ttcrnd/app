from __future__ import annotations

import json
from typing import Any

_USE_REQUESTS = False
try:
    import requests

    _USE_REQUESTS = True
except Exception:
    import urllib.error
    import urllib.parse
    import urllib.request


def _to_dict_headers(hdrs) -> dict[str, str]:
    try:

        return {k: str(v) for k, v in hdrs.items()}
    except Exception:

        try:
            return {k: str(v) for k, v in hdrs.items()}
        except Exception:
            return dict(hdrs or {})


def http_get(
    url: str, headers: dict[str, str] | None = None, timeout: int = 30
) -> tuple[int, bytes, dict[str, str]]:
    if _USE_REQUESTS:
        resp = requests.get(url, headers=headers or {}, timeout=timeout)
        return resp.status_code, resp.content or b"", _to_dict_headers(resp.headers)

    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read() or b"", _to_dict_headers(r.headers)
    except urllib.error.HTTPError as e:
        data = e.read() if e.fp else b""
        return e.code, data, _to_dict_headers(getattr(e, "headers", {}))
    except urllib.error.URLError:
        return 0, b"", {}


def http_head(
    url: str, headers: dict[str, str] | None = None, timeout: int = 15
) -> tuple[int, dict[str, str]]:
    if _USE_REQUESTS:
        resp = requests.head(url, headers=headers or {}, allow_redirects=True, timeout=timeout)
        return resp.status_code, _to_dict_headers(resp.headers)
    req = urllib.request.Request(url, headers=headers or {}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), _to_dict_headers(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, _to_dict_headers(getattr(e, "headers", {}))
    except urllib.error.URLError:
        return 0, {}


def http_post_json(
    url: str, payload: dict[str, Any], headers: dict[str, str] | None = None, timeout: int = 30
) -> tuple[int, bytes, dict[str, str]]:
    base = {"Accept": "application/json", "Content-Type": "application/json"}
    if headers:
        base.update(headers)
    body = json.dumps(payload).encode("utf-8")
    if _USE_REQUESTS:
        resp = requests.post(url, data=body, headers=base, timeout=timeout)
        return resp.status_code, resp.content or b"", _to_dict_headers(resp.headers)
    req = urllib.request.Request(url, data=body, headers=base, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read() or b"", _to_dict_headers(r.headers)
    except urllib.error.HTTPError as e:
        data = e.read() if e.fp else b""
        return e.code, data, _to_dict_headers(getattr(e, "headers", {}))
    except urllib.error.URLError:
        return 0, b"", {}


def get_json(
    url: str, headers: dict[str, str] | None = None, timeout: int = 30
) -> tuple[int, dict[str, Any] | list | None, dict[str, str]]:
    status, data, hdrs = http_get(url, headers=headers, timeout=timeout)
    if not data:
        return status, None, hdrs
    try:
        return status, json.loads(data.decode("utf-8")), hdrs
    except Exception:
        return status, None, hdrs


def get_text(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    max_bytes: int | None = None,
) -> tuple[int, str | None, dict[str, str]]:
    status, data, hdrs = http_get(url, headers=headers, timeout=timeout)
    if max_bytes is not None and data:
        data = data[:max_bytes]
    try:
        if data:

            text = data.decode("utf-8", errors="replace")
        else:
            text = None
    except Exception:
        text = None
    return status, text, hdrs
