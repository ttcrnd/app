#!/usr/bin/env python3

import argparse
import base64
import functools
import json
import os
import re
from dataclasses import dataclass
from urllib.parse import urlencode

from integrations.github import default_headers as _gh_default_headers
from integrations.http import http_get as _http_get

GITHUB_API = "https://api.github.com"

try:
    from pipeline.localization import text
except ModuleNotFoundError:  # pragma: no cover
    try:
        from localization import text
    except ModuleNotFoundError:  # pragma: no cover
        from scripts.localization import text  # type: ignore

RATING_MEETS = text("common", "ratings", "meets")
RATING_PARTIAL = text("common", "ratings", "partial")
RATING_NOT_MET = text("common", "ratings", "not_met")
ERROR_FETCH_NOTE = text("common", "errors", "fetching")


def gh_request(path, params=None, accept="application/vnd.github+json"):
    """GitHub GET request via shared utils; returns (status, headers, json_or_bytes, url)."""
    if path.startswith("http"):
        url = path
    else:
        url = f"{GITHUB_API}{path}"
        if params:
            url += "?" + urlencode(params)
    headers = _gh_default_headers()
    if accept:
        headers["Accept"] = accept
    status, content, hdrs = _http_get(url, headers=headers)

    if content:
        try:
            js = json.loads(content.decode("utf-8"))
            return status, hdrs, js, url
        except Exception:
            pass
    return status, hdrs, content, url


def gh_repo_default_branch(owner, repo):
    st, hdr, js, _ = gh_request(f"/repos/{owner}/{repo}")
    if st != 200:
        detail = js
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace")
        elif not isinstance(detail, str):
            try:
                detail = json.dumps(detail, ensure_ascii=False)
            except Exception:
                detail = str(detail)
        raise SystemExit(
            text(
                "script5",
                "errors",
                "repo_read",
                owner=owner,
                repo=repo,
                status=st,
                detail=detail,
            )
        )
    return js.get("default_branch", "main")


def gh_list_dir(owner, repo, path, ref=None):
    params = {"ref": ref} if ref else None
    st, hdr, js, _ = gh_request(f"/repos/{owner}/{repo}/contents/{path}", params=params)
    if st == 200 and isinstance(js, list):
        return js
    return []


def gh_get_file(owner, repo, path, ref=None):
    params = {"ref": ref} if ref else None
    st, hdr, js, _ = gh_request(f"/repos/{owner}/{repo}/contents/{path}", params=params)
    if st != 200 or not isinstance(js, dict):
        return None
    if js.get("encoding") == "base64":
        try:
            content = base64.b64decode(js["content"]).decode("utf-8", "replace")
            return {
                "content": content,
                "html_url": js.get("html_url"),
                "sha": js.get("sha"),
                "path": path,
            }
        except Exception:
            return None
    return None


def gh_code_search(owner, repo, query, per_page=50):
    q = f"{query} repo:{owner}/{repo}"
    st, hdr, js, url = gh_request("/search/code", params={"q": q, "per_page": per_page})
    if st != 200:

        return []
    return js.get("items", [])


def permalink(owner, repo, ref, path, start_line=None):
    base = f"https://github.com/{owner}/{repo}/blob/{ref}/{path}"
    if start_line:
        return f"{base}#L{start_line}"
    return base


def find_in_text(patterns, text, flags=re.IGNORECASE):
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            return m
    return None


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
        except Exception as exc:
            import traceback

            print(f"[WARN] [5.py] {fn.__name__} failed: {exc}", flush=True)
            traceback.print_exc()
            # Aggregator fallback: return ev map with all 5-1..5-16 set to defaults
            if fn.__name__ == "evaluate_section_5":
                ev = {}
                for i in range(1, 17):
                    ev[f"5-{i}"] = Evidence(RATING_NOT_MET, [], ERROR_FETCH_NOTE)
                return ev
            return {}

    return _wrap


@dataclass
class Evidence:
    verdict: str
    proof: list
    note: str


