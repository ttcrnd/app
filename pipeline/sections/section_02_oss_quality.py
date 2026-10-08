#!/usr/bin/env python3

import argparse
import datetime
import functools
import json
import os
import re
import sys
import time
from urllib.parse import quote

try:
    from pipeline.localization import text
except ModuleNotFoundError:  # pragma: no cover
    try:
        from localization import text
    except ModuleNotFoundError:  # pragma: no cover
        from scripts.localization import text  # type: ignore

from integrations.github import default_headers as _gh_default_headers
from integrations.github import get as _gh_get
from integrations.http import http_get as _http_get
from integrations.http import http_post_json as _http_post_json
from integrations.osv import osv_query_repo as _osv_query_repo
from integrations.scorecard import build_scorecard_map, fetch_scorecard, score_meets
from integrations import github as gh_api
from integrations.depsdev import (
    advisory_count,
    dependent_count,
    fetch_dependents,
    fetch_registry_downloads,
    fetch_version,
)
from integrations.openssf_badge import lookup_badge
from integrations.github_security import collect_github_security, security_features_note
from pipeline.security_md import parse_security_md
from pipeline.package_detect import detect_package, release_has_sigstore_assets
from pipeline.cmvp import search_cmvp
from pipeline.pr_sample import sample_merged_pr_stats

GITHUB_API = "https://api.github.com"
OSV_API = "https://api.osv.dev/v1/query"
NOW = datetime.datetime.now(datetime.timezone.utc)
ISO = "%Y-%m-%dT%H:%M:%SZ"
TARGET_REF = os.environ.get("REPO_REF", "").strip() or None

RATING_MEETS = text("common", "ratings", "meets")
RATING_PARTIAL = text("common", "ratings", "partial")
RATING_NOT_MET = text("common", "ratings", "not_met")
ERROR_FETCH_NOTE = text("common", "errors", "fetching")


def http_get(url: str, headers: dict = None, accept: str = "application/json"):
    base = {"Accept": accept, "User-Agent": "oss-open-source-eval/1.0"}
    if headers:
        base.update(headers)
    status, data, hdrs = _http_get(url, headers=base)
    ct = hdrs.get("Content-Type", "")
    return data, ct, hdrs


def http_post_json(url: str, payload: dict, headers: dict = None):
    status, data, hdrs = _http_post_json(url, payload, headers=headers)
    return data, hdrs


def gh_headers():
    return _gh_default_headers()


def gh_get(path, params=None):
    status, data, headers = _gh_get(path, params=params)
    return (data, headers)


def gh_repo(owner, repo):
    return gh_get(f"/repos/{owner}/{repo}")[0]


class GitHubApiError(RuntimeError):
    """A GitHub call failed (rate limit, auth, 5xx…) — the answer is unknown, not 'no'."""

    def __init__(self, path: str, status: int, data):
        message = data.get("message") if isinstance(data, dict) else None
        super().__init__(f"HTTP {status} na {path}" + (f" ({message})" if message else ""))
        self.status = status


def gh_latest_release(owner, repo):
    path = f"/repos/{owner}/{repo}/releases/latest"
    status, data, _ = _gh_get(path)
    if status == 404:
        return None  # repo has no published release
    if status != 200 or not isinstance(data, dict) or not data.get("tag_name"):
        raise GitHubApiError(path, status, data)
    return data


def gh_all_releases(owner, repo, limit=100):
    path = f"/repos/{owner}/{repo}/releases"
    status, data, _ = _gh_get(path, params={"per_page": min(100, limit)})
    if status != 200 or not isinstance(data, list):
        # Previously the error body (a 2-key dict) leaked through as the "list",
        # so len(...) >= 2 rated an API failure as "has releases".
        raise GitHubApiError(path, status, data)
    return data


def fetch_releases(owner, repo):
    """(releases, latest_release, error). Each call is independent, so a failing
    /releases/latest doesn't discard a successfully loaded list (and vice versa).
    `error` is set when either call failed — the caller must then not treat
    missing data as "no releases"."""
    errors = []
    releases, latest_rel = [], None
    try:
        releases = gh_all_releases(owner, repo, 100)
    except GitHubApiError as exc:
        errors.append(str(exc))
    try:
        latest_rel = gh_latest_release(owner, repo)
    except GitHubApiError as exc:
        errors.append(str(exc))
    return releases, latest_rel, ("; ".join(errors) or None)


def is_project_active(commits_last_year, releases_last_year):
    """2-1 heuristic. Only releases from the last 12 months count — an abandoned
    project with a few ancient releases must not look "active"."""
    return commits_last_year >= 12 or len(releases_last_year or []) >= 2


def _parse_gh_ts(value):
    if not value:
        return None
    try:
        return datetime.datetime.strptime(value, ISO).replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


def releases_within(releases, days=365):
    """Published (non-draft) releases from the last `days` days."""
    cutoff = NOW - datetime.timedelta(days=days)
    out = []
    for rel in releases or []:
        if not isinstance(rel, dict) or rel.get("draft"):
            continue
        published = _parse_gh_ts(rel.get("published_at"))
        if published and published >= cutoff:
            out.append(rel)
    return out


def gh_commits_since(owner, repo, since_days=365, branch=None, limit=3000):
    since = (NOW - datetime.timedelta(days=since_days)).strftime(ISO)
    params = {"since": since, "per_page": 100}
    if branch:
        params["sha"] = branch
    commits = []
    page = 1
    while True:
        params["page"] = page
        data, headers = gh_get(f"/repos/{owner}/{repo}/commits", params)
        if not data or not isinstance(data, list):
            break
        commits.extend(data)
        if len(data) < 100 or len(commits) >= limit:
            break
        page += 1
        time.sleep(0.3)
    return commits[:limit]


def gh_search_code(owner, repo, query, per_page=50):
    q = f"{query} repo:{owner}/{repo}"
    data, _ = gh_get("/search/code", {"q": q, "per_page": per_page})
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    return []


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
            # Fallbacks: for question evaluators return (not met, fetch-error note, ""),
            # for section-level aggregator return skeleton with all questions set to fallback.
            name = fn.__name__
            if name.startswith("evaluate_q_2_"):
                return (RATING_NOT_MET, ERROR_FETCH_NOTE, "")
            if name == "evaluate_open_source_section":
                skeleton_section = args[2] if len(args) >= 3 else kwargs.get("section")
                if skeleton_section is None:
                    return {}
                try:
                    sec = json.loads(json.dumps(skeleton_section))
                    for q in sec.get("questions", []) or []:
                        q["rating"] = RATING_NOT_MET
                        q["note"] = ERROR_FETCH_NOTE
                        q.setdefault("evidence", "")
                    return sec
                except Exception:
                    return skeleton_section
            return (RATING_NOT_MET, ERROR_FETCH_NOTE, "")

    return _wrap


def gh_repo_file_exists(owner, repo, path, ref=None):
    params = {"ref": ref} if ref else None
    data, _ = gh_get(f"/repos/{owner}/{repo}/contents/{path}", params=params)
    return isinstance(data, dict) and ("download_url" in data or "content" in data)


def gh_actions_exists(owner, repo):
    # `total_count >= 0` used to be true for any dict — including a 403/404
    # error body — so an API failure counted as "has CI".
    status, data, _ = _gh_get(f"/repos/{owner}/{repo}/actions/runs", params={"per_page": 1})
    if status == 200 and isinstance(data, dict) and int(data.get("total_count") or 0) > 0:
        return True
    items = gh_search_code(owner, repo, "path:.github/workflows")
    return len(items) > 0


def gh_issues_last_year(owner, repo, issue_state="all", limit=200):
    since = (NOW - datetime.timedelta(days=365)).strftime(ISO)
    issues = []
    page = 1
    while True:
        data, _ = gh_get(
            f"/repos/{owner}/{repo}/issues",
            {"state": issue_state, "since": since, "per_page": 100, "page": page},
        )
        if not isinstance(data, list) or not data:
            break
        for it in data:
            if "pull_request" not in it:
                issues.append(it)
        if len(data) < 100 or len(issues) >= limit:
            break
        page += 1
        time.sleep(0.3)
    return issues[:limit]


