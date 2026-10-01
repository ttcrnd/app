"""Heuristic scan for dangerous crypto / TLS patterns in examples and docs."""

from __future__ import annotations

import re
from typing import Any

# Patterns that commonly indicate insecure examples (not proof of API quality).
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ECB", re.compile(r"\bAES[_/]?ECB\b|\bMODE_ECB\b|\b/ECB\b", re.I)),
    ("MD5", re.compile(r"\bMD5\b|\bhashlib\.md5\b|\bMessageDigest\.getInstance\([\"']MD5", re.I)),
    ("DES", re.compile(r"\bDES\b|\b3DES\b|\bDESede\b", re.I)),
    ("verify_false", re.compile(r"verify\s*=\s*False|InsecureSkipVerify\s*[:=]\s*true", re.I)),
    ("hardcoded_iv", re.compile(r"\bIV\s*=\s*[\"'][0-9a-fA-F]{8,}[\"']", re.I)),
]


def scan_text(text: str, *, source: str = "") -> list[dict[str, Any]]:
    """Return list of {pattern, source, snippet} hits."""
    if not text:
        return []
    hits: list[dict[str, Any]] = []
    for label, cre in _PATTERNS:
        for match in cre.finditer(text):
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 40)
            hits.append(
                {
                    "pattern": label,
                    "source": source,
                    "snippet": text[start:end].replace("\n", " ").strip(),
                }
            )
            if len(hits) >= 40:
                return hits
    return hits


def scan_documents(docs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """docs: list of (path_or_url, text)."""
    all_hits: list[dict[str, Any]] = []
    for path, body in docs:
        all_hits.extend(scan_text(body or "", source=path))
        if len(all_hits) >= 40:
            break
    return all_hits