@_eval_log
def evaluate_section_5(owner, repo, ref):
    """
    Evaluate items 5-1 ... 5-16 for the given repo/ref (default branch or tag).
    Returns dict[id -> Evidence]

    D7: C/OpenSSL heuristics apply only when the repo looks like a C/C++ crypto
    library. Otherwise return explicit "manual / unsupported auto" evidence so
    we do not invent OpenSSL-style conclusions for Rust/Python/etc.
    """
    ev = {}

    def list_headers_under(path):
        files = gh_list_dir(owner, repo, path, ref=ref) or []
        return [f for f in files if f.get("type") == "file" and f.get("name", "").endswith(".h")]

    headers_openssl = list_headers_under("include/openssl")
    headers_generic = list_headers_under("include") if not headers_openssl else []
    headers = headers_openssl or headers_generic
    headers_names = {h.get("name", ""): h for h in headers}

    langs = gh_repo_languages(owner, repo)
    profile = classify_crypto_api_profile(langs, headers_names)
    if profile["mode"] == "manual":
        note = text(
            "script5",
            "ecosystem",
            "note_manual",
            languages=profile["summary"],
            reason=profile["reason"],
        )
        proof = [f"https://api.github.com/repos/{owner}/{repo}/languages"]
        for i in range(1, 17):
            ev[f"5-{i}"] = Evidence(RATING_PARTIAL, proof, note)
        return ev

    if profile["mode"] in ("rust", "go", "python"):
        return _evaluate_ecosystem_profile(owner, repo, ref, profile, langs)

    docs = gh_list_dir(owner, repo, "docs", ref=ref) or []
    readme = gh_get_file(owner, repo, "README.md", ref=ref) or gh_get_file(
        owner, repo, "README.rst", ref=ref
    )
    docs_index = gh_get_file(owner, repo, "docs/README.md", ref=ref) or gh_get_file(
        owner, repo, "docs/index.md", ref=ref
    )
    config_file = gh_get_file(owner, repo, "apps/openssl.cnf", ref=ref) or gh_get_file(
        owner, repo, "apps/openssl.cnf.dist", ref=ref
    )

    ctx = {
        "owner": owner,
        "repo": repo,
        "ref": ref,
        "headers_names": headers_names,
        "docs": docs,
        "readme": readme,
        "docs_index": docs_index,
        "config_file": config_file,
        "languages": langs,
        "api_profile": profile,
        "coverage_headers": [
            "evp.h",
            "aes.h",
            "rsa.h",
            "ec.h",
            "ecdsa.h",
            "ecdh.h",
            "sha.h",
            "sha256.h",
            "sha512.h",
            "md5.h",
            "hmac.h",
            "kdf.h",
            "chacha.h",
            "poly1305.h",
            "cmac.h",
            "cipher.h",
            "rand.h",
            "x509.h",
            "ssl.h",
        ],
    }

    def set_ev(qid: str, evidence: Evidence):
        ev[qid] = evidence

    set_ev("5-1", q5_1(ctx))
    set_ev("5-2", q5_2(ctx))
    set_ev("5-3", q5_3(ctx))
    set_ev("5-4", q5_4(ctx))
    set_ev("5-5", q5_5(ctx))
    set_ev("5-6", q5_6(ctx))
    set_ev("5-7", q5_7(ctx))
    set_ev("5-8", q5_8(ctx))
    set_ev("5-9", q5_9(ctx))
    set_ev("5-10", q5_10(ctx))
    set_ev("5-11", q5_11(ctx))
    set_ev("5-12", q5_12(ctx))
    set_ev("5-13", q5_13(ctx))
    set_ev("5-14", q5_14(ctx))
    set_ev("5-15", q5_15(ctx))
    set_ev("5-16", q5_16(ctx))

    return ev


