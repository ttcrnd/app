"""Shared repo signal helpers used across pipeline sections."""

from __future__ import annotations

from typing import Any

from integrations.github import get as gh_get
from integrations.http import http_get

UA = "oss-review-suite/1.0 (+https://github.com)"

# Common unit-test / integration-test roots across ecosystems.
TEST_ROOT_CANDIDATES = (
    "tests",
    "test",
    "t",
    "Testing",
    "src/test",
    "src/tests",
    "__tests__",
    "spec",
    "Specs",
)

KNOWN_SECURITY_POLICY_URLS = {
    "openssl/openssl": "https://www.openssl.org/policies/security.html",
}


def detect_test_roots(owner: str, repo: str, *, ref: str | None = None) -> dict[str, Any]:
    """Return which test directories exist (best-effort contents API)."""
    found: dict[str, str] = {}
    for path in TEST_ROOT_CANDIDATES:
        params = {"ref": ref} if ref else None
        status, data, _ = gh_get(f"/repos/{owner}/{repo}/contents/{path}", params=params)
        if status == 200:
            found[path] = f"https://github.com/{owner}/{repo}/tree/{ref or 'HEAD'}/{path}"
    return {
        "found": found,
        "has_tests": bool(found),
        "primary": next(iter(found), None),
        "urls": list(found.values()),
    }


def detect_security_policy(owner: str, repo: str, *, ref: str | None = None) -> dict[str, Any]:
    """
    SECURITY.md may be absent while a security policy still exists via
    GitHub community profile, advisories page, or a well-known project URL.
    """
    out: dict[str, Any] = {
        "has_security_md": False,
        "security_md_path": None,
        "security_md_url": None,
        "community_profile": False,
        "policy_urls": [],
        "notes": [],
    }
    repo_key = f"{owner}/{repo}".lower()
    params = {"ref": ref} if ref else None
    for path in ("SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md", "security/SECURITY.md"):
        status, data, _ = gh_get(f"/repos/{owner}/{repo}/contents/{path}", params=params)
        if status == 200 and isinstance(data, dict):
            out["has_security_md"] = True
            out["security_md_path"] = path
            out["security_md_url"] = data.get("html_url") or (
                f"https://github.com/{owner}/{repo}/blob/{ref or 'HEAD'}/{path}"
            )
            out["policy_urls"].append(out["security_md_url"])
            break

    st_cp, cp, _ = gh_get(f"/repos/{owner}/{repo}/community/profile")
    if st_cp == 200 and isinstance(cp, dict):
        out["community_profile"] = True
        files = cp.get("files") if isinstance(cp.get("files"), dict) else {}
        sec = files.get("security") if isinstance(files, dict) else None
        if isinstance(sec, dict) and sec.get("url"):
            out["policy_urls"].append(str(sec["url"]))
            out["notes"].append("community/profile security file present")
            if not out["has_security_md"]:
                out["has_security_md"] = True
                out["security_md_url"] = str(sec["url"])

    known = KNOWN_SECURITY_POLICY_URLS.get(repo_key)
    if known:
        out["policy_urls"].append(known)
        out["notes"].append(f"known security policy URL for {repo_key}")

    # Always expose GH security hub as soft evidence.
    out["policy_urls"].append(f"https://github.com/{owner}/{repo}/security")
    out["policy_urls"].append(f"https://github.com/{owner}/{repo}/security/advisories")

    # Dedupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for u in out["policy_urls"]:
        if u and u not in seen:
            seen.add(u)
            uniq.append(u)
    out["policy_urls"] = uniq
    out["has_policy_signal"] = bool(
        out["has_security_md"] or known or out.get("community_profile")
    )
    return out


