"""
Utilities for repeated evidence processing patterns across scripts.
"""

from __future__ import annotations

import re
from typing import Any


def search_release_assets_for_patterns(
    releases: list[dict[str, Any]], patterns: list[str]
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for rel in releases or []:
        assets = rel.get("assets", []) or []
        for a in assets:
            name = a.get("name", "")
            url = a.get("browser_download_url", "")
            for pat in patterns or []:
                if re.search(pat, name, re.IGNORECASE):
                    findings.append({"release_tag": rel.get("tag_name"), "asset": name, "url": url})
    return findings


def search_tree_for_patterns(
    tree: list[dict[str, Any]], patterns: list[str]
) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    for node in tree or []:
        if node.get("type") != "blob":
            continue
        path = node.get("path", "")
        for pat in patterns or []:
            if re.search(pat, path, re.IGNORECASE):
                matches.append({"path": path, "url": None})
    return matches


def make_evidence_list(urls_or_texts: list[str]) -> list[str]:
    uniq, out = set(), []
    for x in urls_or_texts or []:
        if not x:
            continue
        s = str(x).strip()
        if s and s not in uniq:
            uniq.add(s)
            out.append(s)
    return out
