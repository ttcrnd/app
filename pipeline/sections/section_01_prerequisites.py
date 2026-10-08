#!/usr/bin/env python3

import argparse
import datetime
import functools
import json
import os
import sys
import time
import urllib.parse
import urllib.request

try:
    from pipeline.localization import text
except ModuleNotFoundError:  # pragma: no cover
    try:
        from localization import text
    except ModuleNotFoundError:  # pragma: no cover
        from scripts.localization import text  # type: ignore

from integrations.github import default_headers as _gh_default_headers
from integrations.github import get as _gh_get
from integrations.github import paginate as _gh_paginate

API = "https://api.github.com"

RATING_MEETS = text("common", "ratings", "meets")
RATING_PARTIAL = text("common", "ratings", "partial")
RATING_NOT_MET = text("common", "ratings", "not_met")
ERROR_FETCH_NOTE = text("common", "errors", "fetching")


def gh_headers(token=None, accept_preview=False):
    return _gh_default_headers(token=token, accept_preview=accept_preview)


def gh_get(url, token=None, accept_preview=False):
    status, data, _ = _gh_get(
        url if url.startswith("http") else f"{API}{url}", token=token, accept_preview=accept_preview
    )
    if status != 200:
        raise urllib.error.HTTPError(
            url, status, text("common", "errors", "github_api"), hdrs=None, fp=None
        )
    return data


def gh_paginate(url, token=None, accept_preview=False, max_pages=10):
    if url.startswith("http"):
        try:
            path = url.split(API, 1)[1]
            return _gh_paginate(
                path, token=token, per_page=100, max_pages=max_pages, accept_preview=accept_preview
            )
        except Exception:
            data = gh_get(url, token=token, accept_preview=accept_preview)
            return data if isinstance(data, list) else []
    return _gh_paginate(
        url, token=token, per_page=100, max_pages=max_pages, accept_preview=accept_preview
    )


