"""Regression tests for the 'Known issues' list (stav k 1. 10. 2026).

Each test pins one fix: API errors no longer rate as "has releases", activity
counts only last-12-month releases, 2-7 needs tests to be *required* on PRs,
2-10 only links an existing CODEOWNERS, CI workflows are actually loaded, and
1-1 refuses to confirm a fork.

Evaluators are wrapped in _eval_log, which swallows exceptions into a
"nesplňuje" fallback — so assertions check notes, not just ratings.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import integrations.github as gh  # noqa: E402
from pipeline.sections import section_01_prerequisites as s1  # noqa: E402
from pipeline.sections import section_02_oss_quality as s2  # noqa: E402

MEETS, PARTIAL, NOT_MET = s2.RATING_MEETS, s2.RATING_PARTIAL, s2.RATING_NOT_MET
RATE_LIMIT_BODY = {
    "message": "API rate limit exceeded",
    "documentation_url": "https://docs.github.com/rest",
}


def _iso(days_ago: int) -> str:
    ts = s2.NOW - datetime.timedelta(days=days_ago)
    return ts.strftime(s2.ISO)


def _ctx(**overrides):
    ctx = {
        "commits_cnt": 0,
        "issues_count": 0,
        "releases": [],
        "releases_last_year": [],
        "releases_error": None,
        "latest_rel": None,
        "last_release_ok": False,
        "last_rel_is_prerelease": False,
        "last_rel_name": "",
        "last_rel_date_str": "n/a",
        "project_active": False,
        "has_tests": False,
        "urls": {
            "repo": "https://github.com/o/r",
            "releases": "https://github.com/o/r/releases",
            "tests": "https://github.com/o/r/tree/HEAD/tests",
            "codeowners": None,
        },
    }
    ctx.update(overrides)
    return ctx


# --- 2-16 / 3-2 / 3-5: wrapped list responses ---------------------------------


def test_paginate_unwraps_workflows_object(monkeypatch):
    payload = {"total_count": 2, "workflows": [{"path": "a.yml"}, {"path": "b.yml"}]}
    monkeypatch.setattr(gh, "get", lambda *a, **k: (200, payload, {}))
    assert gh.paginate("/repos/o/r/actions/workflows", list_key="workflows") == payload["workflows"]


def test_paginate_without_list_key_still_ignores_objects(monkeypatch):
    # Pins the old behaviour for callers that expect bare arrays.
    monkeypatch.setattr(gh, "get", lambda *a, **k: (200, {"workflows": [{}]}, {}))
    assert gh.paginate("/repos/o/r/actions/workflows") == []


def test_section3_loads_workflows_and_skips_disabled_and_dynamic(monkeypatch):
    from pipeline.sections import section_03_code_quality as s3

    seen = {}

    def fake_paginate(path, per_page=100, max_pages=10, list_key=None):
        seen["list_key"] = list_key
        return [
            {"name": "CI", "state": "active", "path": ".github/workflows/ci.yml"},
            {"name": "old", "state": "disabled_manually", "path": ".github/workflows/old.yml"},
            {
                "name": "CodeQL",
                "state": "active",
                "path": "dynamic/github-code-scanning/codeql",
                "html_url": "https://github.com/o/r/actions/workflows/codeql",
            },
        ]

    yaml = {
        ".github/workflows/ci.yml": "run: pytest\nuses: codecov/codecov-action\nrun: clang-tidy -Werror",
        ".github/workflows/old.yml": "uses: google/oss-fuzz with libfuzzer",
    }
    monkeypatch.setattr(s3, "_gh_paginate", fake_paginate)
    monkeypatch.setattr(s3, "get_file_text", lambda path: yaml.get(path))
    monkeypatch.setattr(s3, "save_raw", lambda *a, **k: "")
    monkeypatch.setattr(s3, "OWNER", "o")
    monkeypatch.setattr(s3, "REPO_NAME", "r")

    out = s3.collect_actions_and_checks()
    sig = out["signals"]
    assert seen["list_key"] == "workflows"
    assert sig["tests"] and sig["coverage"] and sig["lint"] and sig["strict"]
    assert sig["sast"]  # from GitHub-managed CodeQL default setup
    assert not sig["fuzz"]  # only the disabled workflow fuzzes
    paths = [w["path"] for w in out["workflows"]]
    assert ".github/workflows/old.yml" not in paths
    codeql = next(w for w in out["workflows"] if w["path"].startswith("dynamic/"))
    assert "/blob/" not in codeql["url"]


@pytest.mark.parametrize(
    "yml,expected",
    [("uses: actions/waffle", False), ("run: cargo fuzz run target", True)],
)
def test_section3_short_keywords_need_word_start(yml, expected):
    from pipeline.sections import section_03_code_quality as s3

    assert s3.has_workflow_keyword(yml, "afl", "fuzz") is expected


def test_actions_exists_false_on_api_error(monkeypatch):
    monkeypatch.setattr(s2, "_gh_get", lambda *a, **k: (403, RATE_LIMIT_BODY, {}))
    monkeypatch.setattr(s2, "gh_search_code", lambda *a, **k: [])
    assert s2.gh_actions_exists("o", "r") is False
    monkeypatch.setattr(gh, "get", lambda *a, **k: (403, RATE_LIMIT_BODY, {}))
    monkeypatch.setattr(gh, "search_code", lambda *a, **k: {})
    assert gh.actions_exists("o", "r") is False


# --- 2-1 / 2-1a / 2-1b / 2-1d: releases --------------------------------------


def test_release_api_error_raises_instead_of_leaking_error_body(monkeypatch):
    monkeypatch.setattr(s2, "_gh_get", lambda *a, **k: (403, RATE_LIMIT_BODY, {}))
    with pytest.raises(s2.GitHubApiError, match="403"):
        s2.gh_all_releases("o", "r")
    with pytest.raises(s2.GitHubApiError):
        s2.gh_latest_release("o", "r")


def test_latest_release_404_means_no_release(monkeypatch):
    monkeypatch.setattr(s2, "_gh_get", lambda *a, **k: (404, {"message": "Not Found"}, {}))
    assert s2.gh_latest_release("o", "r") is None


def test_releases_within_drops_old_and_draft():
    rels = [
        {"tag_name": "new", "published_at": _iso(30)},
        {"tag_name": "old", "published_at": _iso(800)},
        {"tag_name": "draft", "published_at": _iso(10), "draft": True},
        {"tag_name": "unpublished", "published_at": None},
    ]
    assert [r["tag_name"] for r in s2.releases_within(rels, 365)] == ["new"]


def test_2_1_old_releases_do_not_make_project_active():
    old = [{"published_at": _iso(900)}, {"published_at": _iso(1200)}]
    recent = s2.releases_within(old, 365)
    assert s2.is_project_active(0, recent) is False
    assert s2.is_project_active(0, [{"published_at": _iso(10)}] * 2) is True
    rating, note, _ = s2.evaluate_q_2_1(
        _ctx(releases=old, releases_last_year=recent, project_active=False)
    )
    assert rating == PARTIAL
    assert "release za 12 měsíců: 0" in note


def test_fetch_releases_keeps_list_when_latest_fails(monkeypatch):
    def fake_get(path, params=None):
        if path.endswith("/releases/latest"):
            return 502, {"message": "Bad Gateway"}, {}
        return 200, [{"tag_name": "v1", "published_at": _iso(5)}], {}

    monkeypatch.setattr(s2, "_gh_get", fake_get)
    releases, latest, error = s2.fetch_releases("o", "r")
    assert [r["tag_name"] for r in releases] == ["v1"]
    assert latest is None
    assert error and "502" in error


def test_fetch_releases_rate_limited_returns_error_not_data(monkeypatch):
    monkeypatch.setattr(s2, "_gh_get", lambda *a, **k: (403, RATE_LIMIT_BODY, {}))
    releases, latest, error = s2.fetch_releases("o", "r")
    assert releases == [] and latest is None
    assert "403" in error
    assert s2.is_project_active(0, s2.releases_within(releases)) is False


def test_2_1_family_api_error_is_partial_with_explanation():
    ctx = _ctx(releases_error="HTTP 403 na /repos/o/r/releases (API rate limit exceeded)")
    for fn in (s2.evaluate_q_2_1, s2.evaluate_q_2_1a, s2.evaluate_q_2_1b, s2.evaluate_q_2_1d):
        rating, note, _ = fn(ctx)
        assert rating == PARTIAL, fn.__name__
        assert "chyba GitHub API" in note, fn.__name__


def test_2_1b_no_activity_without_error_is_still_not_met():
    rating, note, _ = s2.evaluate_q_2_1b(_ctx())
    assert rating == NOT_MET
    assert "releasy (12m): 0" in note


# --- 2-7: tests must be required, not just present ---------------------------


def test_2_7_tests_present_only_is_partial():
    rating, note, _ = s2.evaluate_q_2_7(_ctx(has_tests=True))
    assert rating == PARTIAL
    assert "neověřeno" in note and "nenalezen v CONTRIBUTING" in note


def test_2_7_meets_when_tests_run_on_prs_and_are_required():
    ctx = _ctx(
        has_tests=True,
        scorecard_map={"checks": {"CI-Tests": 9}, "urls": {}},
        tests_required_in_contributing=True,
        contributing_url="https://github.com/o/r/blob/HEAD/CONTRIBUTING.md",
    )
    rating, note, evidence = s2.evaluate_q_2_7(ctx)
    assert rating == MEETS
    assert "Scorecard CI-Tests=9" in note
    assert "CONTRIBUTING.md" in evidence


def test_2_7_ruleset_counts_as_pr_check_but_needs_policy_too():
    ctx = _ctx(
        has_tests=True, branch_rules={"available": True, "types": ["required_status_checks"]}
    )
    rating, note, _ = s2.evaluate_q_2_7(ctx)
    assert rating == PARTIAL
    assert "ruleset: required_status_checks" in note


@pytest.mark.parametrize(
    "sentence",
    [
        "All pull requests must include tests.",
        "New features should come with unit tests.",
        "Tests are required for every change.",
        "Please add tests for your changes.",
        "PRs without tests will not be merged.",
        "Pull requests without tests will be rejected.",
        # A negated sentence earlier must not hide a real requirement later.
        "Docs changes do not need to include tests. Code changes must include tests.",
    ],
)
def test_tests_required_detected(sentence):
    assert s2.tests_required_in_text(sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        "Run the tests with make check.",
        "See tests/README.",
        # Negations / conditions found by review — these used to rate 2-7 as MEETS.
        "Documentation changes do not need to include tests.",
        "No tests are required for typo fixes.",
        "Contributions without tests are welcome too.",
        "PRs without tests will be accepted for docs.",
        "If you add tests for your feature, run make.",
    ],
)
def test_tests_required_ignores_mentions_negations_and_conditions(sentence):
    assert not s2.tests_required_in_text(sentence)


# --- 2-10: CODEOWNERS --------------------------------------------------------


def test_2_10_missing_codeowners_is_not_linked():
    rating, note, evidence = s2.evaluate_q_2_10(_ctx())
    assert rating == PARTIAL
    assert "CODEOWNERS nenalezen" in note
    assert "CODEOWNERS" not in evidence


def test_2_10_existing_codeowners_is_linked():
    url = "https://github.com/o/r/blob/HEAD/.github/CODEOWNERS"
    ctx = _ctx()
    ctx["urls"]["codeowners"] = url
    rating, note, evidence = s2.evaluate_q_2_10(ctx)
    assert note.startswith("CODEOWNERS nalezen")
    assert evidence.startswith(url)


# --- 1-1: forks --------------------------------------------------------------


def _s1_ctx(**repo):
    meta = {"html_url": "https://github.com/me/openssl", "default_branch": "master"}
    meta.update(repo)
    return {
        "repo_meta": meta,
        "org_meta": {"html_url": "https://github.com/me", "is_verified": True},
        "rel_latest": None,
        "tag_name": None,
        "sign_state": None,
    }


def test_1_1_fork_is_never_confirmed_even_with_verified_owner():
    ctx = _s1_ctx(
        fork=True,
        source={"full_name": "openssl/openssl", "html_url": "https://github.com/openssl/openssl"},
    )
    dukazy, rating, note = s1.evaluate_q_1_1("me", "openssl", ctx)
    assert rating == s1.RATING_PARTIAL
    assert "fork (openssl/openssl)" in note
    assert {"type": "fork_source", "url": "https://github.com/openssl/openssl"} in dukazy


def test_1_1_non_fork_verified_owner_still_meets():
    dukazy, rating, note = s1.evaluate_q_1_1("me", "openssl", _s1_ctx(fork=False))
    assert rating == s1.RATING_MEETS
    assert "fork" not in note