def gh_issue_comments(owner, repo, number):
    data, _ = gh_get(f"/repos/{owner}/{repo}/issues/{number}/comments", {"per_page": 100})
    return data if isinstance(data, list) else []


def gh_contributors(owner, repo, limit=200):
    data, _ = gh_get(f"/repos/{owner}/{repo}/contributors", {"per_page": min(100, limit)})
    return data or []


def osv_query_github_repo(owner, repo):
    resp = _osv_query_repo(f"https://github.com/{owner}/{repo}")
    return resp.get("vulns", []) or []


def is_pre_release_version(tag_name: str, name: str = ""):
    s = (tag_name or "") + " " + (name or "")
    return bool(re.search(r"\b(alpha|beta|rc|pre)\b", s, flags=re.IGNORECASE))


def pct(n, d):
    return 0 if d == 0 else (100.0 * n / d)


def first(obj, key, default=None):
    return (obj or {}).get(key, default)


def url_repo(owner, repo):
    return f"https://github.com/{owner}/{repo}"


def url_releases(owner, repo):
    return f"https://github.com/{owner}/{repo}/releases"


def url_issues(owner, repo):
    return f"https://github.com/{owner}/{repo}/issues"


def url_path(owner, repo, path):
    branch_or_ref = TARGET_REF or "HEAD"
    return f"https://github.com/{owner}/{repo}/blob/{branch_or_ref}/{path}"


def _estimate_core_maintainers(contributors: list) -> int:
    """Count contributors with meaningful share (not every User account)."""
    users = [c for c in contributors if isinstance(c, dict) and c.get("type") == "User"]
    if not users:
        return 0
    contributions = [int(c.get("contributions") or 0) for c in users]
    total = sum(contributions) or 1
    # Top contributors with >= 10% of commits among listed contributors
    significant = sum(1 for n in contributions if (n / total) >= 0.10)
    if significant >= 2:
        return significant
    # Fallback: at least two people with >= 5 contributions
    return sum(1 for n in contributions if n >= 5)


def _filter_osv_vulns(vulns: list) -> tuple[list, int]:
    """Keep medium+ signals; count severity hits. Never treat empty as clean MEETS."""
    sev_re = re.compile(r"(CRITICAL|HIGH|MEDIUM)", re.I)
    filtered = []
    sev_hits = 0
    cutoff = NOW - datetime.timedelta(days=60)
    for v in vulns or []:
        if not isinstance(v, dict):
            continue
        blob = json.dumps(v)
        if not sev_re.search(blob):
            continue
        published = v.get("published") or v.get("modified")
        too_old = True
        if published:
            try:
                dt = datetime.datetime.fromisoformat(str(published).replace("Z", "+00:00"))
                too_old = dt <= cutoff
            except Exception:
                too_old = True
        # Count as hit when medium+ and published > 60d ago (unresolved proxy)
        if too_old:
            sev_hits += 1
            filtered.append(v)
        else:
            filtered.append(v)
    return filtered, sev_hits


# CONTRIBUTING wording that makes tests a requirement for contributions (2-7).
_TESTS_REQUIRED_RE = re.compile(
    r"\b(must|should|needs? to|are required to|is required to)\s+"
    r"(include|add|have|contain|provide|come with|be accompanied by)\s+(\w+\s+){0,3}tests?\b"
    r"|\btests?\s+(are|is)\s+(required|mandatory)\b"
    r"|\b(include|add|write)\s+(\w+\s+){0,2}tests?\s+(for|covering)\s+(your|any|all|new|the)\b"
    # Double negative = requirement: "PRs without tests will not be merged / will be rejected".
    r"|\b(pull requests?|PRs?|patches|changes|contributions)\s+(without|lacking)\s+(\w+\s+)?tests?\s+"
    r"(?:(?:will|would|can|are|is)\s*(?:not|n't)\s+be\s+(?:merged|accepted)"
    r"|won't\s+be\s+(?:merged|accepted)"
    r"|(?:will|would)\s+be\s+(?:rejected|closed))",
    re.IGNORECASE,
)
# A match preceded by these (same sentence, close by) is a negation or condition:
# "do not need to include tests", "no tests are required", "if you add tests for…".
_TESTS_NEGATION_RE = re.compile(
    r"\b(not|no|never|don't|doesn't|isn't|aren't|if|unless)\b|n't\b", re.I
)


def tests_required_in_text(text: str | None) -> bool:
    """True when some sentence states tests are *required* (negations/conditions skipped)."""
    if not text:
        return False
    for m in _TESTS_REQUIRED_RE.finditer(text):
        window = text[max(0, m.start() - 40) : m.start()]
        window = re.split(r"[.!?\n]", window)[-1]  # only the current sentence
        if not _TESTS_NEGATION_RE.search(window):
            return True
    return False


def _read_repo_text(owner: str, repo: str, path: str, ref: str | None) -> str | None:
    import base64

    meta = gh_api.get_file(owner, repo, path, ref=ref)
    if not meta:
        return None
    content = meta.get("content")
    if isinstance(content, str):
        try:
            return base64.b64decode(content).decode("utf-8", errors="replace")
        except Exception:
            return None
    download = meta.get("download_url")
    if download:
        status, data, _ = _http_get(download, headers={"User-Agent": "oss-open-source-eval/1.0"})
        if status == 200 and data:
            return data.decode("utf-8", errors="replace")
    return None


def _harvest_audit_urls(*texts: str) -> list[str]:
    urls = []
    cre = re.compile(r"https?://[^\s)\"']+", re.I)
    mention = re.compile(
        r"\baudit\b|cure53|trail of bits|ncc group|ostif|quarkslab|least authority|include security",
        re.I,
    )
    allow_hosts = (
        "audit",
        "cure53",
        "trailofbits",
        "nccgroup",
        "ncc.",
        "ostif",
        "quarkslab",
        "leastauthority",
        "include security",
        "pdf",
    )
    # Well-known public audit citations for major crypto libraries (evidence prefill).
    known = {
        "openssl": [
            "https://www.openssl.org/news/vulnerabilities.html",
            "https://ostif.org/",
        ],
    }
    for body in texts:
        if not body:
            continue
        if mention.search(body):
            for u in cre.findall(body):
                low = u.lower()
                if any(k in low for k in allow_hosts):
                    urls.append(u.rstrip(".,;"))
    blob = "\n".join(t for t in texts if t).lower()
    for key, preset in known.items():
        if key in blob:
            urls.extend(preset)
    # unique preserve order
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _detect_coverage_signal(readme: str, scorecard_map: dict) -> bool:
    blob = (readme or "").lower()
    if any(k in blob for k in ("codecov", "coveralls", "coverage", "jacoco", "lcov")):
        return True
    # Scorecard CI-Tests alone is not coverage
    return False


@_eval_log
def evaluate_q_2_1(ctx):
    """
    Question 2-1: "Project is active and stable."
    Collects commit count over the last 12 months and the number of releases.
    Heuristic: active if commits >= 12 or releases >= 2. Returns (rating, note, evidence URLs).
    """
    recent = ctx.get("releases_last_year", ctx["releases"])
    note = text(
        "script2",
        "evaluate_q_2_1",
        "note",
        commits=ctx["commits_cnt"],
        releases=len(recent),
    )
    return (
        (RATING_MEETS if ctx["project_active"] else RATING_PARTIAL),
        note + _releases_unknown_note(ctx),
        f"{ctx['urls']['repo']}\n{ctx['urls']['releases']}",
    )


def _releases_unknown_note(ctx) -> str:
    err = ctx.get("releases_error")
    if not err:
        return ""
    return f" Release nelze ověřit — chyba GitHub API ({err}); nejde o „nesplňuje“, ověřte ručně."