def iso_now():
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _eval_log(fn):
    @functools.wraps(fn)
    def _wrap(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
            try:
                print(text("common", "evaluate_done", function_name=fn.__name__))
            except Exception:
                pass
            return result
        except Exception:
            name = fn.__name__
            # Question-level fallback: return empty evidence list, rating 'not met', standard note
            if name.startswith("evaluate_q_1_"):
                return ([], RATING_NOT_MET, ERROR_FETCH_NOTE)
            # Aggregator fallback: build a minimal sekce_1 with defaulted questions
            if name == "build_output":
                try:
                    owner, repo = args[0], args[1]
                except Exception:
                    owner, repo = "", ""
                sekce_1 = json.loads(json.dumps(FORM_SEKCE_1))
                for q in sekce_1.get("questions", []) or []:
                    q["rating"] = RATING_NOT_MET
                    q["note"] = ERROR_FETCH_NOTE
                    q["evidence"] = ""
                return {
                    "sekce_1": sekce_1,
                    "raw_evidence": {
                        "collected_at_utc": iso_now(),
                        "owner": owner,
                        "repo": repo,
                    },
                }
            # Default triple
            return ([], RATING_NOT_MET, ERROR_FETCH_NOTE)

    return _wrap


def repo_info(owner, repo, token):
    return gh_get(f"{API}/repos/{owner}/{repo}", token)


def org_info(owner, token):
    try:
        return gh_get(f"{API}/orgs/{owner}", token)
    except Exception:
        return gh_get(f"{API}/users/{owner}", token)


def latest_release(owner, repo, token):
    try:
        return gh_get(f"{API}/repos/{owner}/{repo}/releases/latest", token)
    except Exception:
        return None


def list_releases(owner, repo, token):
    return gh_paginate(f"{API}/repos/{owner}/{repo}/releases", token)


def list_tags(owner, repo, token):
    return gh_paginate(f"{API}/repos/{owner}/{repo}/tags", token)


def get_commit(owner, repo, sha, token):
    return gh_get(f"{API}/repos/{owner}/{repo}/commits/{sha}", token)


def get_git_ref(owner, repo, ref, token):

    return gh_get(f"{API}/repos/{owner}/{repo}/git/ref/{ref}", token)


def get_git_tag(owner, repo, tag_sha, token):
    return gh_get(f"{API}/repos/{owner}/{repo}/git/tags/{tag_sha}", token)


def languages(owner, repo, token):
    return gh_get(f"{API}/repos/{owner}/{repo}/languages", token)


def readme(owner, repo, token):
    try:
        return gh_get(f"{API}/repos/{owner}/{repo}/readme", token)
    except Exception:
        return None


def search_code(owner, repo, token, q):
    """
    Use the GitHub code search API (token recommended).
    Returns a dict with a summary and representative hits (path, fragment).
    """
    query = f"{q}+repo:{owner}/{repo}"
    url = f"{API}/search/code?q={urllib.parse.quote(query)}&per_page=10"
    try:
        data = gh_get(url, token, accept_preview=True)
        total = data.get("total_count", 0)
        items = []
        for it in data.get("items", []):
            path = it.get("path")
            repo_html = it.get("repository", {}).get("html_url")
            html_url = (
                f"{repo_html}/blob/{it.get('sha')}/{path}"
                if repo_html and path
                else it.get("html_url")
            )
            frag = None
            tms = it.get("text_matches") or []
            if tms:
                frag = tms[0].get("fragment")
            items.append({"path": path, "url": html_url, "fragment": frag})
        return {"query": q, "total_count": total, "examples": items}
    except Exception as e:
        return {"query": q, "error": str(e)}


def signed_state_for_tag(owner, repo, tag_name, token):
    """
    Attempt to determine the signature verification status for the tag/commit the tag points to.
    """
    try:
        ref = get_git_ref(owner, repo, f"tags/{tag_name}", token)
        obj = ref.get("object", {})
        if obj.get("type") == "tag":
            tag = get_git_tag(owner, repo, obj.get("sha"), token)
            target_sha = tag.get("object", {}).get("sha")
            if target_sha:
                commit = get_commit(owner, repo, target_sha, token)
                ver = commit.get("commit", {}).get("verification") or commit.get("verification")
                return {"tag_type": "annotated", "commit_sha": target_sha, "verification": ver}
            return {"tag_type": "annotated", "commit_sha": None, "verification": None}
        elif obj.get("type") == "commit":
            commit = get_commit(owner, repo, obj.get("sha"), token)
            ver = commit.get("commit", {}).get("verification") or commit.get("verification")
            return {"tag_type": "lightweight", "commit_sha": obj.get("sha"), "verification": ver}
        else:
            return {"tag_type": obj.get("type"), "commit_sha": None, "verification": None}
    except Exception as e:
        return {"error": str(e)}


def suspicious_search_pack(owner, repo, token):
    """
    Query bundle for question 1-3 (malicious indicators).
    Fully text based; no code execution involved.
    """
    queries = [
        "curl+|+sh",
        "wget+http",
        "Invoke-WebRequest",
        "powershell+-EncodedCommand",
        "base64+-d+|+sh",
        "nc+-e",
        "openssl+s_client",
        "ssh-agent",
        '"~/.ssh/"',
        "eval\\(",
        "exec\\(",
    ]
    results = []
    for q in queries:
        results.append(search_code(owner, repo, token, q))
        time.sleep(0.2)
    return results


FORM_SEKCE_1 = {
    "id": 1,
    "title": text("script1", "form", "title"),
    "questions": [
        {
            "id": "1-1",
            "text": text("script1", "form", "questions", "1-1", "text"),
            "rating": None,
            "note": "",
            "category": text("script1", "form", "category"),
            "description": text("script1", "form", "questions", "1-1", "description"),
            "evidence": "",
        },
        {
            "id": "1-2",
            "text": text("script1", "form", "questions", "1-2", "text"),
            "rating": None,
            "note": "",
            "category": text("script1", "form", "category"),
            "description": text("script1", "form", "questions", "1-2", "description"),
            "evidence": "",
        },
        {
            "id": "1-3",
            "text": text("script1", "form", "questions", "1-3", "text"),
            "rating": None,
            "note": "",
            "category": text("script1", "form", "category"),
            "description": text("script1", "form", "questions", "1-3", "description"),
            "evidence": "",
        },
    ],
}


@_eval_log
def evaluate_q_1_1(owner: str, repo: str, ctx: dict) -> tuple[list, str, str]:
    """
    1-1: Project identity and secure distribution.
    Collects: canonical repo URL, license, latest release/tag, commit/tag verification, org verification.
    Rates: meets if owner is verified or commit/tag is verified; partial otherwise.
    """
    repo_meta = ctx["repo_meta"]
    org_meta = ctx["org_meta"]
    rel_latest = ctx["rel_latest"]
    tag_name = ctx["tag_name"]
    sign_state = ctx["sign_state"]
    dukazy = []
    html_url = repo_meta.get("html_url")
    if html_url:
        dukazy.append({"type": "repo", "url": html_url})
    if repo_meta.get("license", {}).get("spdx_id"):
        dukazy.append(
            {
                "type": "license",
                "url": html_url + "/blob/" + repo_meta.get("default_branch", "master") + "/LICENSE",
            }
        )
    if rel_latest and rel_latest.get("html_url"):
        dukazy.append({"type": "latest_release", "url": rel_latest["html_url"]})
    if tag_name and html_url:
        dukazy.append(
            {"type": "tag", "url": f"{html_url}/releases/tag/{urllib.parse.quote(tag_name)}"}
        )
    if sign_state and isinstance(sign_state, dict):
        ver = sign_state.get("verification") or {}
        dukazy.append(
            {
                "type": "commit_verification",
                "url": (
                    f"{html_url}/commit/{sign_state.get('commit_sha')}"
                    if sign_state.get("commit_sha")
                    else html_url
                ),
                "note": {
                    "tag_type": sign_state.get("tag_type"),
                    "verified": ver.get("verified") if isinstance(ver, dict) else None,
                    "reason": ver.get("reason") if isinstance(ver, dict) else None,
                },
            }
        )
    if org_meta:
        dukazy.append(
            {
                "type": "owner_verification",
                "url": org_meta.get("html_url") or org_meta.get("url"),
                "note": {"is_verified": org_meta.get("is_verified")},
            }
        )
    dukazy.append({"type": "https_distribution", "url": html_url})

    # Registry match + sigstore assets (E6.a)
    registry = ctx.get("registry_match") or {}
    if registry.get("url"):
        dukazy.append(
            {
                "type": "registry",
                "url": registry["url"],
                "note": {
                    "system": registry.get("system"),
                    "name": registry.get("name"),
                    "matched": registry.get("matched"),
                },
            }
        )
    for sig_url in ctx.get("sig_assets") or []:
        dukazy.append({"type": "release_sig_or_sbom", "url": sig_url})
    attest = ctx.get("attestations") or {}
    for url in attest.get("urls") or []:
        dukazy.append({"type": "attestation_or_sig_asset", "url": url})

    has_signed_commit = any(
        isinstance(x.get("note"), dict) and (x["note"].get("verified") is True)
        for x in dukazy
        if x.get("type") == "commit_verification"
    )
    owner_verified = any(
        (x.get("type") == "owner_verification") and (x.get("note", {}).get("is_verified") is True)
        for x in dukazy
        if x.get("type") == "owner_verification"
    )
    registry_ok = bool(registry.get("matched"))
    has_sig_asset = bool(ctx.get("sig_assets") or attest.get("has_signal"))
    has_latest_release = any(x.get("type") == "latest_release" for x in dukazy)

    # A fork is exactly what 1-1 guards against ("not a personal fork or a
    # fraudulent copy"); verified owners/signatures on the fork don't change that.
    if repo_meta.get("fork"):
        source = repo_meta.get("source") or repo_meta.get("parent") or {}
        source_name = source.get("full_name") or "neznámý zdroj"
        source_url = source.get("html_url")
        if source_url:
            dukazy.append({"type": "fork_source", "url": source_url})
        note = (
            f"Repozitář je fork ({source_name}). Ověřte, že hodnotíte kanonický zdroj "
            "knihovny, ne osobní fork nebo kopii — bez toho nelze potvrdit pravost."
        )
        return dukazy, RATING_PARTIAL, note

    if owner_verified or has_signed_commit or (registry_ok and has_sig_asset):
        rating = RATING_MEETS
        note = text("script1", "evaluate_q_1_1", "note_owner_verified")
        if registry_ok:
            note = f"{note} Registry match: {registry.get('system')}/{registry.get('name')}."
        if attest.get("has_signal"):
            note = f"{note} Attestation/sig assets: ano."
    elif has_latest_release or registry_ok or has_sig_asset:
        rating = RATING_PARTIAL
        note = text("script1", "evaluate_q_1_1", "note_release_only")
        if registry_ok:
            note = f"{note} Registry: {registry.get('system')}/{registry.get('name')}."
        if has_sig_asset:
            note = f"{note} Nalezeny podpis/SBOM/attestation artefakty v release."
    else:
        rating = RATING_PARTIAL
        note = text("script1", "evaluate_q_1_1", "note_basic")
    return dukazy, rating, note


@_eval_log
def evaluate_q_1_2(owner: str, repo: str, ctx: dict) -> tuple[list, str, str]:
    """
    1-2: Required functionality and suitability.
    Collects: README/description, languages, popularity metrics, topics.
    Rates: meets with README plus extra signals; otherwise partial/not.
    """
    repo_meta = ctx["repo_meta"]
    langs = ctx["langs"]
    readme_meta = ctx["readme_meta"]
    html_url = repo_meta.get("html_url")
    dukazy = []
    if repo_meta.get("description"):
        dukazy.append({"type": "description", "url": html_url})
    dukazy.append({"type": "languages", "url": f"{html_url}/search?l=&q=&type=code"})
    dukazy.append({"type": "stars_forks_watchers", "url": html_url})
    dukazy.append({"type": "topics", "url": html_url})
    if readme_meta and readme_meta.get("html_url"):
        dukazy.append({"type": "readme", "url": readme_meta["html_url"]})
    has_readme = bool(readme_meta and readme_meta.get("html_url"))
    has_desc = bool(repo_meta.get("description"))
    stars = int(repo_meta.get("stargazers_count") or 0)
    forks = int(repo_meta.get("forks_count") or 0)
    langs_nonempty = bool(langs)
    if has_readme and (langs_nonempty or stars >= 100 or forks >= 20):
        languages_display = list(langs.keys())[:3]
        return (
            dukazy,
            RATING_PARTIAL,
            text(
                "script1",
                "evaluate_q_1_2",
                "note_full",
                languages=languages_display,
                stars=stars,
                forks=forks,
            )
            + " Vyžaduje kontext cílového projektu (ne AUTO).",
        )
    elif has_readme or has_desc:
        return (
            dukazy,
            RATING_PARTIAL,
            text("script1", "evaluate_q_1_2", "note_partial"),
        )
    else:
        return dukazy, RATING_NOT_MET, text("script1", "evaluate_q_1_2", "note_missing")


@_eval_log
def evaluate_q_1_3(owner: str, repo: str, ctx: dict) -> tuple[list, str, str]:
    """
    1-3: Signs of malicious patterns (static search, no execution).
    Collects: code search results for suspicious patterns (curl|sh, base64|sh, ~/.ssh, etc.).
    Rates: meets if none; partial with benign or scarce hits; warn for risky fragments.
    """
    suspicious = ctx["suspicious"]
    repo_meta = ctx["repo_meta"]
    html_url = repo_meta.get("html_url")
    dukazy = []
    for r in suspicious:
        if "error" in r:
            dukazy.append(
                {
                    "type": "code_search_error",
                    "url": html_url,
                    "note": {"query": r["query"], "error": r["error"]},
                }
            )
        else:
            note = {"query": r["query"], "total_count": r.get("total_count")}
            examples = r.get("examples") or []
            if examples:
                note["examples"] = examples[:5]
            dukazy.append({"type": "code_search", "url": html_url, "note": note})
    total_hits = 0
    risky_hits = 0
    benign_hits = 0
    search_errors = 0
    for r in suspicious:
        if "error" in r:
            search_errors += 1
            continue
        cnt = int(r.get("total_count") or 0)
        total_hits += cnt
        examples = r.get("examples") or []
        for ex in examples:
            p = (ex.get("path") or "").lower()
            frag = (ex.get("fragment") or "").lower()
            if any(seg in p for seg in ["docs/", "doc/", "readme", "tests/", "examples/"]):
                benign_hits += 1
            elif (
                ("curl" in frag and "|" in frag)
                or ("base64" in frag and "|" in frag)
                or ("invoke-webrequest" in frag)
                or ("nc -e" in frag)
            ):
                risky_hits += 1
            else:
                benign_hits += 1
    if search_errors and total_hits == 0:
        return (
            dukazy,
            RATING_PARTIAL,
            text("script1", "evaluate_q_1_3", "note_no_hits")
            + " Zdroj code search nedostupný/chyba — neinterpretovat jako absenci škodlivosti.",
        )
    if total_hits == 0:
        # Absence of hits is not an audit — keep partial (FORCE_CONFIRM in workflow).
        return (
            dukazy,
            RATING_PARTIAL,
            text("script1", "evaluate_q_1_3", "note_no_hits")
            + " 0 hitů ≠ audit; vyžaduje potvrzení.",
        )
    elif risky_hits == 0 and total_hits <= 3:
        return (
            dukazy,
            RATING_PARTIAL,
            text("script1", "evaluate_q_1_3", "note_benign", total_hits=total_hits),
        )
    else:
        return (
            dukazy,
            RATING_PARTIAL,
            text("script1", "evaluate_q_1_3", "note_risky", total_hits=total_hits),
        )


def build_output(owner, repo, token):
    requested_ref = os.environ.get("REPO_REF", "").strip() or None
    repo_meta = repo_info(owner, repo, token)
    org_meta = org_info(owner, token)
    rel_latest = latest_release(owner, repo, token)
    releases = list_releases(owner, repo, token)
    tags = list_tags(owner, repo, token)
    langs = languages(owner, repo, token)
    readme_meta = readme(owner, repo, token)
    tag_name = tags[0]["name"] if tags else None
    sign_state = signed_state_for_tag(owner, repo, tag_name, token) if tag_name else None
    suspicious = suspicious_search_pack(owner, repo, token)

    # Registry + release sig/SBOM assets (E6.a)
    from pipeline.package_detect import detect_package, release_has_sigstore_assets
    from integrations.github import get_file as gh_get_file_api
    import base64

    manifest_texts = {}
    for path in ("Cargo.toml", "pyproject.toml", "package.json"):
        meta = gh_get_file_api(owner, repo, path, ref=requested_ref, token=token)
        if meta and meta.get("content"):
            try:
                manifest_texts[path] = base64.b64decode(meta["content"]).decode(
                    "utf-8", errors="replace"
                )
            except Exception:
                pass
    package_info = detect_package(owner, repo, manifest_texts)
    registry_match = {}
    if package_info.get("system") and package_info.get("name"):
        system = package_info["system"]
        name = package_info["name"]
        if system == "cargo":
            registry_match = {
                "system": system,
                "name": name,
                "url": f"https://crates.io/crates/{name}",
                "matched": True,
            }
        elif system == "pypi":
            registry_match = {
                "system": system,
                "name": name,
                "url": f"https://pypi.org/project/{name}/",
                "matched": True,
            }
        elif system == "npm":
            registry_match = {
                "system": system,
                "name": name,
                "url": f"https://www.npmjs.com/package/{name}",
                "matched": True,
            }
    sig_assets = release_has_sigstore_assets((rel_latest or {}).get("assets") or [])
    from pipeline.repo_signals import detect_release_attestations

    attestations = detect_release_attestations(owner, repo, rel_latest if isinstance(rel_latest, dict) else None)

    ctx = {
        "repo_meta": repo_meta,
        "org_meta": org_meta,
        "rel_latest": rel_latest,
        "releases": releases,
        "tags": tags,
        "langs": langs,
        "readme_meta": readme_meta,
        "tag_name": tag_name,
        "sign_state": sign_state,
        "suspicious": suspicious,
        "registry_match": registry_match,
        "sig_assets": sig_assets,
        "attestations": attestations,
        "package_info": package_info,
    }

    dukazy_1_1, rating_1_1, note_1_1 = evaluate_q_1_1(owner, repo, ctx)
    dukazy_1_2, rating_1_2, note_1_2 = evaluate_q_1_2(owner, repo, ctx)
    dukazy_1_3, rating_1_3, note_1_3 = evaluate_q_1_3(owner, repo, ctx)

    sekce_1 = json.loads(json.dumps(FORM_SEKCE_1))
    for q in sekce_1["questions"]:
        if q["id"] == "1-1":
            q["evidence"] = json.dumps(dukazy_1_1, ensure_ascii=False)
            q["rating"] = rating_1_1
            q["note"] = note_1_1
        elif q["id"] == "1-2":
            q["evidence"] = json.dumps(dukazy_1_2, ensure_ascii=False)
            q["rating"] = rating_1_2
            q["note"] = note_1_2
        elif q["id"] == "1-3":
            q["evidence"] = json.dumps(dukazy_1_3, ensure_ascii=False)
            q["rating"] = rating_1_3
            q["note"] = note_1_3

    raw = {
        "collected_at_utc": iso_now(),
        "owner": owner,
        "repo": repo,
        "requested_ref": requested_ref,
        "effective_ref": requested_ref or repo_meta.get("default_branch"),
        "repo_meta": {
            "html_url": repo_meta.get("html_url"),
            "description": repo_meta.get("description"),
            "created_at": repo_meta.get("created_at"),
            "pushed_at": repo_meta.get("pushed_at"),
            "updated_at": repo_meta.get("updated_at"),
            "default_branch": repo_meta.get("default_branch"),
            "license": repo_meta.get("license"),
            "stargazers_count": repo_meta.get("stargazers_count"),
            "forks_count": repo_meta.get("forks_count"),
            "watchers_count": repo_meta.get("watchers_count"),
            "archived": repo_meta.get("archived"),
            "disabled": repo_meta.get("disabled"),
            "fork": repo_meta.get("fork"),
            "fork_source": (repo_meta.get("source") or {}).get("full_name"),
            "topics": repo_meta.get("topics"),
            "size_kb": repo_meta.get("size"),
            "has_downloads": repo_meta.get("has_downloads"),
            "has_issues": repo_meta.get("has_issues"),
            "has_projects": repo_meta.get("has_projects"),
            "has_wiki": repo_meta.get("has_wiki"),
        },
        "org_meta": {
            "login": org_meta.get("login"),
            "type": org_meta.get("type"),
            "is_verified": org_meta.get("is_verified"),
            "html_url": org_meta.get("html_url") or org_meta.get("url"),
        },
        "release_latest": rel_latest,
        "releases_count": len(releases),
        "tags_count": len(tags),
        "checked_tag": tag_name,
        "checked_tag_sign_state": sign_state,
        "languages": langs,
        "suspicious_search": suspicious,
    }

    return {"sekce_1": sekce_1, "raw_evidence": raw}


def _merge_into_form(input_path: str, output_path: str, sekce_1: dict, raw: dict | None = None):
    with open(input_path, encoding="utf-8") as f:
        form = json.load(f)

    section = None
    for s in form.get("sections", []):
        if str(s.get("id")) == "1":
            section = s
            break
    if section is None:
        # Ensure evidence is a string (JSON string of list) for consistency
        for q in sekce_1.get("questions", []):
            dv = q.get("evidence")
            if isinstance(dv, list) or isinstance(dv, dict):
                q["evidence"] = json.dumps(dv, ensure_ascii=False)
        requested_ref = os.environ.get("REPO_REF", "").strip() or None
        sec_meta = sekce_1.setdefault("meta", {})
        if isinstance(sec_meta, dict):
            sec_meta["requested_ref"] = requested_ref
            sec_meta["effective_ref"] = requested_ref or sec_meta.get("effective_ref")
        form.setdefault("sections", []).append(sekce_1)
    else:
        new_proofs = {}
        new_ratings = {}
        new_notes = {}
        for q in sekce_1.get("questions", []):
            qid = q.get("id")
            dv = q.get("evidence")
            if isinstance(dv, (list, dict)):
                new_proofs[qid] = json.dumps(dv, ensure_ascii=False)
            else:
                new_proofs[qid] = str(dv) if dv is not None else ""
            if q.get("rating"):
                new_ratings[qid] = q.get("rating")
            if q.get("note"):
                new_notes[qid] = q.get("note")
        for q in section.get("questions", []):
            qid = q.get("id")
            if qid in new_proofs:
                q["evidence"] = new_proofs[qid]
            if (not q.get("rating")) and (qid in new_ratings):
                q["rating"] = new_ratings[qid]
            if (not q.get("note")) and (qid in new_notes):
                q["note"] = new_notes[qid]
        requested_ref = os.environ.get("REPO_REF", "").strip() or None
        sec_meta = section.setdefault("meta", {})
        if isinstance(sec_meta, dict):
            sec_meta["requested_ref"] = requested_ref
            sec_meta["effective_ref"] = requested_ref or sec_meta.get("effective_ref")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(form, f, ensure_ascii=False, indent=2)
    try:
        outdir = os.path.join(os.path.dirname(output_path) or ".", "raw")
        os.makedirs(outdir, exist_ok=True)
        if raw is not None:
            with open(
                os.path.join(outdir, "section1_predpoklady_raw.json"), "w", encoding="utf-8"
            ) as rf:
                json.dump(raw, rf, ensure_ascii=False, indent=2)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description=text("script1", "cli", "description"))
    ap.add_argument("--owner", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--input", default=None, help=text("script1", "cli", "help_input"))
    ap.add_argument("--output", default=None, help=text("script1", "cli", "help_output"))
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    args = ap.parse_args()

    print(
        f"[START] [1.py] Zahajuji vyhodnocení sekce 1 pro {args.owner}/{args.repo}",
        flush=True,
    )
    print("[INFO] [1.py] Načítám metadata projektu, release a reputační signály.", flush=True)
    try:
        result = build_output(args.owner, args.repo, args.token)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        sys.stderr.write(text("common", "errors", "http_error", code=e.code, body=body) + "\n")
        sys.exit(2)
    except Exception as e:
        sys.stderr.write(text("common", "errors", "generic", message=e) + "\n")
        sys.exit(1)

    if args.input and args.output:
        print("[INFO] [1.py] Sloučím výsledky sekce 1 do pracovního formuláře.", flush=True)
        _merge_into_form(args.input, args.output, result["sekce_1"], result.get("raw_evidence"))
        print(text("script1", "cli", "success_merge", path=args.output))
        print(f"[DONE] [1.py] Sekce 1 byla zapsána do {args.output}", flush=True)
    else:
        out_path = args.out or "result_predpoklady.json"
        payload = {
            "formular": {
                "title": text("script1", "payload", "title"),
                "version": text("script1", "payload", "version"),
                "language": text("script1", "payload", "language"),
                "sections": [result["sekce_1"]],
            },
            "raw_evidence": result.get("raw_evidence", {}),
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(text("script1", "cli", "success_write", path=out_path))
        print(f"[DONE] [1.py] Sekce 1 byla zapsána do {out_path}", flush=True)


if __name__ == "__main__":
    main()
