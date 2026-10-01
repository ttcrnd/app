"""SECURITY.md / VDP content heuristics."""

from __future__ import annotations

import re
from typing import Any


def parse_security_md(text: str) -> dict[str, Any]:
    body = text or ""
    lower = body.lower()
    signals = {
        "has_security_email": bool(re.search(r"security\s*@|\bsecurity@", lower)),
        "has_pgp": bool(re.search(r"\bpgp\b|\bgpg\b|openpgp", lower)),
        "has_private_reporting": bool(
            re.search(r"private vulnerability|vulnerability disclosure|vdp\b", lower)
        ),
        "has_sla": bool(re.search(r"\bsla\b|\d+\s*(business\s+)?days?|72\s*hours?", lower)),
        "has_backport": bool(re.search(r"backport|supported versions|security support", lower)),
        "has_security_team": bool(re.search(r"security team|product security|psirt", lower)),
        "has_audit_mention": bool(
            re.search(r"\baudit\b|cure53|trail of bits|ncc group|ostif", lower)
        ),
    }
    strength = sum(1 for v in signals.values() if v)
    return {"signals": signals, "strength": strength, "process_like": strength >= 2}