@_eval_log
def evaluate_q_2_1a(ctx):
    """
    2-1a: "Latest public release ≤ 1 year (not a prerelease)" - evaluates release date and prerelease flag.
    """
    note = text(
        "script2",
        "evaluate_q_2_1a",
        "note",
        release_name=ctx["last_rel_name"] or "nenalezen",
        release_date=ctx["last_rel_date_str"],
        is_prerelease=ctx["last_rel_is_prerelease"],
    )
    if ctx.get("releases_error"):
        return RATING_PARTIAL, note + _releases_unknown_note(ctx), ctx["urls"]["releases"]
    meets = (
        RATING_MEETS
        if ctx["last_release_ok"]
        else (RATING_PARTIAL if ctx["latest_rel"] else RATING_NOT_MET)
    )
    return meets, note, ctx["urls"]["releases"]


@_eval_log
def evaluate_q_2_1b(ctx):
    """2-1b: Any activity within the year (commit/issue/release from the last 12 months)."""
    recent = ctx.get("releases_last_year", ctx["releases"])
    any_activity = ctx["commits_cnt"] > 0 or ctx["issues_count"] > 0 or len(recent) > 0
    note = text(
        "script2",
        "evaluate_q_2_1b",
        "note",
        commits=ctx["commits_cnt"],
        issues=ctx["issues_count"],
        releases=len(recent),
    )
    if any_activity:
        rating = RATING_MEETS
    elif ctx.get("releases_error"):
        rating = RATING_PARTIAL  # releases unknown — can't claim "no activity"
    else:
        rating = RATING_NOT_MET
    return rating, note + _releases_unknown_note(ctx), ctx["urls"]["repo"]


@_eval_log
def evaluate_q_2_1c(ctx):
    """2-1c: Maintainer responses ≥ 50% (heuristic from issues and comments)."""
    meets = (
        RATING_MEETS
        if ctx["maint_res_ok"]
        else (RATING_PARTIAL if ctx["issues_count"] > 0 else RATING_NOT_MET)
    )
    sample_n = int(ctx.get("maint_sample_size") or ctx["issues_count"] or 0)
    note = text(
        "script2",
        "evaluate_q_2_1c",
        "note",
        responses=ctx["issues_with_maintainer_response"],
        issues=sample_n,
        percentage=ctx["maint_response_pct"],
    )
    if sample_n and sample_n != ctx["issues_count"]:
        note = f"{note} (vzorek {sample_n} z {ctx['issues_count']} issues)"
    return meets, note, ctx["urls"]["issues"]


@_eval_log
def evaluate_q_2_1d(ctx):
    """2-1d: Latest release is not marked as a prerelease (tag/name)."""
    note = text(
        "script2",
        "evaluate_q_2_1d",
        "note",
        release_name=ctx["last_rel_name"] or "n/a",
    )
    if ctx.get("releases_error"):
        return RATING_PARTIAL, note + _releases_unknown_note(ctx), ctx["urls"]["releases"]
    meets = (
        RATING_MEETS if ctx["latest_rel"] and not ctx["last_rel_is_prerelease"] else RATING_PARTIAL
    )
    return meets, note, ctx["urls"]["releases"]


@_eval_log
def evaluate_q_2_2(ctx):
    """2-2: README purpose — existence alone is not MEETS (E2)."""
    has_readme = ctx["has_readme"]
    return (
        (RATING_PARTIAL if has_readme else RATING_NOT_MET),
        text(
            "script2",
            "evaluate_q_2_2",
            "note_exists" if has_readme else "note_missing",
        ),
        ctx["urls"]["readme"],
    )



@_eval_log
def evaluate_q_2_3(ctx):
    """2-3: Bug reporting and contribution process - SECURITY.md / CONTRIBUTING.md."""
    has_contributing = ctx["has_contributing"]
    has_security = ctx["has_security"]
    policy = ctx.get("security_policy") or {}
    policy_signal = bool(policy.get("has_policy_signal") or has_security)
    gh_sec = ctx.get("github_security") or {}
    if has_contributing and policy_signal:
        meets = RATING_MEETS
    elif has_contributing or policy_signal:
        meets = RATING_PARTIAL
    else:
        meets = RATING_PARTIAL
    note = text(
        "script2",
        "evaluate_q_2_3",
        "note",
        has_contributing=has_contributing,
        has_security=policy_signal,
    )
    if policy.get("notes"):
        note = f"{note} Policy signály: {'; '.join(list(policy.get('notes') or [])[:2])}."
    badge_note = ctx.get("badge_note") or ""
    badge = ctx.get("badge") or {}
    if badge_note:
        note = f"{note} {badge_note}"
    sec_note = security_features_note(gh_sec)
    if gh_sec.get("private_reporting") is True:
        note = f"{note} {sec_note}"
    elif sec_note and "Private" in sec_note:
        note = f"{note} {sec_note}"
    proofs = "\n".join(
        filter(
            None,
            [
                ctx["urls"]["contributing"] if has_contributing else "",
                ctx["urls"]["security"] if has_security else "",
                *((policy.get("policy_urls") or [])[:3]),
                badge.get("url") or "",
                *((gh_sec.get("urls") or [])[:1]),
            ],
        )
    )
    return meets, note, proofs or ctx["urls"]["repo"]


@_eval_log
def evaluate_q_2_4(ctx):
    """2-4: Vulnerability response — SECURITY.md content signals (E10)."""
    has_security = ctx["has_security"]
    policy = ctx.get("security_policy") or {}
    sec = ctx.get("security_parse") or {}
    process_like = bool(sec.get("process_like"))
    gh_sec = ctx.get("github_security") or {}
    policy_signal = bool(policy.get("has_policy_signal"))
    if has_security and process_like:
        meets = RATING_MEETS
        note = text("script2", "evaluate_q_2_4", "note_with_security") + " Procesní signály v SECURITY.md."
    elif has_security or policy_signal:
        meets = RATING_PARTIAL
        note = text("script2", "evaluate_q_2_4", "note_with_security")
        if policy_signal and not has_security:
            note = f"{note} Bez SECURITY.md souboru — použit community/known policy URL."
    else:
        meets = RATING_PARTIAL
        note = text("script2", "evaluate_q_2_4", "note_without_security")
    if gh_sec.get("private_reporting") is True:
        note = f"{note} Private vulnerability reporting zapnuto."
        meets = RATING_MEETS if (has_security or policy_signal) else meets
    if isinstance(gh_sec.get("advisories_count"), int) and gh_sec["advisories_count"] > 0:
        note = f"{note} Published GHSA: {gh_sec['advisories_count']}."
        if meets == RATING_PARTIAL and policy_signal:
            meets = RATING_MEETS
    evidence = ctx["urls"]["security"] if has_security else ctx["urls"]["releases"]
    extra = "\n".join(
        list((policy.get("policy_urls") or [])[:3]) + list((gh_sec.get("urls") or [])[:2])
    )
    if extra:
        evidence = f"{evidence}\n{extra}"
    return meets, note, evidence



@_eval_log
def evaluate_q_2_5(ctx):
    """2-5: Auditable history - conservatively 'partial' with repository and release links."""
    return (
        RATING_PARTIAL,
        text("script2", "evaluate_q_2_5", "note"),
        f"{ctx['urls']['repo']}\n{ctx['urls']['releases']}",
    )


@_eval_log
def evaluate_q_2_6(ctx):
    """2-6: Unresolved medium+ vulns >60d — filtered OSV (+ optional deps.dev)."""
    filtered = ctx.get("vulns_filtered")
    if filtered is None:
        filtered = ctx.get("open_or_recent_vulns") or []
    sev_hits = int(ctx.get("sev_hits") or 0)
    deps_note = ctx.get("depsdev_note") or ""
    gh_sec = ctx.get("github_security") or {}
    note = text(
        "script2",
        "evaluate_q_2_6",
        "note",
        vulns_count=len(filtered),
    )
    if deps_note:
        note = f"{note} {deps_note}"
    dep_open = gh_sec.get("dependabot_open")
    if isinstance(dep_open, int):
        note = f"{note} Open Dependabot alerts={dep_open}."
        if dep_open > 0:
            sev_hits = max(sev_hits, dep_open)
    if isinstance(gh_sec.get("advisories_count"), int) and gh_sec["advisories_count"] > 0:
        note = f"{note} Published GH advisories={gh_sec['advisories_count']}."
    # 0 open alerts never implies MEETS — only PARTIAL / NOT_MET.
    if sev_hits == 0:
        rating = RATING_PARTIAL
    else:
        rating = RATING_NOT_MET
    evidence = ctx.get("osv_evidence") or ctx["urls"]["repo"]
    extra = "\n".join((gh_sec.get("urls") or [])[:2])
    if extra:
        evidence = f"{evidence}\n{extra}"
    return rating, note, evidence