def detect_oss_fuzz_project(owner: str, repo: str) -> dict[str, Any]:
    """Match OSS-Fuzz via google/oss-fuzz projects/<name>/project.yaml (raw) + API."""
    name = (repo or "").strip().lower()
    out: dict[str, Any] = {
        "overview_hit": False,
        "oss_fuzz_dir": False,
        "project_report_url": None,
        "project_name": name,
        "urls": ["https://google.github.io/oss-fuzz/"],
        "notes": [],
    }
    if not name:
        return out

    # Prefer raw GitHub (no API quota) — exists for enrolled projects.
    raw_url = f"https://raw.githubusercontent.com/google/oss-fuzz/master/projects/{name}/project.yaml"
    s_raw, body, _ = http_get(raw_url, headers={"User-Agent": UA}, timeout=20)
    if s_raw == 200 and body:
        out["oss_fuzz_dir"] = True
        out["overview_hit"] = True
        out["project_yaml"] = body.decode("utf-8", errors="replace")[:2000]
        out["urls"].append(f"https://github.com/google/oss-fuzz/tree/master/projects/{name}")
        out["urls"].append(raw_url)

    status, data, _ = gh_get(f"/repos/google/oss-fuzz/contents/projects/{name}")
    if status == 200:
        out["oss_fuzz_dir"] = True
        out["urls"].append(f"https://github.com/google/oss-fuzz/tree/master/projects/{name}")
    elif status and status not in (404,) and not out["oss_fuzz_dir"]:
        out["notes"].append(f"oss-fuzz contents status={status}")

    s1, body, _ = http_get(
        "https://oss-fuzz-introspector.storage.googleapis.com/projects-overview.json",
        headers={"User-Agent": UA},
        timeout=25,
    )
    if s1 == 200 and isinstance(body, (bytes, bytearray)):
        import json

        try:
            payload = json.loads(body.decode("utf-8", errors="replace"))
        except Exception:
            payload = {}
        projects = payload.get("projects") if isinstance(payload, dict) else None
        if isinstance(projects, list):
            for row in projects:
                if not isinstance(row, dict):
                    continue
                proj = str(row.get("project") or "").lower()
                if proj == name or proj.replace("-", "") == name.replace("-", ""):
                    out["overview_hit"] = True
                    out["overview_row"] = row
                    break
    elif s1:
        out["notes"].append(f"overview.json status={s1}")

    candidate = (
        f"https://oss-fuzz-introspector.storage.googleapis.com/{name}/latest/report.html"
    )
    s2, _, _ = http_get(candidate, headers={"User-Agent": UA}, timeout=15)
    if s2 == 200:
        out["project_report_url"] = candidate
        out["urls"].append(candidate)

    out["present"] = bool(out["overview_hit"] or out["oss_fuzz_dir"] or out["project_report_url"])
    return out


def detect_release_attestations(owner: str, repo: str, release: dict | None) -> dict[str, Any]:
    """Sigstore-ish release assets + best-effort attestation list endpoint."""
    out: dict[str, Any] = {
        "asset_urls": [],
        "attestation_status": 0,
        "attestation_count": None,
        "urls": [],
        "notes": [],
    }
    assets = (release or {}).get("assets") or []
    tokens = ("sigstore", "sig", "sbom", "provenance", "intoto", "attestation", ".pem", "cosign")
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "").lower()
        url = asset.get("browser_download_url") or asset.get("url")
        if url and any(t in name for t in tokens):
            out["asset_urls"].append(str(url))
    if out["asset_urls"]:
        out["urls"].extend(out["asset_urls"][:5])
        out["notes"].append(f"release assets hinting signatures/SBOM: {len(out['asset_urls'])}")

    # Optional attestations API (may 404/403 without perms).
    st, data, _ = gh_get(f"/repos/{owner}/{repo}/attestations", params={"per_page": 5})
    out["attestation_status"] = st
    if st == 200 and isinstance(data, dict):
        attestations = data.get("attestations")
        if isinstance(attestations, list):
            out["attestation_count"] = len(attestations)
            out["urls"].append(f"https://github.com/{owner}/{repo}/attestations")
    elif st in (401, 403, 404):
        out["notes"].append(f"attestations status={st}")

    out["has_signal"] = bool(out["asset_urls"] or (out["attestation_count"] or 0) > 0)
    return out
