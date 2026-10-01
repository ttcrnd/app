"""Sample merged PRs for review heuristics (E16)."""

from __future__ import annotations

from typing import Any

from integrations.github import get as gh_get


def sample_merged_pr_stats(owner: str, repo: str, *, limit: int = 30) -> dict[str, Any]:
    """
    REST best-effort: recent closed PRs, keep merged ones, inspect reviews.
    Returns metrics + evidence URLs. Never raises.
    """
    status, data, _ = gh_get(
        f"/repos/{owner}/{repo}/pulls",
        params={"state": "closed", "sort": "updated", "direction": "desc", "per_page": min(100, limit * 2)},
    )
    if status != 200 or not isinstance(data, list):
        return {
            "available": False,
            "status": status,
            "sampled": 0,
            "with_non_author_approval": 0,
            "self_merge": 0,
            "median_reviewers": None,
            "urls": [f"https://github.com/{owner}/{repo}/pulls?q=is%3Apr+is%3Amerged"],
        }

    merged = [p for p in data if isinstance(p, dict) and p.get("merged_at")][:limit]
    with_approval = 0
    self_merge = 0
    reviewer_counts: list[int] = []
    urls: list[str] = []

    for pr in merged:
        number = pr.get("number")
        author = ((pr.get("user") or {}) or {}).get("login") or ""
        html = pr.get("html_url")
        if html:
            urls.append(html)
        st_r, reviews, _ = gh_get(f"/repos/{owner}/{repo}/pulls/{number}/reviews", params={"per_page": 50})
        approvers: set[str] = set()
        if st_r == 200 and isinstance(reviews, list):
            for rev in reviews:
                if not isinstance(rev, dict):
                    continue
                if str(rev.get("state") or "").upper() != "APPROVED":
                    continue
                login = ((rev.get("user") or {}) or {}).get("login") or ""
                if login and login != author:
                    approvers.add(login)
        reviewer_counts.append(len(approvers))
        if approvers:
            with_approval += 1
        # Self-merge proxy: merged by author and no non-author approval
        merged_by = ((pr.get("merged_by") or {}) or {}).get("login") or ""
        if merged_by and merged_by == author and not approvers:
            self_merge += 1

    sampled = len(merged)
    median = None
    if reviewer_counts:
        ordered = sorted(reviewer_counts)
        mid = len(ordered) // 2
        median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2

    return {
        "available": True,
        "status": status,
        "sampled": sampled,
        "with_non_author_approval": with_approval,
        "self_merge": self_merge,
        "approval_rate": (with_approval / sampled) if sampled else 0.0,
        "self_merge_rate": (self_merge / sampled) if sampled else 0.0,
        "median_reviewers": median,
        "urls": urls[:5]
        or [f"https://github.com/{owner}/{repo}/pulls?q=is%3Apr+is%3Amerged"],
    }