@_eval_log
def evaluate_q_2_7(ctx):
    """2-7: Test suite exists AND tests are required for new contributions.

    The criterion has two halves; test presence alone used to rate MEETS.
    Now MEETS needs both: tests run on PRs before merge (Scorecard CI-Tests,
    required status checks via branch protection or rulesets) and an explicit
    requirement for tests in the contribution guide.
    """
    has_tests = bool(ctx["has_tests"])
    sc_map = ctx.get("scorecard_map") or {}
    ci_tests = (sc_map.get("checks") or {}).get("CI-Tests")
    bp = ctx.get("branch_protection") or {}
    status_checks = bp.get("required_status_checks")
    rule_types = (ctx.get("branch_rules") or {}).get("types") or []

    pr_check_sources = []
    if score_meets(ci_tests, 7):
        pr_check_sources.append(f"Scorecard CI-Tests={ci_tests}")
    if isinstance(status_checks, list) and status_checks:
        pr_check_sources.append(f"branch protection: {len(status_checks)} povinných status checks")
    if "required_status_checks" in rule_types:
        pr_check_sources.append("ruleset: required_status_checks")
    tests_run_on_prs = bool(pr_check_sources)
    tests_required = bool(ctx.get("tests_required_in_contributing"))

    note = (
        f"Testy v repu: {'ano' if has_tests else 'nenalezeny'}. "
        f"Testy povinně běží u PR před mergem: "
        f"{'ano (' + ', '.join(pr_check_sources) + ')' if tests_run_on_prs else 'neověřeno'}. "
        f"Požadavek na testy u nových příspěvků: "
        f"{'ano (CONTRIBUTING)' if tests_required else 'nenalezen v CONTRIBUTING'}."
    )
    if has_tests and tests_run_on_prs and tests_required:
        rating = RATING_MEETS
    else:
        rating = RATING_PARTIAL
        if has_tests:
            note += " Existence testů nestačí — vynucení u PR ověřte ručně."

    evidence = [ctx["urls"]["tests"] if has_tests else ctx["urls"]["repo"]]
    if ctx.get("contributing_url"):
        evidence.append(ctx["contributing_url"])
    if sc_map.get("urls", {}).get("CI-Tests"):
        evidence.append(sc_map["urls"]["CI-Tests"])
    return rating, note, "\n".join(evidence)


@_eval_log
def evaluate_q_2_8(ctx):
    """2-8: Release notes plus CVE mentions in the latest release."""
    gh_sec = ctx.get("github_security") or {}
    note = text(
        "script2",
        "evaluate_q_2_8",
        "note",
        has_release_notes=ctx["has_release_notes"],
        has_cve=ctx["cve_in_last_release"],
    )
    if isinstance(gh_sec.get("advisories_count"), int):
        note = f"{note} GH security advisories published={gh_sec['advisories_count']}."
    evidence = ctx["urls"]["releases"]
    extra = "\n".join((gh_sec.get("urls") or [])[:1])
    if extra:
        evidence = f"{evidence}\n{extra}"
    return (
        (RATING_MEETS if ctx["has_release_notes"] else RATING_PARTIAL),
        note,
        evidence,
    )


@_eval_log
def evaluate_q_2_9(ctx):
    """2-9: Mandatory code review — branch protection, Scorecard, PR sample."""
    bp = ctx.get("branch_protection") or {}
    sc_map = ctx.get("scorecard_map") or {}
    checks = sc_map.get("checks") or {}
    pr = ctx.get("pr_stats") or {}
    urls = []
    cr = checks.get("Code-Review")
    bps = checks.get("Branch-Protection")
    req = bp.get("required_approving_review_count")
    status_checks = bp.get("required_status_checks")
    approval_rate = float(pr.get("approval_rate") or 0)
    self_merge_rate = float(pr.get("self_merge_rate") or 0)
    self_merge_heavy = pr.get("available") and pr.get("sampled", 0) >= 5 and self_merge_rate > 0.5

    if self_merge_heavy:
        rating = RATING_PARTIAL
        note = (
            f"PR sample n={pr.get('sampled')}: self-merge {self_merge_rate:.0%} "
            f"(>50 %) — ne MEETS; non-author approval {approval_rate:.0%}."
        )
        urls.extend(pr.get("urls") or [])
    elif bp.get("available") and isinstance(req, int) and req >= 1 and status_checks is not None:
        rating = RATING_MEETS
        note = (
            f"Branch protection: required_reviews={req}, "
            f"status_checks={len(status_checks) if isinstance(status_checks, list) else status_checks}."
        )
        urls.append(f"{ctx['urls']['repo']}/settings/branches")
    elif pr.get("available") and pr.get("sampled", 0) >= 5 and approval_rate >= 0.7 and self_merge_rate <= 0.3:
        rating = RATING_MEETS
        note = (
            f"PR sample n={pr.get('sampled')}: non-author approval "
            f"{approval_rate:.0%}, self-merge {self_merge_rate:.0%}."
        )
        urls.extend(pr.get("urls") or [])
    elif score_meets(cr, 7) or (score_meets(bps, 5) and score_meets(cr, 5)):
        rating = RATING_MEETS
        note = f"Scorecard Code-Review={cr}, Branch-Protection={bps} (vyžaduje potvrzení)."
        if sc_map.get("urls", {}).get("Code-Review"):
            urls.append(sc_map["urls"]["Code-Review"])
    elif score_meets(cr, 3) or score_meets(bps, 3) or bp.get("available") or pr.get("available"):
        rating = RATING_PARTIAL
        note = (
            f"Částečné signály review (Code-Review={cr}, Branch-Protection={bps}, "
            f"PR approval_rate={approval_rate:.0%})."
        )
        urls.extend(pr.get("urls") or [])
    else:
        rating = RATING_PARTIAL
        note = text("script2", "evaluate_q_2_9", "note")
    urls.append(ctx["urls"]["workflows"])
    return rating, note, "\n".join(u for u in urls if u)



@_eval_log
def evaluate_q_2_10(ctx):
    """2-10: Thorough review by core maintainers — CODEOWNERS + PR sample."""
    pr = ctx.get("pr_stats") or {}
    codeowners_url = ctx["urls"].get("codeowners")
    if codeowners_url:
        note = "CODEOWNERS nalezen. " + text("script2", "evaluate_q_2_10", "note")
        evidence = codeowners_url
    else:
        # Used to link a CODEOWNERS URL without checking it exists (→ 404 evidence).
        note = (
            "CODEOWNERS nenalezen nebo nedostupný (CODEOWNERS, .github/, docs/). "
            "Úzký tým revidentů z veřejných dat nelze doložit."
        )
        evidence = ctx["urls"]["repo"]
    if pr.get("available") and pr.get("sampled", 0) >= 5:
        note = (
            f"{note} PR sample: median_reviewers={pr.get('median_reviewers')}, "
            f"approval_rate={float(pr.get('approval_rate') or 0):.0%}."
        )
        urls = pr.get("urls") or []
        if urls:
            evidence = f"{evidence}\n" + "\n".join(urls[:3])
    return RATING_PARTIAL, note, evidence


