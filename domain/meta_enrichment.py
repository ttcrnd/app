"""Canonical evidence pack + META enrichment for review forms."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from urllib.parse import quote


def _iso_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return ""


def infer_library_type(form_obj: dict[str, Any]) -> str:
    """Best-effort typ knihovny from languages / topics / package system."""
    meta = form_obj.get("meta") if isinstance(form_obj.get("meta"), dict) else {}
    existing = str(meta.get("library_type") or meta.get("type") or "").strip()
    if existing:
        return existing

    langs: dict[str, Any] = {}
    topics: list[str] = []
    package_system = ""
    for sec in form_obj.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        sm = sec.get("meta") if isinstance(sec.get("meta"), dict) else {}
        if isinstance(sm.get("languages"), dict) and not langs:
            langs = sm["languages"]
        if isinstance(sm.get("topics"), list) and not topics:
            topics = [str(t).lower() for t in sm["topics"] if t]
        pkg = sm.get("package_info") if isinstance(sm.get("package_info"), dict) else {}
        if pkg.get("system") and not package_system:
            package_system = str(pkg.get("system"))

    topic_blob = " ".join(topics)
    cryptoish = any(
        token in topic_blob
        for token in ("crypto", "cryptography", "tls", "ssl", "pgp", "security")
    )
    top_lang = ""
    if langs:
        top_lang = max(langs.items(), key=lambda kv: float(kv[1] or 0))[0]

    if cryptoish and top_lang:
        return f"kryptografická knihovna ({top_lang})"
    if cryptoish:
        return "kryptografická knihovna"
    if package_system:
        return f"softwarová knihovna ({package_system})"
    if top_lang:
        return f"softwarová knihovna ({top_lang})"
    return "softwarová knihovna"


def _first_http_lines(*blobs: Any, limit: int = 20) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for blob in blobs:
        text = blob if isinstance(blob, str) else ""
        if isinstance(blob, list):
            parts: list[str] = []
            for item in blob:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("url"):
                    parts.append(str(item["url"]))
            text = "\n".join(parts)
        for line in text.replace(";", "\n").splitlines():
            url = line.strip()
            if not url.startswith("http"):
                continue
            if url in seen:
                continue
            seen.add(url)
            out.append(url)
            if len(out) >= limit:
                return out
    return out


def build_evidence_pack(form_obj: dict[str, Any]) -> list[dict[str, str]]:
    """3–5 canonical URLs for the work strip (label + url)."""
    meta = form_obj.get("meta") if isinstance(form_obj.get("meta"), dict) else {}
    existing = meta.get("evidence_pack")
    if isinstance(existing, list) and existing:
        cleaned: list[dict[str, str]] = []
        for item in existing:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            label = str(item.get("label") or "").strip() or "Odkaz"
            if url.startswith("http"):
                cleaned.append({"label": label, "url": url})
            if len(cleaned) >= 5:
                break
        if cleaned:
            return cleaned

    repo = str(meta.get("repo") or "").strip()
    owner, name = (repo.split("/", 1) + [""])[:2] if "/" in repo else ("", "")
    candidates: list[tuple[str, str]] = []

    if owner and name:
        candidates.append(("GitHub", f"https://github.com/{owner}/{name}"))
        candidates.append(
            (
                "Scorecard",
                f"https://securityscorecards.dev/viewer/?uri=github.com/{quote(owner)}/{quote(name)}",
            )
        )
        candidates.append(("SECURITY.md", f"https://github.com/{owner}/{name}/blob/HEAD/SECURITY.md"))
        candidates.append(("Releases", f"https://github.com/{owner}/{name}/releases"))

    # Harvest known URLs from questions / section meta.
    harvested: list[str] = []
    for sec in form_obj.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        sm = sec.get("meta") if isinstance(sec.get("meta"), dict) else {}
        for key in ("badge_url", "registry_url", "depsdev_url", "scorecard_url"):
            val = sm.get(key)
            if isinstance(val, str) and val.startswith("http"):
                harvested.append(val)
        for q in sec.get("questions") or []:
            if not isinstance(q, dict):
                continue
            harvested.extend(_first_http_lines(q.get("evidence"), limit=8))

    label_for = {
        "bestpractices.coreinfrastructure.org": "OpenSSF Badge",
        "deps.dev": "deps.dev",
        "crates.io": "crates.io",
        "pypi.org": "PyPI",
        "npmjs.com": "npm",
        "csrc.nist.gov": "NIST CMVP",
        "securityscorecards.dev": "Scorecard",
        "api.securityscorecards.dev": "Scorecard",
    }
    for url in harvested:
        low = url.lower()
        label = "Evidence"
        for needle, pretty in label_for.items():
            if needle in low:
                label = pretty
                break
        if "SECURITY.md" in url:
            label = "SECURITY.md"
        candidates.append((label, url))

    pack: list[dict[str, str]] = []
    seen: set[str] = set()
    for label, url in candidates:
        key = url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        pack.append({"label": label, "url": url})
        if len(pack) >= 5:
            break
    return pack


def enrich_form_meta(form_obj: dict[str, Any]) -> dict[str, Any]:
    """Fill META fields used by PDF/UI without inventing methodology ratings."""
    if not isinstance(form_obj, dict):
        return form_obj
    meta = form_obj.setdefault("meta", {})
    if not isinstance(meta, dict):
        return form_obj

    if not str(meta.get("assessment_date") or "").strip():
        meta["assessment_date"] = (
            _iso_date(meta.get("started_at"))
            or _iso_date(meta.get("finished_at"))
            or date.today().isoformat()
        )

    if not str(meta.get("library_type") or meta.get("type") or "").strip():
        inferred = infer_library_type(form_obj)
        meta["library_type"] = inferred
        meta["type"] = inferred

    if not str(meta.get("publisher") or meta.get("owner") or "").strip():
        repo = str(meta.get("repo") or "").strip()
        if "/" in repo:
            meta["publisher"] = repo.split("/", 1)[0]
            meta.setdefault("owner", meta["publisher"])

    if not str(meta.get("name") or meta.get("library_name") or "").strip():
        repo = str(meta.get("repo") or "").strip()
        if "/" in repo:
            meta["name"] = repo.split("/", 1)[1]
            meta["library_name"] = meta["name"]

    meta["evidence_pack"] = build_evidence_pack(form_obj)
    return form_obj


def diff_form_ratings(
    current: dict[str, Any],
    previous: dict[str, Any],
) -> list[dict[str, str]]:
    """Compare question ratings between two forms (best-effort)."""
    prev_map: dict[str, str] = {}
    for sec in previous.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        for q in sec.get("questions") or []:
            if not isinstance(q, dict):
                continue
            qid = str(q.get("id") or "").strip()
            if qid:
                prev_map[qid] = str(q.get("rating") or "").strip()

    changes: list[dict[str, str]] = []
    for sec in current.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        for q in sec.get("questions") or []:
            if not isinstance(q, dict):
                continue
            qid = str(q.get("id") or "").strip()
            if not qid or qid not in prev_map:
                continue
            cur = str(q.get("rating") or "").strip()
            old = prev_map[qid]
            if cur != old:
                changes.append({"id": qid, "from": old or "—", "to": cur or "—"})
    return changes
