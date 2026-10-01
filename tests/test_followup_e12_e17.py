from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.workflow import FORCE_CONFIRM_IDS
from integrations.depsdev import advisory_count, dependent_count
from integrations.github_security import security_features_note
from pipeline.crypto_signals import scan_crypto_docs
from pipeline.sections.section_02_oss_quality import evaluate_q_2_9, evaluate_q_2_15


def test_dependent_count_parses():
    assert dependent_count({"status": 200, "data": {"dependentCount": 1234}}) == 1234
    assert dependent_count({"status": 404, "data": None}) is None


def test_advisory_count_parses():
    assert advisory_count({"data": {"advisoryKeys": ["a", "b"]}}) == 2
    assert advisory_count({"data": {}}) == 0


def test_security_features_note():
    note = security_features_note(
        {
            "private_reporting": True,
            "advisories_count": 2,
            "dependabot_open": 3,
            "dependabot_by_severity": {"high": 1, "medium": 2},
        }
    )
    assert "Private vulnerability reporting: zapnuto" in note
    assert "advisories: 2" in note
    assert "Dependabot alerts: 3" in note


def test_crypto_signals_vectors_and_ban():
    docs = [
        (
            "README.md",
            "We run Wycheproof vectors. AES-ECB is deprecated and must not be used. dudect timing tests.",
        )
    ]
    sig = scan_crypto_docs(docs)
    assert sig["has_vectors"] is True
    assert sig["has_timing_tests"] is True
    assert sig["has_ban_list"] is True


def test_2_9_self_merge_heavy_not_meets():
    ctx = {
        "urls": {"repo": "https://github.com/acme/lib", "workflows": "https://github.com/acme/lib/actions"},
        "branch_protection": {},
        "scorecard_map": {"checks": {"Code-Review": 9, "Branch-Protection": 8}, "urls": {}},
        "pr_stats": {
            "available": True,
            "sampled": 20,
            "approval_rate": 0.2,
            "self_merge_rate": 0.7,
            "urls": ["https://github.com/acme/lib/pull/1"],
        },
    }
    rating, note, _ = evaluate_q_2_9(ctx)
    assert rating == "částečně splňuje"
    assert "self-merge" in note.lower() or "self-merge" in note


def test_2_15_prefer_dependents_over_stars():
    ctx = {
        "stargazers": 10,
        "forks": 1,
        "watchers": 1,
        "dependents_count": 80,
        "downloads_count": None,
        "downloads_meta": {},
        "depsdev_url": "https://deps.dev/cargo/foo",
        "urls": {"repo": "https://github.com/acme/lib"},
    }
    # text() localization may need env — call and check metric path via note
    rating, note, evidence = evaluate_q_2_15(ctx)
    assert rating == "splňuje"
    assert "dependents=80" in note
    assert "deps.dev" in evidence or evidence.startswith("http")


def test_force_confirm_includes_2_9():
    assert "2-9" in FORCE_CONFIRM_IDS