@_eval_log
def evaluate_q_2_11(ctx):
    """2-11: Dedicated security maintainer — SECURITY.md role signals."""
    has_security = ctx["has_security"]
    policy = ctx.get("security_policy") or {}
    policy_signal = bool(policy.get("has_policy_signal"))
    sec = ctx.get("security_parse") or {}
    signals = (sec.get("signals") or {})
    evidence = ctx["urls"]["security"]
    if policy.get("policy_urls"):
        evidence = "\n".join([evidence] + list(policy["policy_urls"][:2]))
    if signals.get("has_security_team"):
        return (
            RATING_PARTIAL,
            text("script2", "evaluate_q_2_11", "note") + " Zmíněn security team.",
            evidence,
        )
    if has_security or policy_signal:
        return (
            RATING_PARTIAL,
            text("script2", "evaluate_q_2_11", "note")
            + (" Security policy URL/community profile nalezen." if policy_signal else ""),
            evidence,
        )
    return (
        RATING_NOT_MET,
        text("script2", "evaluate_q_2_11", "note"),
        ctx["urls"]["repo"],
    )



@_eval_log
def evaluate_q_2_12(ctx):
    """2-12: >=2 maintainers — top committers share, not all User contributors."""
    core = int(ctx.get("core_maintainers") or 0)
    contributors = ctx.get("contributors") or []
    return (
        (RATING_MEETS if core >= 2 else RATING_NOT_MET),
        text(
            "script2",
            "evaluate_q_2_12",
            "note",
            contributors_count=len(contributors),
            has_core=core >= 2,
        ),
        f"{ctx['urls']['repo']}/graphs/contributors",
    )



@_eval_log
def evaluate_q_2_13(ctx):
    """2-13: Max two approvers — signal from protection only."""
    bp = ctx.get("branch_protection") or {}
    req = bp.get("required_approving_review_count")
    note = text("script2", "evaluate_q_2_13", "note")
    if isinstance(req, int) and req in (1, 2):
        note = f"{note} required_approving_review_count={req}."
    return RATING_PARTIAL, note, ctx["urls"]["repo"]



@_eval_log
def evaluate_q_2_14(ctx):
    """2-14: Full-time developer sponsorship - indicated by FUNDING.yml."""
    has_funding = ctx["has_funding"]
    return (
        (RATING_PARTIAL if has_funding else RATING_NOT_MET),
        text("script2", "evaluate_q_2_14", "note"),
        (ctx["urls"]["funding"] if has_funding else ctx["urls"]["repo"]),
    )


@_eval_log
def evaluate_q_2_15(ctx):
    """2-15: Widely adopted — downloads/dependents preferred over stars."""
    stargazers = ctx["stargazers"]
    forks = ctx["forks"]
    watchers = ctx["watchers"]
    dependents = ctx.get("dependents_count")
    downloads = ctx.get("downloads_count")
    downloads_meta = ctx.get("downloads_meta") or {}
    metric = "stars/forks fallback"
    if isinstance(dependents, int) and dependents >= 50:
        rating = RATING_MEETS
        metric = f"deps.dev dependents={dependents}"
    elif isinstance(downloads, int) and downloads >= 10000:
        rating = RATING_MEETS
        src = downloads_meta.get("source") or "registry"
        metric = f"{src} downloads={downloads}"
    elif stargazers >= 1000 or forks >= 200:
        rating = RATING_MEETS
        metric = "stars/forks fallback"
    else:
        rating = RATING_PARTIAL
    note = text(
        "script2",
        "evaluate_q_2_15",
        "note",
        stars=stargazers,
        forks=forks,
        watchers=watchers,
    )
    note = f"{note} Metrika: {metric}."
    evidence = downloads_meta.get("url") or ctx.get("depsdev_url") or ctx["urls"]["repo"]
    return rating, note, evidence



@_eval_log
def evaluate_q_2_16(ctx):
    """2-16: CI + coverage — Actions alone is not MEETS (E2)."""
    has_actions = ctx["has_actions"]
    sc_map = ctx.get("scorecard_map") or {}
    ci_score = (sc_map.get("checks") or {}).get("CI-Tests")
    has_coverage = bool(ctx.get("has_coverage_signal"))
    if has_actions and has_coverage:
        rating = RATING_MEETS
    elif has_actions and score_meets(ci_score, 7) and has_coverage:
        rating = RATING_MEETS
    elif has_actions or score_meets(ci_score, 5):
        rating = RATING_PARTIAL
    else:
        rating = RATING_PARTIAL
    note = text("script2", "evaluate_q_2_16", "note", has_actions=has_actions)
    note = f"{note} coverage_signal={has_coverage}; CI-Tests={ci_score}."
    evidence = ctx["urls"]["workflows"]
    cov_url = (sc_map.get("urls") or {}).get("CI-Tests")
    if cov_url:
        evidence = f"{evidence}\n{cov_url}"
    return rating, note, evidence



@_eval_log
def evaluate_q_2_17(ctx):
    """2-17: Dependency freshness — Dependabot/Renovate/Scorecard/lockfile/SBOM."""
    has_deps_bot = bool(ctx.get("has_dependabot") or ctx.get("has_renovate"))
    sc_map = ctx.get("scorecard_map") or {}
    checks = sc_map.get("checks") or {}
    dep_score = checks.get("Dependency-Update-Tool")
    pinned_score = checks.get("Pinned-Dependencies")
    pinned = bool(ctx.get("has_lockfile"))
    has_sbom = bool(ctx.get("has_sbom"))
    lock_urls = list(ctx.get("lockfile_urls") or [])
    sbom_urls = list(ctx.get("sbom_urls") or [])
    urls = [ctx["urls"]["releases"]]
    if ctx.get("dependabot_url"):
        urls.insert(0, ctx["dependabot_url"])
    if ctx.get("renovate_url"):
        urls.insert(0, ctx["renovate_url"])
    urls.extend(lock_urls[:3])
    urls.extend(sbom_urls[:2])
    pinned_url = (sc_map.get("urls") or {}).get("Pinned-Dependencies")
    if pinned_url:
        urls.append(pinned_url)
    if has_deps_bot and (pinned or has_sbom or score_meets(pinned_score, 7)):
        rating = RATING_MEETS
        note = "Dependabot/Renovate + lockfile/SBOM/Pinned signály (vyžaduje potvrzení)."
        note = (
            f"{note} Dependency-Update-Tool={dep_score}; "
            f"Pinned-Dependencies={pinned_score}; lockfile={pinned}; sbom={has_sbom}."
        )
    elif has_deps_bot or score_meets(dep_score, 5) or score_meets(pinned_score, 5) or pinned or has_sbom:
        rating = RATING_PARTIAL
        note = (
            "Nalezen Dependabot/Renovate config (vyžaduje potvrzení)."
            if has_deps_bot
            else text("script2", "evaluate_q_2_17", "note")
        )
        note = (
            f"{note} Dependency-Update-Tool={dep_score}; "
            f"Pinned-Dependencies={pinned_score}; lockfile={pinned}; sbom={has_sbom}."
        )
    else:
        rating = RATING_PARTIAL
        note = text("script2", "evaluate_q_2_17", "note")
    gh_sec = ctx.get("github_security") or {}
    if isinstance(gh_sec.get("dependabot_open"), int):
        note = f"{note} Open Dependabot alerts={gh_sec['dependabot_open']} (0 ≠ MEETS)."
    return rating, note, "\n".join(dict.fromkeys(u for u in urls if u))



@_eval_log
def evaluate_q_2_18(ctx):
    """2-18: Assurance case - outside automation scope; provide repository/documentation links."""
    return (
        RATING_PARTIAL,
        text("script2", "evaluate_q_2_18", "note"),
        ctx["urls"]["repo"],
    )


@_eval_log
def evaluate_q_2_19(ctx):
    """2-19: FLOSS license declared - based on GitHub API."""
    has_license = ctx["has_license"]
    return (
        (RATING_MEETS if has_license else RATING_PARTIAL),
        text("script2", "evaluate_q_2_19", "note", license_id=ctx["license_id"]),
        ctx["urls"]["license"],
    )


@_eval_log
def evaluate_q_2_20(ctx):
    """2-20: Third-party audit — harvest URLs only."""
    audit_urls = ctx.get("audit_urls") or []
    note = text("script2", "evaluate_q_2_20", "note")
    if audit_urls:
        note = f"{note} Nalezené odkazy/zmínky: {len(audit_urls)}."
        evidence = "\n".join(audit_urls[:8] + [ctx["urls"]["repo"]])
    else:
        evidence = ctx["urls"]["repo"]
    return RATING_PARTIAL, note, evidence