def gh_repo_languages(owner: str, repo: str) -> dict[str, int]:
    status, _hdr, data, _url = gh_request(f"/repos/{owner}/{repo}/languages")
    if status == 200 and isinstance(data, dict):
        out: dict[str, int] = {}
        for key, value in data.items():
            try:
                out[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        return out
    return {}


def _evaluate_ecosystem_profile(owner, repo, ref, profile, langs) -> dict:
    """E5: Rust/Go/Python signal pack — always CONFIRM-friendly PARTIAL/MEETS with evidence."""
    from pipeline.crypto_signals import crypto_signals_note, scan_crypto_docs

    mode = profile["mode"]
    proof = [f"https://api.github.com/repos/{owner}/{repo}/languages"]
    readme = gh_get_file(owner, repo, "README.md", ref=ref) or {}
    readme_txt = ""
    if isinstance(readme, dict) and readme.get("content"):
        import base64

        try:
            readme_txt = base64.b64decode(readme["content"]).decode("utf-8", errors="replace")
        except Exception:
            readme_txt = ""
    blob = readme_txt.lower()
    cargo = gh_get_file(owner, repo, "Cargo.toml", ref=ref) if mode == "rust" else None
    docs_for_scan = [("README.md", readme_txt)]
    for path in ("SECURITY.md", "docs/crypto.md", "CONTRIBUTING.md"):
        meta = gh_get_file(owner, repo, path, ref=ref) or {}
        if isinstance(meta, dict) and meta.get("content"):
            import base64

            try:
                docs_for_scan.append(
                    (path, base64.b64decode(meta["content"]).decode("utf-8", errors="replace"))
                )
            except Exception:
                pass
    crypto = scan_crypto_docs(docs_for_scan)
    crypto_note = crypto_signals_note(crypto)
    signals = {
        "rust": {
            "5-4": ("getrandom", "osrng", "rand::"),
            "5-5": ("result<", "thiserror", "anyhow"),
            "5-12": ("result<", "eyre"),
            "5-14": ("subtle", "zeroize", "constant_time"),
        },
        "go": {
            "5-4": ("crypto/rand", "rand.read"),
            "5-5": ("error)", "fmt.Errorf"),
            "5-12": ("error)", "errors."),
            "5-14": ("subtle.", "constanttime"),
        },
        "python": {
            "5-4": ("os.urandom", "secrets.", "cryptography"),
            "5-5": ("raise ", "except "),
            "5-12": ("raise ", "exception"),
            "5-14": ("compare_digest", "hmac.compare"),
        },
    }.get(mode, {})

    base_note = (
        f"Profil {mode} ({profile['summary']}). "
        "Heuristiky jsou signály — verdikt vyžaduje potvrzení (E5)."
    )
    if crypto_note:
        base_note = f"{base_note} {crypto_note}"
    ev = {}
    for i in range(1, 17):
        qid = f"5-{i}"
        keys = signals.get(qid, ())
        hit = any(k in blob for k in keys)
        rating = RATING_PARTIAL
        note = base_note
        if hit and qid in signals:
            note = f"{base_note} Signál pro {qid}: {', '.join(keys)}."
        elif cargo and qid in ("5-4", "5-14") and isinstance(cargo, dict):
            note = f"{base_note} Cargo.toml přítomen (slabý signál pro {qid})."
        if qid in ("5-3", "5-9", "5-10") and crypto.get("has_ban_list"):
            note = f"{note} Ban-list/deprecation signál v docs."
        if qid == "5-7" and crypto.get("has_vectors"):
            note = f"{note} Test vectors / Wycheproof zmíněny."
        if qid == "5-14" and crypto.get("has_timing_tests"):
            note = f"{note} Constant-time / dudect / subtle zmíněny."
        if qid in ("5-3", "5-9", "5-10") and int(crypto.get("misuse_count") or 0) > 0:
            note = f"{note} Misuse hits≈{crypto.get('misuse_count')}."
            rating = RATING_PARTIAL
        ev[qid] = Evidence(rating, proof, note)
    return ev


def classify_crypto_api_profile(languages: dict[str, int], headers_names: dict[str, dict]) -> dict:
    """Decide crypto API automation profile (D7 + E5 language modes)."""
    total = sum(languages.values()) or 0
    c_bytes = languages.get("C", 0) + languages.get("C++", 0)
    rust_bytes = languages.get("Rust", 0)
    go_bytes = languages.get("Go", 0)
    py_bytes = languages.get("Python", 0)
    c_share = (c_bytes / total) if total else 0.0
    rust_share = (rust_bytes / total) if total else 0.0
    go_share = (go_bytes / total) if total else 0.0
    py_share = (py_bytes / total) if total else 0.0
    top = sorted(languages.items(), key=lambda kv: kv[1], reverse=True)[:5]
    summary = (
        ", ".join(
            f"{name} {share:.0%}"
            for name, share in ((n, (v / total if total else 0.0)) for n, v in top)
        )
        or "(jazyky nedostupné)"
    )
    has_openssl_headers = any(
        name in headers_names for name in ("evp.h", "ssl.h", "opensslconf.h", "crypto.h")
    ) or any("openssl" in (headers_names[n].get("path") or "").lower() for n in headers_names)

    proof = []
    if has_openssl_headers or c_share >= 0.25:
        return {
            "mode": "c_openssl",
            "summary": summary,
            "reason": "detekován C/C++ podíl a/nebo OpenSSL hlavičky",
            "proof": proof,
            "c_share": c_share,
        }
    if rust_share >= 0.4:
        return {
            "mode": "rust",
            "summary": summary,
            "reason": "dominantní Rust — ekosystémový profil (E5)",
            "proof": proof,
            "c_share": c_share,
        }
    if go_share >= 0.4:
        return {
            "mode": "go",
            "summary": summary,
            "reason": "dominantní Go — ekosystémový profil (E5)",
            "proof": proof,
            "c_share": c_share,
        }
    if py_share >= 0.4:
        return {
            "mode": "python",
            "summary": summary,
            "reason": "dominantní Python — ekosystémový profil (E5)",
            "proof": proof,
            "c_share": c_share,
        }

    return {
        "mode": "manual",
        "summary": summary,
        "reason": (
            "automatické heuristiky sekce 5 jsou vázané na C/OpenSSL nebo Rust/Go/Python; "
            "pro tento ekosystém je nutné ruční hodnocení (D7)"
        ),
        "proof": proof,
        "c_share": c_share,
    }


def _has_header(ctx, name: str) -> bool:
    return name in ctx["headers_names"]


def _proof_header(ctx, name: str) -> list:
    h = ctx["headers_names"].get(name)
    return [h.get("html_url")] if h and h.get("html_url") else []


def q5_1(ctx) -> Evidence:
    """5-1: API covers common cryptographic operations.

    Collects presence of common headers (EVP, AES, RSA, EC, SHA, HMAC, RAND, X509, SSL).
    Heuristic: meets when at least one coverage header is found; otherwise partial.
    """
    found = [n for n in ctx["coverage_headers"] if _has_header(ctx, n)]
    if found:
        proofs = sum([_proof_header(ctx, n) for n in found], [])
        return Evidence(
            RATING_MEETS,
            proofs,
            text("script5", "q5_1", "note_found", modules=", ".join(found)),
        )
    return Evidence(RATING_PARTIAL, [], text("script5", "q5_1", "note_missing"))


def q5_2(ctx) -> Evidence:
    """5-2: Understandable high-level abstractions (e.g., EVP/SSL/X509).

    Collects headers evp.h, ssl.h, x509.h to confirm friendly layers.
    """
    hi = [n for n in ["evp.h", "ssl.h", "x509.h"] if _has_header(ctx, n)]
    proofs = sum([_proof_header(ctx, n) for n in hi], [])
    verdict = RATING_MEETS if proofs else RATING_PARTIAL
    note = text("script5", "q5_2", "note")
    return Evidence(verdict, proofs, note)


def q5_3(ctx) -> Evidence:
    """5-3: Secure defaults (TLS presets, cipher suite selection).

    Collects ssl.h, openssl.cnf configuration files, and docs mentioning default/preset/seclevel with TLS.
    Heuristic: meets when configuration or documented presets exist; otherwise partial.
    """
    proofs = []
    proofs += _proof_header(ctx, "ssl.h")
    if ctx.get("config_file"):
        proofs.append(permalink(ctx["owner"], ctx["repo"], ctx["ref"], ctx["config_file"]["path"]))
    docs_default = []
    for d in ctx["docs"]:
        if d.get("type") == "file" and d.get("name", "").endswith(".md"):
            f = gh_get_file(ctx["owner"], ctx["repo"], d["path"], ref=ctx["ref"])
            if f and re.search(
                r"(default|preset|seclevel).*(cipher|suite|tls)", f["content"], re.I
            ):
                docs_default.append(permalink(ctx["owner"], ctx["repo"], ctx["ref"], d["path"]))
    proofs += docs_default
    if proofs:
        strong = bool(ctx.get("config_file") or docs_default)
        verdict = RATING_MEETS if strong else RATING_PARTIAL
        note_key = "note_strong" if strong else "note_partial"
        return Evidence(verdict, proofs, text("script5", "q5_3", note_key))
    return Evidence(RATING_PARTIAL, [], text("script5", "q5_3", "note_missing"))


def q5_4(ctx) -> Evidence:
    """5-4: CSPRNG available and promoted (e.g., RAND_bytes).

    Collects rand.h and RAND_bytes usage within the repository.
    """
    proofs = []
    proofs += _proof_header(ctx, "rand.h")
    items = gh_code_search(ctx["owner"], ctx["repo"], "RAND_bytes")
    proofs += [i.get("html_url") for i in items if i.get("html_url")]
    if proofs:
        return Evidence(
            RATING_MEETS,
            proofs,
            text("script5", "q5_4", "note_full"),
        )
    return Evidence(RATING_NOT_MET, [], text("script5", "q5_4", "note_none"))


def q5_5(ctx) -> Evidence:
    """5-5: Errors are understandable (no secret leakage).

    Collects err.h, ERR_error_string occurrences, and potential error-mapping helpers.
    """
    proofs = []
    err_hdr = gh_get_file(ctx["owner"], ctx["repo"], "include/openssl/err.h", ref=ctx["ref"])
    if err_hdr:
        proofs.append(permalink(ctx["owner"], ctx["repo"], ctx["ref"], err_hdr["path"]))
    elif _has_header(ctx, "err.h"):
        proofs += _proof_header(ctx, "err.h")
    items = gh_code_search(ctx["owner"], ctx["repo"], "ERR_error_string")
    proofs += [i.get("html_url") for i in items if i.get("html_url")]
    if proofs:
        return Evidence(
            RATING_MEETS,
            proofs,
            text("script5", "q5_5", "note_full"),
        )
    return Evidence(RATING_PARTIAL, [], text("script5", "q5_5", "note_none"))


def q5_6(ctx) -> Evidence:
    """5-6: Explicit key/IV generation and handling.

    Collects calls to RSA_generate_key_ex, EC_KEY_generate_key, EVP_PKEY_keygen, EVP_CIPHER_CTX_ctrl, RAND_bytes, plus relevant headers.
    """
    items = (
        gh_code_search(ctx["owner"], ctx["repo"], "EVP_PKEY_keygen")
        + gh_code_search(ctx["owner"], ctx["repo"], "RSA_generate_key_ex")
        + gh_code_search(ctx["owner"], ctx["repo"], "EC_KEY_generate_key")
        + gh_code_search(ctx["owner"], ctx["repo"], "EVP_CIPHER_CTX_ctrl")
        + gh_code_search(ctx["owner"], ctx["repo"], "RAND_bytes")
    )
    proofs = [i.get("html_url") for i in items if i.get("html_url")]
    for n in ["evp.h", "rsa.h", "ec.h", "cipher.h", "rand.h"]:
        if _has_header(ctx, n):
            proofs += _proof_header(ctx, n)
    if proofs:
        return Evidence(
            RATING_MEETS,
            proofs,
            text("script5", "q5_6", "note_full"),
        )
    return Evidence(RATING_PARTIAL, [], text("script5", "q5_6", "note_none"))


def q5_7(ctx) -> Evidence:
    """5-7: Runtime parameter checks (guardrails/assert).

    Collects OPENSSL_assert/ossl_assert and similar guard patterns.
    """
    items = gh_code_search(ctx["owner"], ctx["repo"], "OPENSSL_assert") + gh_code_search(
        ctx["owner"], ctx["repo"], "ossl_assert"
    )
    proofs = [i.get("html_url") for i in items if i.get("html_url")]
    if proofs:
        return Evidence(
            RATING_PARTIAL,
            proofs,
            text("script5", "q5_7", "note_found"),
        )
    return Evidence(RATING_PARTIAL, [], text("script5", "q5_7", "note_none"))


def q5_8(ctx) -> Evidence:
    """5-8: Transparent mapping of high-level abstractions to algorithms.

    Collects docs in docs/* describing EVP/provider/FIPS relationships and includes evp.h when present.
    """
    proofs = []
    for d in ctx["docs"]:
        if d.get("type") == "file" and d.get("name", "").endswith(".md"):
            f = gh_get_file(ctx["owner"], ctx["repo"], d["path"], ref=ctx["ref"])
            if f and re.search(
                r"\bEVP\b.*(algorithm|cipher|curve|hash)|\bprovider\b|\bFIPS\b",
                f["content"],
                re.I | re.S,
            ):
                proofs.append(permalink(ctx["owner"], ctx["repo"], ctx["ref"], d["path"]))
    if proofs or _has_header(ctx, "evp.h"):
        proofs += _proof_header(ctx, "evp.h")
        return Evidence(
            RATING_PARTIAL,
            proofs,
            text("script5", "q5_8", "note_some"),
        )
    return Evidence(RATING_PARTIAL, [], text("script5", "q5_8", "note_none"))


def q5_9(ctx) -> Evidence:
    """5-9: Parameter overrides with friction or warnings.

    Collects 'deprecated', 'insecure', 'LEGACY' occurrences and related configuration files.
    """
    proofs = []
    insecure = (
        gh_code_search(ctx["owner"], ctx["repo"], "deprecated")
        + gh_code_search(ctx["owner"], ctx["repo"], "insecure")
        + gh_code_search(ctx["owner"], ctx["repo"], "LEGACY")
    )
    proofs += [i.get("html_url") for i in insecure if i.get("html_url")]
    if ctx.get("config_file"):
        proofs.append(permalink(ctx["owner"], ctx["repo"], ctx["ref"], ctx["config_file"]["path"]))
    if proofs:
        return Evidence(
            RATING_PARTIAL,
            proofs,
            text("script5", "q5_9", "note"),
        )
    return Evidence(RATING_PARTIAL, [], text("script5", "q5_9", "note_none"))


def q5_10(ctx) -> Evidence:
    """5-10: Risky choices clearly marked as unsuitable.

    Collects searches such as 'MD5 deprecated', 'SHA1 deprecated', 'RC4 deprecated', etc.
    """
    bads = ["MD5", "SHA1", "RC4", "DES", "ECB"]
    proofs = []
    for b in bads:
        items = gh_code_search(ctx["owner"], ctx["repo"], b + " deprecated")
        proofs += [i.get("html_url") for i in items if i.get("html_url")]
    if proofs:
        return Evidence(
            RATING_PARTIAL,
            proofs,
            text("script5", "q5_10", "note"),
        )
    return Evidence(RATING_PARTIAL, [], text("script5", "q5_10", "note_none"))


def q5_11(ctx) -> Evidence:
    """5-11: Strictly typed API (as far as C allows).

    Collects headers with opaque structures (cipher.h, evp.h, ec.h) to indicate type safety.
    """
    proofs = []
    for n in ["cipher.h", "evp.h", "ec.h"]:
        if _has_header(ctx, n):
            proofs += _proof_header(ctx, n)
    return Evidence(
        RATING_PARTIAL,
        proofs,
        text("script5", "q5_11", "note"),
    )


def q5_12(ctx) -> Evidence:
    """5-12: Exceptions/monadic types.

    Context: not applicable for C; uses return codes and ERR_* API, so rated partial.
    """
    return Evidence(RATING_PARTIAL, [], text("script5", "q5_12", "note"))


def q5_13(ctx) -> Evidence:
    """5-13: Combined steps / fluent interface.

    Context: C APIs are procedural; fluent chaining is uncommon.
    """
    return Evidence(RATING_PARTIAL, [], text("script5", "q5_13", "note"))


def q5_14(ctx) -> Evidence:
    """5-14: Auxiliary safety functions (zeroize, constant-time compare)."""
    proofs = []
    if _has_header(ctx, "crypto.h"):
        proofs += _proof_header(ctx, "crypto.h")
    items = (
        gh_code_search(ctx["owner"], ctx["repo"], "CRYPTO_memcmp")
        + gh_code_search(ctx["owner"], ctx["repo"], "OPENSSL_cleanse")
        + gh_code_search(ctx["owner"], ctx["repo"], "timingsafe_memcmp")
    )
    proofs += [i.get("html_url") for i in items if i.get("html_url")]
    if proofs:
        return Evidence(
            RATING_MEETS,
            proofs,
            text("script5", "q5_14", "note_full"),
        )
    return Evidence(RATING_PARTIAL, [], text("script5", "q5_14", "note_none"))


def q5_15(ctx) -> Evidence:
    """5-15: Compliance with language safety standards (MISRA/CERT-C).

    Collects references to guidelines in code or documentation via search.
    """
    proofs = []
    proofs += [
        i.get("html_url")
        for i in gh_code_search(ctx["owner"], ctx["repo"], "MISRA")
        if i.get("html_url")
    ]
    proofs += [
        i.get("html_url")
        for i in gh_code_search(ctx["owner"], ctx["repo"], "CERT C")
        if i.get("html_url")
    ]
    if proofs:
        return Evidence(
            RATING_PARTIAL,
            proofs,
            text("script5", "q5_15", "note"),
        )
    return Evidence(RATING_PARTIAL, [], text("script5", "q5_15", "note_none"))


def q5_16(ctx) -> Evidence:
    """5-16: Test mode with reduced security is clearly separated.

    Collects build flags such as FUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION and mentions of 'test mode'.
    """
    proofs = []
    proofs += [
        i.get("html_url")
        for i in gh_code_search(
            ctx["owner"], ctx["repo"], "FUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION"
        )
        if i.get("html_url")
    ]
    proofs += [
        i.get("html_url")
        for i in gh_code_search(ctx["owner"], ctx["repo"], "test mode")
        if i.get("html_url")
    ]
    if proofs:
        return Evidence(
            RATING_PARTIAL,
            proofs,
            text("script5", "q5_16", "note"),
        )
    return Evidence(RATING_PARTIAL, [], text("script5", "q5_16", "note_none"))


def load_form(path):
    if not path:
        return {
            "title": text("script5", "form", "title"),
            "version": text("script5", "form", "version"),
            "language": text("script5", "form", "language"),
            "sections": [
                {
                    "id": "5-sec:api",
                    "title": text("script5", "form", "section_title"),
                    "questions": [
                        {
                            "id": f"5-{i}",
                            "text": "",
                            "rating": None,
                            "note": "",
                            "category": text("script5", "form", "category"),
                            "description": "",
                            "evidence": "",
                        }
                        for i in range(1, 17)
                    ],
                }
            ],
        }
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_form(form, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(form, f, ensure_ascii=False, indent=4)


def fill_section_5(form, ev_map, requested_ref=None, effective_ref=None):
    sections = form.get("sections")
    if sections is None:
        sections = form.get("sekce", [])
    sec = next((s for s in sections if str(s.get("id")) == "5-sec:api"), None)
    if not sec:
        raise SystemExit(text("script5", "errors", "missing_section"))
    sec_meta = sec.setdefault("meta", {})
    if isinstance(sec_meta, dict):
        sec_meta["requested_ref"] = requested_ref
        sec_meta["effective_ref"] = effective_ref
        # Preserve ecosystem note from first question if present (D7).
        sample = next(iter(ev_map.values()), None)
        if sample and "D7:" in str(sample.note):
            sec_meta["crypto_api_automation"] = "manual_non_c"
        else:
            sec_meta["crypto_api_automation"] = "c_openssl_heuristics"

    questions = sec.get("questions")
    if questions is None:
        questions = sec.get("otazky", [])
    by_id = {q["id"]: q for q in questions}
    for qid, ev in ev_map.items():
        q = by_id.get(qid)
        if not q:
            continue
        evidence_text = "\n".join(sorted(set(ev.proof)))
        q["rating"] = ev.verdict
        q["note"] = ev.note
        q["evidence"] = evidence_text
        q["heuristic_rating"] = True
        if "hodnoceni" in q:
            q["hodnoceni"] = ev.verdict
        if "poznamka" in q:
            q["poznamka"] = ev.note
        if "dukaz" in q:
            q["dukaz"] = evidence_text
    return form


def main():
    ap = argparse.ArgumentParser(description=text("script5", "cli", "description"))
    ap.add_argument("--owner", required=True, help=text("script5", "cli", "help_owner"))
    ap.add_argument("--repo", required=True, help=text("script5", "cli", "help_repo"))
    ap.add_argument(
        "--ref",
        default=None,
        help=text("script5", "cli", "help_ref"),
    )
    ap.add_argument("--input", help=text("script5", "cli", "help_input"))
    ap.add_argument("--output", required=True, help=text("script5", "cli", "help_output"))
    args = ap.parse_args()

    print(
        f"[START] [5.py] Zahajuji vyhodnocení sekce 5 pro {args.owner}/{args.repo}",
        flush=True,
    )
    requested_ref = args.ref or os.environ.get("REPO_REF", "").strip() or None
    ref = requested_ref or gh_repo_default_branch(args.owner, args.repo)
    print(f"[INFO] [5.py] Použitý ref pro vyhodnocení: {ref}", flush=True)
    print("[INFO] [5.py] Kontroluji kryptografické API signály a bezpečnostní prvky.", flush=True)
    ev_map = evaluate_section_5(args.owner, args.repo, ref)
    form = load_form(args.input)
    form = fill_section_5(form, ev_map, requested_ref=requested_ref, effective_ref=ref)
    save_form(form, args.output)

    print(text("script5", "cli", "success", path=args.output))
    print(text("script5", "cli", "note"))
    print(text("script5", "cli", "hint"))
    print(f"[DONE] [5.py] Sekce 5 byla zapsána do {args.output}", flush=True)


if __name__ == "__main__":
    main()
