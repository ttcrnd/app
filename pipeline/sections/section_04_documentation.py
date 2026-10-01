#!/usr/bin/env python3

import argparse
import base64
import functools
import json
import os
import re
import sys
from urllib.parse import urlparse

import requests

try:
    from pipeline.localization import text
except ModuleNotFoundError:  # pragma: no cover
    try:
        from localization import text
    except ModuleNotFoundError:  # pragma: no cover
        from scripts.localization import text  # type: ignore

from domain.docs import (
    extract_links_from_markdown,
    md_has_api_reference_signals,
    md_has_code_examples,
    md_has_crypto_warnings,
    md_has_howto_guides,
    md_has_install_instructions,
)
from integrations.github import get as _gh_get
from integrations.http import get_text as _http_get_text
from integrations.http import http_head as _http_head

GITHUB_API = "https://api.github.com"
TARGET_REF = os.environ.get("REPO_REF", "").strip() or None
SESSION = requests.Session()
SESSION.headers.update(
    {"Accept": "application/vnd.github+json", "User-Agent": "oss-doc-auditor/1.0"}
)
if "GITHUB_TOKEN" in os.environ and os.environ["GITHUB_TOKEN"].strip():
    SESSION.headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN'].strip()}"

RATING_MEETS = text("common", "ratings", "meets")
RATING_PARTIAL = text("common", "ratings", "partial")
RATING_NOT_MET = text("common", "ratings", "not_met")
ERROR_FETCH_NOTE = text("common", "errors", "fetching")