@_eval_log
def evaluate_q_2_21(ctx):
    """2-21: Willingness to consult - proxied via issue activity."""
    return (
        RATING_PARTIAL,
        text("script2", "evaluate_q_2_21", "note"),
        ctx["urls"]["issues"],
    )


@_eval_log
def evaluate_q_2_22(ctx):
    """2-22: FIPS — CMVP search prefill (always CONFIRM)."""
    cmvp = ctx.get("cmvp") or {}
    note = text("script2", "evaluate_q_2_22", "note")
    if cmvp.get("note"):
        note = f"{note} {cmvp['note']}"
    evidence = cmvp.get("search_url") or (
        "https://csrc.nist.gov/projects/cryptographic-module-validation-program/validated-modules/search"
    )
    rating = RATING_PARTIAL
    # OpenSSL / FIPS provider claim → stronger partial with CMVP search evidence.
    if not ctx.get("no_fips_claim"):
        note = f"{note} Docs obsahují FIPS claim — ověř CMVP modul/verzi."
        if cmvp.get("possible_hit") or cmvp.get("search_url"):
            rating = RATING_PARTIAL
    else:
        note = (
            f"{note} V docs/README nebyl nalezen FIPS claim — pokud se FIPS netýká, "
            "nech Nehodnoceno a vysvětli v poznámce."
        )
    return rating, note, evidence


