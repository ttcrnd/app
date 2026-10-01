from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module {module_name} from {file_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"
m1 = _load_module("mod1", _SCRIPTS / "1.py")
m2 = _load_module("mod2", _SCRIPTS / "2.py")
m3 = _load_module("mod3", _SCRIPTS / "3.py")
m4 = _load_module("mod4", _SCRIPTS / "4.py")
m5 = _load_module("mod5", _SCRIPTS / "5.py")

OWNER = "Mbed-TLS"
REPO = "mbedtls"
OWNER_REPO = f"{OWNER}/{REPO}"


def _load_form(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_form(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_end_to_end_aggregate(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    skeleton = root / "assets" / "questions.json"
    assert skeleton.exists(), "assets/questions.json must exist for the test"

    out_dir = tmp_path
    work = out_dir / "form.json"
    work.write_text(skeleton.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr(
        m1,
        "repo_info",
        lambda owner, repo, token: {
            "html_url": f"https://github.com/{OWNER_REPO}",
            "default_branch": "main",
            "license": {"spdx_id": "Apache-2.0"},
            "description": "Test repo",
            "stargazers_count": 10000,
            "forks_count": 1000,
            "subscribers_count": 500,
            "created_at": "2020-01-01T00:00:00Z",
            "pushed_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "has_downloads": True,
            "has_issues": True,
            "has_projects": True,
            "has_wiki": True,
            "topics": ["crypto"],
        },
    )
    monkeypatch.setattr(
        m1,
        "org_info",
        lambda owner, token: {
            "html_url": f"https://github.com/{owner}",
            "is_verified": True,
            "login": owner,
            "type": "Organization",
        },
    )
    monkeypatch.setattr(
        m1,
        "latest_release",
        lambda o, r, t: {
            "html_url": f"https://github.com/{OWNER_REPO}/releases/tag/v1.0.0",
            "tag_name": "v1.0.0",
            "published_at": "2025-01-01T00:00:00Z",
            "prerelease": False,
            "body": "Fixes CVE-2024-0001",
        },
    )
    monkeypatch.setattr(m1, "list_releases", lambda o, r, t: [{"tag_name": "v1.0.0"}])
    monkeypatch.setattr(m1, "list_tags", lambda o, r, t: [{"name": "v1.0.0"}])
    monkeypatch.setattr(
        m1,
        "get_commit",
        lambda o, r, sha, t: {"commit": {"verification": {"verified": True, "reason": "valid"}}},
    )
    monkeypatch.setattr(m1, "languages", lambda o, r, t: {"C": 999999})
    monkeypatch.setattr(
        m1,
        "readme",
        lambda o, r, t: {"html_url": f"https://github.com/{OWNER_REPO}/blob/main/README.md"},
    )
    monkeypatch.setattr(
        m1,
        "search_code",
        lambda o, r, t, q: {
            "query": q,
            "total_count": 1,
            "examples": [
                {
                    "path": "scripts/install.sh",
                    "url": f"https://github.com/{OWNER_REPO}/blob/main/scripts/install.sh",
                    "fragment": "curl | sh",
                }
            ],
        },
    )
    monkeypatch.setattr(
        m1,
        "suspicious_search_pack",
        lambda o, r, t: [
            {"query": "curl|sh", "total_count": 0, "examples": []},
            {"query": "wget http", "total_count": 0, "examples": []},
        ],
    )

    out1 = m1.build_output(OWNER, REPO, token=None)
    m1._merge_into_form(str(work), str(work), out1["sekce_1"], out1.get("raw_evidence"))

    monkeypatch.setattr(
        m2,
        "gh_repo",
        lambda o, r: {
            "default_branch": "main",
            "license": {"spdx_id": "Apache-2.0"},
            "stargazers_count": 1200,
            "forks_count": 300,
            "subscribers_count": 200,
            "topics": ["crypto"],
        },
    )
    monkeypatch.setattr(
        m2,
        "gh_all_releases",
        lambda o, r, limit=100: [{"name": "v1.0.0", "tag_name": "v1.0.0", "body": "notes"}],
    )
    monkeypatch.setattr(
        m2,
        "gh_latest_release",
        lambda o, r: {
            "name": "v1.0.0",
            "tag_name": "v1.0.0",
            "published_at": "2025-01-01T00:00:00Z",
            "prerelease": False,
            "body": "CVE-2024-0001",
        },
    )
    monkeypatch.setattr(
        m2, "gh_commits_since", lambda o, r, since_days=365, branch=None, limit=3000: [{}] * 30
    )
    monkeypatch.setattr(
        m2,
        "gh_issues_last_year",
        lambda o, r, issue_state="all", limit=200: [{"number": 1, "author_association": "MEMBER"}],
    )
    monkeypatch.setattr(
        m2, "gh_issue_comments", lambda o, r, number: [{"author_association": "MEMBER"}]
    )
    monkeypatch.setattr(m2, "gh_repo_file_exists", lambda o, r, p: True)
    monkeypatch.setattr(m2, "gh_actions_exists", lambda o, r: True)
    monkeypatch.setattr(
        m2, "gh_search_code", lambda o, r, q, per_page=50: [{"path": "tests/test_something.c"}]
    )
    monkeypatch.setattr(
        m2,
        "gh_contributors",
        lambda o, r, limit=200: [{"type": "User"}, {"type": "User"}, {"type": "User"}],
    )
    monkeypatch.setattr(m2, "osv_query_github_repo", lambda o, r: [])

    form2 = _load_form(work)
    target2 = None
    for s in form2.get("sections", []):
        if str(s.get("id")) == "2":
            target2 = s
            break
    assert target2 is not None, "Section 2 must exist in skeleton"
    enriched2 = m2.evaluate_open_source_section(OWNER, REPO, target2)
    for i, s in enumerate(form2.get("sections", [])):
        if str(s.get("id")) == "2":
            form2["sections"][i] = enriched2
            break
    _save_form(work, form2)

    evidence3 = {
        "repo_meta": {"html_url": f"https://github.com/{OWNER_REPO}", "languages": {"C": 1000}},
        "presence_files": {
            "CONTRIBUTING.md": f"https://github.com/{OWNER_REPO}/blob/main/CONTRIBUTING.md",
            ".clang-format": f"https://github.com/{OWNER_REPO}/blob/main/.clang-format",
            ".clang-tidy": f"https://github.com/{OWNER_REPO}/blob/main/.clang-tidy",
            ".editorconfig": f"https://github.com/{OWNER_REPO}/blob/main/.editorconfig",
            ".github/workflows": f"https://github.com/{OWNER_REPO}/tree/main/.github/workflows",
        },
        "readme": {"coverage_mentions": ["coverage"], "ci_mentions": ["ci"], "links": []},
        "actions": {
            "workflows": [
                {
                    "name": "ci",
                    "state": "active",
                    "path": ".github/workflows/ci.yml",
                    "url": f"https://github.com/{OWNER_REPO}/blob/main/.github/workflows/ci.yml",
                    "hints": ["lint", "tests", "coverage"],
                }
            ],
            "signals": {
                "lint": True,
                "sast": True,
                "tests": True,
                "coverage": True,
                "fuzz": True,
                "sanitizers": True,
            },
        },
        "code_scanning": {"status": 200, "count": 0},
        "oss_fuzz": {
            "project_report_url": "https://introspector.oss-fuzz.com/project/mbedtls",
            "overview_hit": True,
        },
        "fuzz_dirs": {"fuzz": f"https://github.com/{OWNER_REPO}/tree/main/fuzz"},
    }
    section3 = m3.assess_section_3(evidence3)
    m3._merge_section3_into_form(str(work), str(work), section3)

    readme_text = """
    # Mbed TLS
    Install: use cmake && make
    API reference on Read the Docs
    Example:
    ```c
    int main() { return 0; }
    ```
    Deprecated: SHA-1
    How-to: Getting started
    """
    monkeypatch.setattr(
        m4,
        "repo_meta",
        lambda o, r: {"homepage": "https://mbedtls.readthedocs.io", "topics": ["crypto"]},
    )
    monkeypatch.setattr(
        m4,
        "gh_get_readme",
        lambda o, r: (readme_text, f"https://github.com/{OWNER_REPO}/blob/main/README.md"),
    )
    monkeypatch.setattr(
        m4,
        "list_tree",
        lambda o, r, branch="HEAD": [
            "docs/index.md",
            "docs/conf.py",
            "examples/a.c",
            "SECURITY.md",
            "README.md",
            "Doxyfile",
        ],
    )
    monkeypatch.setattr(m4, "http_head_ok", lambda url: True)
    monkeypatch.setattr(
        m4, "http_get_text", lambda url, max_bytes=500_000: '<html><input role="search"></html>'
    )

    def fake_gh_get(path, params=None):
        content = base64.b64encode(
            b"Install and API reference. Deprecated: SHA-1. How-to present."
        ).decode("ascii")
        return {
            "type": "file",
            "encoding": "base64",
            "content": content,
            "html_url": f"https://github.com/{OWNER_REPO}/blob/main/{path.split('/contents/')[-1]}",
        }

    monkeypatch.setattr(m4, "gh_get", fake_gh_get)

    def fake_gh_get_contents(owner, repo, path=""):
        if (
            path.endswith("INSTALL.md")
            or path.endswith("README.md")
            or path.endswith("docs/index.md")
        ):
            return [{"type": "file", "encoding": "base64", "content": ""}]
        return []

    monkeypatch.setattr(m4, "gh_get_contents", fake_gh_get_contents)

    form4 = _load_form(work)
    updated4 = m4.evaluate_section4(OWNER, REPO, form4)
    _save_form(work, updated4)

    def fake_list_dir(owner, repo, path, ref=None):
        if path == "include/mbedtls":
            files = [
                "aes.h",
                "gcm.h",
                "ccm.h",
                "chacha20.h",
                "chachapoly.h",
                "poly1305.h",
                "sha256.h",
                "sha512.h",
                "md.h",
                "md5.h",
                "cipher.h",
                "pk.h",
                "rsa.h",
                "ecp.h",
                "ecdsa.h",
                "ecdh.h",
                "hkdf.h",
                "tls.h",
                "ssl.h",
                "ssl_ciphersuites.h",
                "ctr_drbg.h",
                "hmac_drbg.h",
                "entropy.h",
                "x509.h",
                "x509_crt.h",
                "check_config.h",
                "platform_util.h",
            ]
            return [
                {
                    "type": "file",
                    "name": n,
                    "path": f"include/mbedtls/{n}",
                    "html_url": f"https://github.com/{OWNER_REPO}/blob/main/include/mbedtls/{n}",
                }
                for n in files
            ]
        if path == "include/psa":
            return [
                {
                    "type": "file",
                    "name": "crypto.h",
                    "path": "include/psa/crypto.h",
                    "html_url": f"https://github.com/{OWNER_REPO}/blob/main/include/psa/crypto.h",
                }
            ]
        if path == "docs":
            return [{"type": "file", "name": "defaults.md", "path": "docs/defaults.md"}]
        return []

    monkeypatch.setattr(m5, "gh_list_dir", fake_list_dir)

    def fake_get_file(owner, repo, path, ref=None):

        if path.endswith("config.h") or path.endswith("mbedtls_config.h"):
            return {
                "path": path,
                "html_url": f"https://github.com/{OWNER_REPO}/blob/main/{path}",
                "content": "#define MBEDTLS_CHECK_PARAMS 1",
            }
        if (
            path.endswith("error.h")
            or path.endswith("library/error.c")
            or path.endswith("platform_util.h")
        ):
            return {
                "path": path,
                "html_url": f"https://github.com/{OWNER_REPO}/blob/main/{path}",
                "content": "int mbedtls_strerror(int);",
            }
        if path.endswith("docs/defaults.md"):
            return {
                "path": path,
                "html_url": f"https://github.com/{OWNER_REPO}/blob/main/{path}",
                "content": "default ciphersuite preset",
            }
        if path.endswith("check_config.h"):
            return {
                "path": path,
                "html_url": f"https://github.com/{OWNER_REPO}/blob/main/{path}",
                "content": "#define MBEDTLS_CHECK_PARAMS",
            }
        return None

    monkeypatch.setattr(m5, "gh_get_file", fake_get_file)

    def fake_code_search(owner, repo, query, per_page=50):
        hits = {
            "mbedtls_ctr_drbg_random": [
                {"html_url": f"https://github.com/{OWNER_REPO}/blob/main/programs/random.c"}
            ],
            "mbedtls_hmac_drbg_random": [
                {"html_url": f"https://github.com/{OWNER_REPO}/blob/main/programs/random_hmac.c"}
            ],
            "mbedtls_strerror": [
                {"html_url": f"https://github.com/{OWNER_REPO}/blob/main/library/error.c"}
            ],
            "ecp_gen_keypair": [
                {"html_url": f"https://github.com/{OWNER_REPO}/blob/main/library/ecp.c"}
            ],
            "rsa_gen_key": [
                {"html_url": f"https://github.com/{OWNER_REPO}/blob/main/library/rsa.c"}
            ],
            "cipher_set_iv": [
                {"html_url": f"https://github.com/{OWNER_REPO}/blob/main/library/cipher.c"}
            ],
            "MBEDTLS_CHECK_PARAMS": [
                {
                    "html_url": f"https://github.com/{OWNER_REPO}/blob/main/include/mbedtls/check_config.h"
                }
            ],
            "constant time compare": [
                {"html_url": f"https://github.com/{OWNER_REPO}/blob/main/library/ct.c"}
            ],
            "MISRA": [],
            "CERT C": [],
            "deprecated": [
                {"html_url": f"https://github.com/{OWNER_REPO}/blob/main/include/mbedtls/md5.h"}
            ],
            "insecure": [],
            "LEGACY": [],
            "test mode": [],
        }
        for k, v in hits.items():
            if k in query:
                return v
        return []

    monkeypatch.setattr(m5, "gh_code_search", fake_code_search)
    monkeypatch.setattr(m5, "gh_repo_default_branch", lambda o, r: "main")

    ev5 = m5.evaluate_section_5(OWNER, REPO, ref="main")
    form5 = _load_form(work)
    form5 = m5.fill_section_5(form5, ev5)
    _save_form(work, form5)

    final_form = _load_form(work)

    sec1 = next(s for s in final_form["sections"] if str(s.get("id")) == "1")
    for q in sec1["questions"]:
        if q["id"] in ("1-1", "1-2", "1-3"):
            assert isinstance(q.get("evidence"), str) and len(q.get("evidence")) >= 0

    sec2 = next(s for s in final_form["sections"] if str(s.get("id")) == "2")
    for q in sec2["questions"]:
        assert q.get("rating") is not None
        assert isinstance(q.get("evidence"), str)

    sec3 = next(s for s in final_form["sections"] if str(s.get("id")) == "3")
    for q in sec3["questions"]:
        assert isinstance(q.get("evidence"), str)

    sec4 = next(s for s in final_form["sections"] if str(s.get("id")) == "4")
    for q in sec4["questions"]:
        assert q.get("rating") in ("splňuje", "částečně splňuje", "nesplňuje")
        assert isinstance(q.get("evidence"), str)

    sec5 = next(s for s in final_form["sections"] if str(s.get("id")) == "5-sec:api")
    ids_5 = {q["id"] for q in sec5["questions"]}
    assert all(f"5-{i}" in ids_5 for i in range(1, 17))
    for q in sec5["questions"]:
        assert q.get("rating") in ("splňuje", "částečně splňuje", "nesplňuje")
        assert isinstance(q.get("evidence"), str)

    files = []
    for p in sorted(tmp_path.rglob("*")):
        if p.is_file():
            try:
                rel = p.relative_to(tmp_path)
            except Exception:
                rel = p
            files.append(str(rel))
    print("\n[artifacts] test_end_to_end_aggregate generated:")
    for f in files:
        print(f" - {f}")