def _eval_log(fn):
    @functools.wraps(fn)
    def _wrap(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
            try:
                print(f"[evaluate] {fn.__name__} done")
            except Exception:
                pass
            return result
        except Exception:
            # Aggregator fallback: set all section 4 questions to default and return the form
            if fn.__name__ == "evaluate_section4":
                if len(args) >= 3:
                    form = args[2]
                else:
                    form = kwargs.get("form", {})
                try:
                    section4 = next(
                        (s for s in form.get("sections", []) if str(s.get("id")) == "4"), None
                    )
                    if section4 and isinstance(section4.get("questions"), list):
                        for q in section4["questions"]:
                            q["rating"] = RATING_NOT_MET
                            q["note"] = ERROR_FETCH_NOTE
                            q["evidence"] = ""
                except Exception:
                    pass
                return form
            # Default: rethrow-safe default not needed for helper fns since they aren't decorated
            return kwargs.get("form") if "form" in kwargs else (args[2] if len(args) >= 3 else {})

    return _wrap


def gh_get(path, params=None):
    status, data, _ = _gh_get(path, params=params)
    if status == 404:
        return None
    if status and status >= 400:
        raise RuntimeError(text("script4", "errors", "github_api", status=status, path=path))
    return data


def gh_get_contents(owner, repo, path="", ref=None):
    effective_ref = ref or TARGET_REF
    params = {"ref": effective_ref} if effective_ref else None
    data = gh_get(f"/repos/{owner}/{repo}/contents/{path}", params=params)
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    return data


def gh_get_readme(owner, repo, ref=None):
    effective_ref = ref or TARGET_REF
    params = {"ref": effective_ref} if effective_ref else None
    data = gh_get(f"/repos/{owner}/{repo}/readme", params=params)
    if not data:
        return None, None
    content = data.get("content")
    html_url = data.get("html_url")
    if content:
        try:
            decoded = base64.b64decode(content).decode("utf-8", errors="replace")
            return decoded, html_url
        except Exception:
            pass
    return None, html_url


def decode_file_content(item):
    if item.get("encoding") == "base64" and "content" in item:
        try:
            return base64.b64decode(item["content"]).decode("utf-8", errors="replace")
        except Exception:
            return None
    return None


def find_first_existing(owner, repo, candidates, ref=None):
    for p in candidates:
        items = gh_get_contents(owner, repo, p, ref=ref)
        for it in items:
            if it.get("type") == "file":
                return it
    return None


def repo_meta(owner, repo):
    meta = gh_get(f"/repos/{owner}/{repo}") or {}
    _home = meta.get("homepage") or ""
    topics = gh_get(f"/repos/{owner}/{repo}/topics") or {}
    meta["topics"] = topics.get("names", [])
    meta["requested_ref"] = TARGET_REF
    meta["effective_ref"] = TARGET_REF or meta.get("default_branch", "main")
    return meta


def list_tree(owner, repo, ref=None):
    meta = gh_get(f"/repos/{owner}/{repo}")
    default_branch = meta.get("default_branch", "main") if meta else "main"
    effective_ref = ref or TARGET_REF or default_branch
    commit = gh_get(f"/repos/{owner}/{repo}/commits/{effective_ref}")
    if not commit:
        return []
    sha = commit.get("sha")
    if not sha:
        return []
    tree = gh_get(f"/repos/{owner}/{repo}/git/trees/{sha}?recursive=1")
    if not tree:
        return []
    return [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]


def http_head_ok(url):
    status, _ = _http_head(url)
    return 200 <= int(status or 0) < 400


def http_get_text(url, max_bytes=500_000):
    status, text, _ = _http_get_text(url, max_bytes=max_bytes)
    return text if status and status < 400 else None


def detect_doc_system(paths, readme_text, homepage_links):
    """
    Returns dict with doc_system (sphinx/mkdocs/doxygen/wiki/other),
    doc_urls (candidate URLs), has_search(bool)
    """
    doc_urls = set()

    sphinx_signals = any(p.endswith("/conf.py") and "docs/" in p for p in paths)
    mkdocs_signals = "mkdocs.yml" in paths or any(p.endswith("mkdocs.yml") for p in paths)
    doxygen_signals = any("Doxyfile" in p for p in paths) or md_has_api_reference_signals(
        readme_text
    )

    for u in homepage_links:
        host = urlparse(u).netloc.lower()
        if "readthedocs.io" in host or "rtfd.io" in host:
            doc_urls.add(u)
        if "github.io" in host or "pages" in host:
            doc_urls.add(u)

    has_search = False
    search_hints = []

    for u in list(doc_urls)[:8]:
        html = http_get_text(u)
        if not html:
            continue
        if re.search(
            r"readthedocs|rtd-search-form|search__input|role=\"search\"", html, re.IGNORECASE
        ):
            has_search = True
            search_hints.append(u)
        if re.search(r"mkdocs|data-md-component=\"search\"", html, re.IGNORECASE):
            has_search = True
            search_hints.append(u)
        if re.search(r"Sphinx|searchindex\.js", html, re.IGNORECASE):
            has_search = True
            search_hints.append(u)

    doc_system = "other"
    if sphinx_signals:
        doc_system = "sphinx"
    elif mkdocs_signals:
        doc_system = "mkdocs"
    elif doxygen_signals:
        doc_system = "doxygen/wiki/other"

    return {
        "doc_system": doc_system,
        "doc_urls": sorted(doc_urls),
        "has_search": has_search,
        "search_evidence": search_hints,
    }


def evidence(*urls):
    return sorted(set(u for u in urls if u))


def decide(score_true, notes_true, notes_false):
    return (RATING_MEETS, notes_true) if score_true else (RATING_PARTIAL, notes_false)


def q4_1(ctx):
    """
    4-1: Official documentation covering install steps and full API reference.
    Collects README/INSTALL files, docs (Sphinx/MkDocs/Doxygen), and links from README/homepage.
    Heuristic: meets if both install instructions and API reference signals exist; otherwise partial.
    """
    has_install = ctx["has_install"]
    api_signals = ctx["api_signals"]
    status, note = (
        (
            RATING_MEETS,
            text("script4", "q4_1", "note_full"),
        )
        if (has_install and api_signals)
        else (
            RATING_PARTIAL,
            text("script4", "q4_1", "note_partial"),
        )
    )
    proofs = []
    if ctx["install_file"] and ctx["install_file"].get("html_url"):
        proofs.append(ctx["install_file"]["html_url"])
    proofs += ctx["readme_evd"] + ctx["doc_detect"]["doc_urls"]
    return status, note, proofs


def q4_2(ctx):
    """
    4-2: Code examples for common usage.
    Heuristic: detect code blocks with "example" in README or presence of examples/* directories.
    Misuse scan (E13): dangerous patterns force PARTIAL + warning note.
    Never AUTO-MEETS from absence of misuse hits alone (metodika §4.3).
    """
    from pipeline.misuse_scan import scan_text

    has_examples = ctx["has_examples"]
    readme = ctx.get("readme_text") or ""
    misuse = scan_text(readme, source="README")
    status, note = (
        (RATING_PARTIAL, text("script4", "q4_2", "note_full") + " (CONFIRM — ověř bezpečnost ukázek).")
        if has_examples and not misuse
        else (
            RATING_PARTIAL,
            text("script4", "q4_2", "note_partial"),
        )
    )
    if misuse:
        pats = sorted({h["pattern"] for h in misuse})
        note = f"{note} Misuse scan: {', '.join(pats)} (vyžaduje ruční kontrolu bezpečnosti ukázek)."
        status = RATING_PARTIAL
    proofs = (
        ctx["readme_evd"]
        + [
            f"https://github.com/{ctx['owner_repo']}/tree/HEAD/{p}"
            for p in ctx["examples_candidates"][:10]
        ]
        + ctx["doc_detect"]["doc_urls"]
    )
    return status, note, proofs


def q4_3(ctx):
    """
    4-3: Clear warnings about risky algorithms or parameters.
    Keyword hits are CONFIRM-only (FORCE_CONFIRM); never treat as high-confidence MEETS alone.
    """
    has_warnings = ctx["has_warnings"]
    warn_hits = ctx["warn_hits"]
    status, note = (
        (RATING_PARTIAL, text("script4", "q4_3", "note_full") + " (CONFIRM — zkontroluj kvalitu varování).")
        if has_warnings
        else (
            RATING_PARTIAL,
            text("script4", "q4_3", "note_partial"),
        )
    )
    proofs = ctx["readme_evd"] + warn_hits + ctx["doc_detect"]["doc_urls"]
    return status, note, proofs


def q4_4(ctx):
    """
    4-4: Structured documentation with search capability.
    """
    has_docs_search = bool(ctx["doc_detect"]["doc_urls"]) and bool(ctx["doc_detect"]["has_search"])
    status, note = (
        (
            RATING_MEETS,
            text(
                "script4",
                "q4_4",
                "note_full",
                doc_system=ctx["doc_detect"]["doc_system"],
            ),
        )
        if has_docs_search
        else (
            RATING_PARTIAL,
            text("script4", "q4_4", "note_partial"),
        )
    )
    proofs = (
        ctx["doc_detect"]["doc_urls"] + ctx["doc_detect"]["search_evidence"] + ctx["readme_evd"]
    )
    return status, note, proofs


def q4_5(ctx):
    """
    4-5: How-to guides, recipes, or scenarios.
    """
    has_howto = ctx["has_howto"]
    howto_hits = ctx["howto_hits"]
    status, note = (
        (RATING_MEETS, text("script4", "q4_5", "note_full"))
        if has_howto
        else (
            RATING_PARTIAL,
            text("script4", "q4_5", "note_partial"),
        )
    )
    proofs = ctx["readme_evd"] + howto_hits + ctx["doc_detect"]["doc_urls"]
    return status, note, proofs


def q4_6(ctx):
    """
    4-6: Intro/overview content with fundamentals and links to recommended practices.
    """
    has_intro = ctx["has_intro"]
    intro_hits = ctx["intro_hits"]
    status, note = (
        (RATING_MEETS, text("script4", "q4_6", "note_full"))
        if has_intro
        else (
            RATING_PARTIAL,
            text("script4", "q4_6", "note_partial"),
        )
    )
    proofs = intro_hits + ctx["doc_detect"]["doc_urls"] + ctx["readme_evd"]
    return status, note, proofs


def q4_7(ctx):
    """
    4-7: Unofficial sources do not misinform - cannot be verified automatically, so we attach external links.
    """
    status = RATING_PARTIAL
    note = text("script4", "q4_7", "note")
    proofs = ctx["ext_links"][:15] + ctx["readme_evd"]
    return status, note, proofs


@_eval_log
def evaluate_section4(owner, repo, form):

    effective_ref = TARGET_REF
    meta = repo_meta(owner, repo)
    readme_text, readme_url = gh_get_readme(owner, repo, ref=effective_ref)
    paths = list_tree(owner, repo, ref=effective_ref)

    links = set(extract_links_from_markdown(readme_text or ""))
    homepage = (meta.get("homepage") or "").strip()
    if homepage:
        links.add(homepage)

    doc_detect = detect_doc_system(paths, readme_text or "", list(links))

    readme_evd = evidence(readme_url)
    wiki_url = f"https://github.com/{owner}/{repo}/wiki"
    if http_head_ok(wiki_url):
        readme_evd.append(wiki_url)

    install_file = find_first_existing(
        owner,
        repo,
        ["INSTALL", "INSTALL.md", "docs/INSTALL.md", "README.md", "README"],
        ref=effective_ref,
    )
    api_ref_candidates = [
        p for p in paths if re.search(r"(docs|doc|api|reference|doxygen)", p, re.IGNORECASE)
    ]
    examples_candidates = [
        p for p in paths if re.search(r"(examples?|sample|demo)", p, re.IGNORECASE)
    ]
    conf_sphinx = [p for p in paths if p.endswith("conf.py") and "docs/" in p]
    mkdocs_yml = [p for p in paths if p.endswith("mkdocs.yml")]
    doxyfiles = [p for p in paths if "Doxyfile" in p]

    section4 = next((s for s in form.get("sections", []) if str(s.get("id")) == "4"), None)
    if not section4:
        raise RuntimeError(text("script4", "errors", "missing_section"))

    def set_q(qid, status, note, proofs):
        for q in section4["questions"]:
            if q.get("id") == qid:
                q["rating"] = status
                q["note"] = note.strip()
                q["evidence"] = "\n".join(sorted(set(proofs)))[:5000]
                q["heuristic_rating"] = True
                return

    has_install = md_has_install_instructions(readme_text or "") or bool(install_file)
    api_signals = (
        bool(api_ref_candidates)
        or md_has_api_reference_signals(readme_text or "")
        or bool(doxyfiles)
        or bool(conf_sphinx)
        or bool(mkdocs_yml)
    )
    has_examples = md_has_code_examples(readme_text or "") or bool(examples_candidates)
    has_warnings = md_has_crypto_warnings(readme_text or "")
    warn_hits = []
    for p in paths[:2000]:
        if not re.search(
            r"(docs|README|SECURITY|USAGE|GUIDE|HOWTO|crypto|cipher|hash|cbc|ecb|sha|warning|deprecated)",
            p,
            re.IGNORECASE,
        ):
            continue
        if not p.lower().endswith((".md", ".rst", ".txt")):
            continue
        params = {"ref": effective_ref} if effective_ref else None
        item = gh_get(f"/repos/{owner}/{repo}/contents/{p}", params=params)
        if isinstance(item, dict) and item.get("type") == "file":
            txt = decode_file_content(item) or ""
            if md_has_crypto_warnings(txt):
                has_warnings = True
                warn_hits.append(item.get("html_url"))
                if len(warn_hits) >= 10:
                    break
    has_howto = md_has_howto_guides(readme_text or "")
    howto_hits = []
    for p in paths[:2000]:
        if not re.search(
            r"(docs|guide|howto|tutorial|recipes|get(ting)?-?started|usage)", p, re.IGNORECASE
        ):
            continue
        if not p.lower().endswith((".md", ".rst", ".txt")):
            continue
        params = {"ref": effective_ref} if effective_ref else None
        item = gh_get(f"/repos/{owner}/{repo}/contents/{p}", params=params)
        if isinstance(item, dict) and item.get("type") == "file":
            txt = decode_file_content(item) or ""
            if md_has_howto_guides(txt) or md_has_code_examples(txt):
                has_howto = True
                howto_hits.append(item.get("html_url"))
                if len(howto_hits) >= 10:
                    break
    has_intro = False
    intro_hits = []
    if re.search(
        r"\b(overview|introduction|get(ting)? started|background|basics)\b",
        readme_text or "",
        re.IGNORECASE,
    ):
        has_intro = True
        intro_hits.append(readme_url)
    for p in paths[:2000]:
        if not re.search(
            r"(docs|intro|overview|get(ting)?-?started|basics|background)", p, re.IGNORECASE
        ):
            continue
        if not p.lower().endswith((".md", ".rst", ".txt")):
            continue
        params = {"ref": effective_ref} if effective_ref else None
        item = gh_get(f"/repos/{owner}/{repo}/contents/{p}", params=params)
        if isinstance(item, dict) and item.get("type") == "file":
            txt = decode_file_content(item) or ""
            if re.search(
                r"\b(overview|introduction|get(ting)? started|background|basics)\b",
                txt,
                re.IGNORECASE,
            ):
                has_intro = True
                intro_hits.append(item.get("html_url"))
                if len(intro_hits) >= 10:
                    break
    ext_links = [
        u for u in links if urlparse(u).netloc and "github.com" not in urlparse(u).netloc.lower()
    ]

    ctx = {
        "owner_repo": f"{owner}/{repo}",
        "install_file": install_file,
        "readme_evd": readme_evd,
        "readme_text": readme_text or "",
        "doc_detect": doc_detect,
        "has_install": has_install,
        "api_signals": api_signals,
        "has_examples": has_examples,
        "examples_candidates": examples_candidates,
        "has_warnings": has_warnings,
        "warn_hits": warn_hits,
        "has_howto": has_howto,
        "howto_hits": howto_hits,
        "has_intro": has_intro,
        "intro_hits": intro_hits,
        "ext_links": ext_links,
    }

    s, n, p = q4_1(ctx)
    set_q("4-1", s, n, p)
    s, n, p = q4_2(ctx)
    set_q("4-2", s, n, p)
    s, n, p = q4_3(ctx)
    set_q("4-3", s, n, p)
    s, n, p = q4_4(ctx)
    set_q("4-4", s, n, p)
    s, n, p = q4_5(ctx)
    set_q("4-5", s, n, p)
    s, n, p = q4_6(ctx)
    set_q("4-6", s, n, p)
    s, n, p = q4_7(ctx)
    set_q("4-7", s, n, p)

    sec_meta = section4.setdefault("meta", {})
    if isinstance(sec_meta, dict):
        sec_meta["default_branch"] = meta.get("default_branch")
        sec_meta["requested_ref"] = TARGET_REF
        sec_meta["effective_ref"] = effective_ref or meta.get("default_branch")

    return form


def main():
    ap = argparse.ArgumentParser(description=text("script4", "cli", "description"))
    ap.add_argument("--repo", required=True, help=text("script4", "cli", "help_repo"))
    ap.add_argument("--input", required=True, help=text("script4", "cli", "help_input"))
    ap.add_argument("--output", required=True, help=text("script4", "cli", "help_output"))
    args = ap.parse_args()

    print(f"[START] [4.py] Zahajuji vyhodnocení sekce 4 pro {args.repo}", flush=True)
    owner_repo = args.repo.strip().split("/")
    if len(owner_repo) != 2:
        print(text("script4", "errors", "repo_format"), file=sys.stderr)
        sys.exit(2)
    owner, repo = owner_repo

    print(
        "[INFO] [4.py] Načítám formulář a analyzuji dokumentaci, návody a API reference.",
        flush=True,
    )
    with open(args.input, encoding="utf-8") as f:
        form = json.load(f)

    updated = evaluate_section4(owner, repo, form)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=4)

    print(text("script4", "cli", "success", path=args.output))
    print(f"[DONE] [4.py] Sekce 4 byla zapsána do {args.output}", flush=True)


if __name__ == "__main__":
    main()