@_eval_log
def evaluate_open_source_section(owner, repo, skeleton_section):
    def progress(msg: str) -> None:
        print(f"[INFO] [2.py] {msg}", flush=True)

    progress("Načítám metadata repozitáře a release…")
    repo_info = gh_repo(owner, repo) or {}
    default_branch = repo_info.get("default_branch", "master")
    effective_ref = TARGET_REF or default_branch
    releases, latest_rel, releases_error = fetch_releases(owner, repo)
    if releases_error:
        progress(f"[WARN] Release se nepodařilo načíst: {releases_error}")
    releases_last_year = releases_within(releases, 365)

    progress(f"Stahuji commity za 12 měsíců (ref={effective_ref})…")
    commits_365 = gh_commits_since(owner, repo, 365, branch=effective_ref, limit=3000)
    commits_cnt = len(commits_365)
    progress(f"Committů za rok: {commits_cnt}")
    last_release_date = None
    if latest_rel and latest_rel.get("published_at"):
        last_release_date = datetime.datetime.strptime(latest_rel["published_at"], ISO).replace(
            tzinfo=datetime.timezone.utc
        )

    progress("Stahuji issues za 12 měsíců…")
    issues = gh_issues_last_year(owner, repo, "all", limit=400)
    issues_count = len(issues)
    # Cap comment fan-out — one GitHub call per issue is the slow path on busy repos.
    comment_sample = issues[:80]
    progress(
        f"Issues: {issues_count}; kontroluji maintainer odpovědi u vzorku {len(comment_sample)}…"
    )
    issues_with_maintainer_response = 0
    for idx, it in enumerate(comment_sample, start=1):
        assoc = (it.get("author_association") or "").upper()
        if assoc in ("MEMBER", "OWNER", "COLLABORATOR"):
            issues_with_maintainer_response += 1
        elif int(it.get("comments") or 0) > 0:
            comments = gh_issue_comments(owner, repo, it["number"])
            for c in comments:
                ua = (c.get("author_association") or "").upper()
                if ua in ("MEMBER", "OWNER", "COLLABORATOR"):
                    issues_with_maintainer_response += 1
                    break
            time.sleep(0.05)
        if idx == 1 or idx % 20 == 0 or idx == len(comment_sample):
            progress(f"Maintainer odpovědi: {idx}/{len(comment_sample)} issues…")

    progress("Kontroluji SECURITY / CONTRIBUTING / CoC / Actions / testy…")
    from pipeline.repo_signals import detect_security_policy, detect_test_roots

    security_policy = detect_security_policy(owner, repo, ref=effective_ref)
    has_security = bool(
        security_policy.get("has_security_md")
        or any(
            [
                gh_repo_file_exists(owner, repo, "SECURITY.md", ref=effective_ref),
                gh_repo_file_exists(owner, repo, ".github/SECURITY.md", ref=effective_ref),
            ]
        )
    )
    has_contributing = any(
        [
            gh_repo_file_exists(owner, repo, "CONTRIBUTING.md", ref=effective_ref),
            gh_repo_file_exists(owner, repo, ".github/CONTRIBUTING.md", ref=effective_ref),
            gh_repo_file_exists(owner, repo, "docs/CONTRIBUTING.md", ref=effective_ref),
        ]
    )
    has_coc = any(
        [
            gh_repo_file_exists(owner, repo, "CODE_OF_CONDUCT.md", ref=effective_ref),
            gh_repo_file_exists(owner, repo, ".github/CODE_OF_CONDUCT.md", ref=effective_ref),
        ]
    )

    has_actions = gh_actions_exists(owner, repo)
    test_roots = detect_test_roots(owner, repo, ref=effective_ref)
    test_hits = gh_search_code(owner, repo, "path:tests OR path:test OR filename:test")
    has_tests = bool(test_roots.get("has_tests") or test_hits)

    _rel_notes_url = url_releases(owner, repo)
    last_rel_is_prerelease = False
    if latest_rel:
        last_rel_is_prerelease = bool(latest_rel.get("prerelease"))
    last_rel_name = first(latest_rel, "name", "") or first(latest_rel, "tag_name", "")
    has_release_notes = bool(latest_rel and (latest_rel.get("body") or "").strip())
    cve_in_last_release = bool(
        re.search(r"\bCVE-\d{4}-\d+\b", (latest_rel or {}).get("body", ""), flags=re.IGNORECASE)
    )

    progress("Dotazuji OSV.dev…")
    vulns = osv_query_github_repo(owner, repo)
    vulns_filtered, sev_hits_pre = _filter_osv_vulns(vulns)
    open_or_recent_vulns = vulns_filtered
    osv_evidence = f"OSV.dev query: repo=https://github.com/{owner}/{repo}"

    stargazers = repo_info.get("stargazers_count", 0)
    forks = repo_info.get("forks_count", 0)
    watchers = repo_info.get("subscribers_count", 0)
    has_funding = gh_repo_file_exists(owner, repo, ".github/FUNDING.yml", ref=effective_ref) or (
        gh_repo_file_exists(owner, repo, "FUNDING.yml", ref=effective_ref)
    )
    contributors = gh_contributors(owner, repo, 200)
    core_maintainers = _estimate_core_maintainers(contributors)

    # Scorecard (E1) — once per section
    progress("Načítám OpenSSF Scorecard…")
    scorecard_raw = fetch_scorecard(owner, repo)
    scorecard_map = build_scorecard_map(scorecard_raw)

    # Branch protection (E3)
    bp_raw = gh_api.get_branch_protection(owner, repo, default_branch)
    branch_protection = gh_api.normalize_branch_protection(bp_raw)
    branch_rules = gh_api.get_branch_rule_types(owner, repo, default_branch)

    # 2-7: does the project *require* tests on contributions? (not just "has tests")
    contributing_text, contributing_url = None, None
    for cpath in ("CONTRIBUTING.md", ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md"):
        contributing_text = _read_repo_text(owner, repo, cpath, effective_ref)
        if contributing_text:
            contributing_url = url_path(owner, repo, cpath)
            break
    tests_required_in_contributing = tests_required_in_text(contributing_text)

    # 2-10: GitHub honours CODEOWNERS in exactly these three locations.
    codeowners_url = None
    for cpath in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"):
        if gh_repo_file_exists(owner, repo, cpath, ref=effective_ref):
            codeowners_url = url_path(owner, repo, cpath)
            break

    # Dependabot / Renovate / lockfiles (E4 / E11)
    progress("Kontroluji Dependabot/Renovate, lockfile a SBOM…")
    dep_paths = [
        (".github/dependabot.yml", "dependabot"),
        (".github/dependabot.yaml", "dependabot"),
        ("dependabot.yml", "dependabot"),
        ("renovate.json", "renovate"),
        (".github/renovate.json", "renovate"),
        ("renovate.json5", "renovate"),
    ]
    has_dependabot = False
    has_renovate = False
    dependabot_url = None
    renovate_url = None
    for pth, kind in dep_paths:
        if gh_repo_file_exists(owner, repo, pth, ref=effective_ref):
            if kind == "dependabot":
                has_dependabot = True
                dependabot_url = url_path(owner, repo, pth)
            else:
                has_renovate = True
                renovate_url = url_path(owner, repo, pth)
    lock_paths = [
        "Cargo.lock",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "go.sum",
        "poetry.lock",
        "Pipfile.lock",
        "composer.lock",
    ]
    lockfile_urls = []
    for p in lock_paths:
        if gh_repo_file_exists(owner, repo, p, ref=effective_ref):
            lockfile_urls.append(url_path(owner, repo, p))
    has_lockfile = bool(lockfile_urls)

    sbom_paths = [
        "sbom.json",
        "bom.json",
        "sbom.spdx.json",
        "bom.spdx.json",
        ".github/sbom.json",
    ]
    sbom_urls = []
    for p in sbom_paths:
        if gh_repo_file_exists(owner, repo, p, ref=effective_ref):
            sbom_urls.append(url_path(owner, repo, p))

    # SECURITY.md parse (E10) + audit harvest (E6.d)
    security_body = _read_repo_text(owner, repo, "SECURITY.md", effective_ref) or _read_repo_text(
        owner, repo, ".github/SECURITY.md", effective_ref
    )
    security_parse = parse_security_md(security_body or "")
    readme_body = _read_repo_text(owner, repo, "README.md", effective_ref) or ""
    audit_urls = _harvest_audit_urls(
        security_body or "",
        readme_body,
        (latest_rel or {}).get("body") or "",
    )
    if has_security and not any("SECURITY" in u for u in audit_urls):
        pass

    # Coverage signal for 2-16 (E2)
    has_coverage_signal = _detect_coverage_signal(readme_body, scorecard_map)

    # Package / deps.dev / Badge / PR sample / CMVP (E9, E14, E16, E6)
    progress("Detekuji balíček, deps.dev, badge a vzorek PR…")
    manifest_texts = {}
    for manifest in ("Cargo.toml", "pyproject.toml", "package.json"):
        body = _read_repo_text(owner, repo, manifest, effective_ref)
        if body:
            manifest_texts[manifest] = body
    package_info = detect_package(owner, repo, manifest_texts)
    depsdev_note = ""
    depsdev_url = ""
    dependents_count = None
    downloads_count = None
    downloads_meta: dict = {}
    pkg_version = (
        (TARGET_REF or "").lstrip("v")
        or package_info.get("version_hint")
        or (last_rel_name or "").lstrip("v")
    )
    if package_info.get("system") and package_info.get("name"):
        sys_name = package_info["system"]
        pkg_name = package_info["name"]
        depsdev_url = f"https://deps.dev/{sys_name}/{quote(pkg_name)}"
        dl = fetch_registry_downloads(sys_name, pkg_name)
        downloads_meta = dl
        if isinstance(dl.get("downloads"), int):
            downloads_count = dl["downloads"]
        if pkg_version:
            ver_payload = fetch_version(sys_name, pkg_name, pkg_version)
            adv_n = advisory_count(ver_payload)
            deps_payload = fetch_dependents(sys_name, pkg_name, pkg_version)
            dependents_count = dependent_count(deps_payload)
            depsdev_note = (
                f"deps.dev {sys_name}/{pkg_name}@{pkg_version}: "
                f"advisoryKeys≈{adv_n}, dependents≈{dependents_count} "
                f"(status={ver_payload.get('status')}/{deps_payload.get('status')})."
            )
            if adv_n > 0 and sev_hits_pre == 0:
                sev_hits_pre = max(sev_hits_pre, 1)
        elif downloads_count is not None:
            depsdev_note = (
                f"Registry downloads ({downloads_meta.get('source')}): {downloads_count}."
            )

    badge = lookup_badge(owner, repo)
    badge_note = ""
    if badge.get("tier"):
        badge_note = f"OpenSSF Badge: {badge.get('tier')}."
    elif badge.get("url"):
        badge_note = "OpenSSF Badge projekt nalezen."

    pr_stats = sample_merged_pr_stats(owner, repo, limit=30)
    github_security = collect_github_security(owner, repo)
    cmvp = search_cmvp(repo)
    no_fips_claim = not bool(
        re.search(r"\bfips\b|\b140-2\b|\b140-3\b", (security_body or "") + "\n" + readme_body, re.I)
    )

    # Sigstore-ish assets on latest release (feeds 2-17 / evidence packs)
    sig_assets = release_has_sigstore_assets((latest_rel or {}).get("assets") or [])
    for asset_url in sig_assets:
        low = str(asset_url).lower()
        if any(token in low for token in ("sbom", "spdx", "cyclonedx", "bom.json")):
            if asset_url not in sbom_urls:
                sbom_urls.append(asset_url)
    has_sbom = bool(sbom_urls)

    progress("Počítám heuristiky a vyplňuji otázky sekce 2…")
    one_year_ago = NOW - datetime.timedelta(days=365)
    last_release_ok = bool(
        last_release_date and last_release_date >= one_year_ago and not last_rel_is_prerelease
    )
    project_active = is_project_active(commits_cnt, releases_last_year)
    # Percentage over the inspected sample (not raw issue count) so the heuristic stays calibrated.
    maint_sample_size = len(comment_sample)
    maint_response_pct = pct(issues_with_maintainer_response, max(1, maint_sample_size))
    maint_res_ok = maint_response_pct >= 50.0

    urls = {
        "repo": url_repo(owner, repo),
        "releases": url_releases(owner, repo),
        "issues": url_issues(owner, repo),
        "workflows": url_path(owner, repo, ".github/workflows"),
        "codeowners": codeowners_url,
        "security": (
            (security_policy.get("security_md_url") if security_policy else None)
            or url_path(owner, repo, "SECURITY.md")
        ),
        "contributing": url_path(owner, repo, "CONTRIBUTING.md"),
        "readme": url_path(owner, repo, "README.md"),
        "funding": url_path(owner, repo, ".github/FUNDING.yml"),
        "tests": (
            (test_roots.get("urls") or [None])[0]
            if test_roots.get("urls")
            else url_path(owner, repo, "tests")
        ),
        "license": url_path(owner, repo, "LICENSE"),
    }
    ctx = {
        "repo_info": repo_info,
        "default_branch": default_branch,
        "effective_ref": effective_ref,
        "requested_ref": TARGET_REF,
        "releases": releases,
        "releases_last_year": releases_last_year,
        "releases_error": releases_error,
        "latest_rel": latest_rel,
        "commits_cnt": commits_cnt,
        "issues": issues,
        "issues_count": issues_count,
        "issues_with_maintainer_response": issues_with_maintainer_response,
        "maint_sample_size": maint_sample_size,
        "maint_response_pct": maint_response_pct,
        "maint_res_ok": maint_res_ok,
        "has_security": has_security,
        "security_policy": security_policy,
        "has_contributing": has_contributing,
        "has_coc": has_coc,
        "has_actions": has_actions,
        "has_tests": has_tests,
        "last_rel_is_prerelease": last_rel_is_prerelease,
        "last_rel_name": last_rel_name,
        "has_release_notes": has_release_notes,
        "cve_in_last_release": cve_in_last_release,
        "open_or_recent_vulns": open_or_recent_vulns,
        "vulns_filtered": vulns_filtered,
        "osv_evidence": osv_evidence,
        "stargazers": stargazers,
        "forks": forks,
        "watchers": watchers,
        "has_funding": has_funding,
        "contributors": contributors,
        "core_maintainers": core_maintainers,
        "project_active": project_active,
        "last_release_ok": last_release_ok,
        "last_rel_date_str": first(latest_rel, "published_at", "n/a") if latest_rel else "n/a",
        "has_readme": gh_repo_file_exists(owner, repo, "README.md", ref=effective_ref)
        or gh_repo_file_exists(owner, repo, "README.rst", ref=effective_ref),
        "has_license": bool(repo_info.get("license", {}).get("spdx_id")),
        "license_id": repo_info.get("license", {}).get("spdx_id", "neznámo"),
        "urls": urls,
        "scorecard_raw": scorecard_raw,
        "scorecard_map": scorecard_map,
        "branch_protection": branch_protection,
        "branch_rules": branch_rules,
        "contributing_url": contributing_url,
        "tests_required_in_contributing": tests_required_in_contributing,
        "has_dependabot": has_dependabot,
        "has_renovate": has_renovate,
        "dependabot_url": dependabot_url,
        "renovate_url": renovate_url,
        "has_lockfile": has_lockfile,
        "lockfile_urls": lockfile_urls,
        "has_sbom": has_sbom,
        "sbom_urls": sbom_urls,
        "security_parse": security_parse,
        "audit_urls": audit_urls,
        "has_coverage_signal": has_coverage_signal,
        "dependents_count": dependents_count,
        "downloads_count": downloads_count,
        "downloads_meta": downloads_meta,
        "depsdev_note": depsdev_note,
        "depsdev_url": depsdev_url,
        "package_info": package_info,
        "badge": badge,
        "badge_note": badge_note,
        "pr_stats": pr_stats,
        "github_security": github_security,
        "cmvp": cmvp,
        "no_fips_claim": no_fips_claim,
        "sig_assets": sig_assets,
    }
    q_index = {q["id"]: q for q in skeleton_section.get("questions", [])}

    def setq(qid, meets: str, note: str, evidence: str):
        if qid not in q_index:
            return
        q = q_index[qid]
        q["rating"] = meets
        q["note"] = note
        q["evidence"] = evidence
        q["heuristic_rating"] = True

    # Persist refs on section meta for run_all aggregation / OSV pinning.
    sec_meta = skeleton_section.setdefault("meta", {})
    if isinstance(sec_meta, dict):
        sec_meta["effective_ref"] = effective_ref
        sec_meta["default_branch"] = default_branch
        sec_meta["requested_ref"] = TARGET_REF or ""

    m, n, e = evaluate_q_2_1(ctx)
    setq("2-1", m, n, e)
    m, n, e = evaluate_q_2_1a(ctx)
    setq("2-1a", m, n, e)
    m, n, e = evaluate_q_2_1b(ctx)
    setq("2-1b", m, n, e)
    m, n, e = evaluate_q_2_1c(ctx)
    setq("2-1c", m, n, e)
    m, n, e = evaluate_q_2_1d(ctx)
    setq("2-1d", m, n, e)
    m, n, e = evaluate_q_2_2(ctx)
    setq("2-2", m, n, e)
    m, n, e = evaluate_q_2_3(ctx)
    setq("2-3", m, n, e)
    m, n, e = evaluate_q_2_4(ctx)
    setq("2-4", m, n, e)
    m, n, e = evaluate_q_2_5(ctx)
    setq("2-5", m, n, e)
    sev_hits = sev_hits_pre
    ctx["sev_hits"] = sev_hits
    m, n, e = evaluate_q_2_6(ctx)
    setq("2-6", m, n, e)
    m, n, e = evaluate_q_2_7(ctx)
    setq("2-7", m, n, e)
    m, n, e = evaluate_q_2_8(ctx)
    setq("2-8", m, n, e)
    m, n, e = evaluate_q_2_9(ctx)
    setq("2-9", m, n, e)
    m, n, e = evaluate_q_2_10(ctx)
    setq("2-10", m, n, e)
    m, n, e = evaluate_q_2_11(ctx)
    setq("2-11", m, n, e)
    m, n, e = evaluate_q_2_12(ctx)
    setq("2-12", m, n, e)
    m, n, e = evaluate_q_2_13(ctx)
    setq("2-13", m, n, e)
    m, n, e = evaluate_q_2_14(ctx)
    setq("2-14", m, n, e)
    m, n, e = evaluate_q_2_15(ctx)
    setq("2-15", m, n, e)
    m, n, e = evaluate_q_2_16(ctx)
    setq("2-16", m, n, e)
    m, n, e = evaluate_q_2_17(ctx)
    setq("2-17", m, n, e)
    m, n, e = evaluate_q_2_18(ctx)
    setq("2-18", m, n, e)
    m, n, e = evaluate_q_2_19(ctx)
    setq("2-19", m, n, e)
    m, n, e = evaluate_q_2_20(ctx)
    setq("2-20", m, n, e)
    m, n, e = evaluate_q_2_21(ctx)
    setq("2-21", m, n, e)
    m, n, e = evaluate_q_2_22(ctx)
    setq("2-22", m, n, e)

    sec_meta = skeleton_section.setdefault("meta", {})
    if isinstance(sec_meta, dict):
        sec_meta["default_branch"] = default_branch
        sec_meta["requested_ref"] = TARGET_REF
        sec_meta["effective_ref"] = effective_ref
        sec_meta["package_info"] = package_info
        if badge.get("url"):
            sec_meta["badge_url"] = badge.get("url")
        if depsdev_url:
            sec_meta["depsdev_url"] = depsdev_url
        if package_info.get("system") and package_info.get("name"):
            sys_name = package_info["system"]
            pkg_name = package_info["name"]
            if sys_name == "cargo":
                sec_meta["registry_url"] = f"https://crates.io/crates/{pkg_name}"
            elif sys_name == "pypi":
                sec_meta["registry_url"] = f"https://pypi.org/project/{pkg_name}/"
            elif sys_name == "npm":
                sec_meta["registry_url"] = f"https://www.npmjs.com/package/{pkg_name}"
        if downloads_meta.get("url"):
            sec_meta["downloads_url"] = downloads_meta["url"]
        if isinstance(dependents_count, int):
            sec_meta["dependents_count"] = dependents_count
        if isinstance(downloads_count, int):
            sec_meta["downloads_count"] = downloads_count
        sc_url = (scorecard_map.get("urls") or {}).get("Code-Review")
        if sc_url:
            sec_meta["scorecard_url"] = sc_url
        sec_meta["lockfile_urls"] = lockfile_urls
        sec_meta["sbom_urls"] = sbom_urls

    return skeleton_section


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=4)


