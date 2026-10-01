"""Shared crypto / test-vector / ban-list signals for section 5 (E17)."""

from __future__ import annotations

import re
from typing import Any

from pipeline.misuse_scan import scan_text

_VECTOR_RE = re.compile(
    r"wycheproof|nist\s*kat|known[-_ ]answer|test[-_ ]vectors?|/vectors?/|testdata.*crypto",
    re.I,
)
_TIMING_RE = re.compile(r"\bdudect\b|\bctgrind\b|\bconstant[-_ ]time\b|\bsubtle\b", re.I)
_BAN_RE = re.compile(
    r"\b(ECB|MD5|SHA-?1|DES|3DES|RC4)\b.*(禁用|deprecated|disabled|forbidden|ban|nesmí|zakáz)",
    re.I,
)
_BAN_ALT_RE = re.compile(
    r"(deprecated|disabled|do not use|avoid).{0,40}\b(ECB|MD5|SHA-?1|DES|RC4)\b"
    r"|\b(ECB|MD5|SHA-?1|DES|RC4)\b.{0,40}(deprecated|disabled|do not use|avoid)",
    re.I,
)


def scan_crypto_docs(docs: list[tuple[str, str]]) -> dict[str, Any]:
    """
    Aggregate signals from (path, text) docs.
    Returns structured hits for 5-3 / 5-7 / 5-9 / 5-10 / 5-14.
    """
    vector_hits: list[dict[str, str]] = []
    timing_hits: list[dict[str, str]] = []
    ban_hits: list[dict[str, str]] = []
    misuse_hits: list[dict[str, Any]] = []

    for path, body in docs:
        text = body or ""
        if not text:
            continue
        for match in _VECTOR_RE.finditer(text):
            vector_hits.append(_snip(path, text, match.start(), match.end()))
            if len(vector_hits) >= 8:
                break
        for match in _TIMING_RE.finditer(text):
            timing_hits.append(_snip(path, text, match.start(), match.end()))
            if len(timing_hits) >= 8:
                break
        for cre in (_BAN_RE, _BAN_ALT_RE):
            for match in cre.finditer(text):
                ban_hits.append(_snip(path, text, match.start(), match.end()))
                if len(ban_hits) >= 8:
                    break
        misuse_hits.extend(scan_text(text, source=path))
        if len(misuse_hits) >= 30:
            break

    return {
        "has_vectors": bool(vector_hits),
        "has_timing_tests": bool(timing_hits),
        "has_ban_list": bool(ban_hits),
        "vector_hits": vector_hits[:5],
        "timing_hits": timing_hits[:5],
        "ban_hits": ban_hits[:5],
        "misuse_hits": misuse_hits[:20],
        "misuse_count": len(misuse_hits),
    }


def _snip(path: str, text: str, start: int, end: int) -> dict[str, str]:
    a = max(0, start - 36)
    b = min(len(text), end + 36)
    return {
        "source": path,
        "snippet": text[a:b].replace("\n", " ").strip(),
    }


def crypto_signals_note(signals: dict[str, Any]) -> str:
    parts: list[str] = []
    if signals.get("has_vectors"):
        parts.append("Nalezeny zmínky o test vectors / Wycheproof / KAT.")
    if signals.get("has_timing_tests"):
        parts.append("Nalezeny constant-time / dudect / subtle signály.")
    if signals.get("has_ban_list"):
        parts.append("Docs zmiňují ban/deprecation slabých algoritmů.")
    if int(signals.get("misuse_count") or 0) > 0:
        parts.append(f"Misuse scan hits≈{signals.get('misuse_count')} (CONFIRM).")
    return " ".join(parts)
