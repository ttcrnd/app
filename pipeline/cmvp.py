"""NIST CMVP search helpers (prefill evidence only)."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote_plus

from integrations.http import http_get

UA = "oss-review-suite/1.0 (+https://github.com)"
SEARCH_UI = (
    "https://csrc.nist.gov/projects/cryptographic-module-validation-program/"
    "validated-modules/search"
)


def search_cmvp(product_name: str) -> dict[str, Any]:
    """
    Best-effort search. NIST HTML search is brittle; we always return a search URL
    and optionally note if the name appears in a lightweight fetch.
    """
    query = (product_name or "").strip()
    # Prefer well-known FIPS product names for common crypto libs.
    aliases = {
        "openssl": "OpenSSL FIPS",
        "libressl": "LibreSSL",
        "boringssl": "BoringSSL",
    }
    search_query = aliases.get(query.lower(), query) if query else ""
    search_url = (
        f"{SEARCH_UI}?SearchMode=Advanced&Keyword={quote_plus(search_query)}"
        if search_query
        else SEARCH_UI
    )
    hit = False
    status = 0
    if search_query:
        # Public keyword endpoint varies; try a HEAD/GET of search page as availability signal only.
        status, body, _ = http_get(search_url, headers={"User-Agent": UA}, timeout=20)
        if status == 200 and body:
            text = body.decode("utf-8", errors="ignore")
            # Very weak positive: page contains the keyword (often true for search UI chrome)
            hit = bool(re.search(re.escape(query), text, re.I)) and "validated" in text.lower()
    return {
        "status": status,
        "query": search_query or query,
        "search_url": search_url,
        "possible_hit": hit,
        "note": (
            "CMVP: možný hit v odpovědi stránky — ověř mapování verze/platformy ručně."
            if hit
            else "CMVP: otevři oficiální vyhledávání a ověř modul/verzi ručně."
        ),
    }


def dumps_safe(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "{}"