def main():
    ap = argparse.ArgumentParser(description=text("script2", "cli", "description"))
    ap.add_argument("--repo", required=True, help=text("script2", "cli", "help_repo"))
    ap.add_argument("--skeleton", required=True, help=text("script2", "cli", "help_skeleton"))
    ap.add_argument("--out", required=True, help=text("script2", "cli", "help_out"))
    args = ap.parse_args()

    print(f"[START] [2.py] Zahajuji vyhodnocení sekce 2 pro {args.repo}", flush=True)
    if "/" not in args.repo:
        print(text("script2", "cli", "error_repo_format"), file=sys.stderr)
        sys.exit(2)
    owner, repo = args.repo.split("/", 1)

    print("[INFO] [2.py] Načítám skeleton formuláře a hledám sekci 2.", flush=True)
    data = load_json(args.skeleton)

    target = None
    for s in data.get("sections", []):
        if str(s.get("id")) == "2":
            target = s
            break
    if not target:
        print(text("script2", "cli", "error_missing_section"), file=sys.stderr)
        sys.exit(3)

    print(
        "[INFO] [2.py] Vyhodnocuji aktivitu, governance a bezpečnostní signály OSS projektu.",
        flush=True,
    )
    enriched = evaluate_open_source_section(owner, repo, target)

    for i, s in enumerate(data.get("sections", [])):
        if str(s.get("id")) == "2":
            data["sections"][i] = enriched
            break

    save_json(args.out, data)

    print(text("script2", "cli", "success_saved", path=args.out), file=sys.stderr)
    print(text("script2", "cli", "tip_token"), file=sys.stderr)
    print(f"[DONE] [2.py] Sekce 2 byla zapsána do {args.out}", flush=True)


if __name__ == "__main__":
    main()
