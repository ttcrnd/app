from __future__ import annotations

from domain.meta_enrichment import (
    build_evidence_pack,
    diff_form_ratings,
    enrich_form_meta,
    infer_library_type,
)


def test_enrich_sets_assessment_date_and_type():
    form = {
        "meta": {"repo": "openssl/openssl", "started_at": "2026-09-20T10:00:00+00:00"},
        "sections": [{"meta": {"languages": {"C": 90, "Perl": 10}, "topics": ["cryptography"]}}],
    }
    enrich_form_meta(form)
    assert form["meta"]["assessment_date"] == "2026-09-20"
    assert "kryptografická" in form["meta"]["library_type"]
    pack = form["meta"]["evidence_pack"]
    assert 3 <= len(pack) <= 5
    assert pack[0]["url"].startswith("https://github.com/openssl/openssl")


def test_build_evidence_pack_dedupes():
    form = {
        "meta": {"repo": "rpgp/rpgp"},
        "sections": [
            {
                "questions": [
                    {"id": "2-4", "evidence": "https://github.com/rpgp/rpgp/blob/main/SECURITY.md\nhttps://github.com/rpgp/rpgp"}
                ]
            }
        ],
    }
    pack = build_evidence_pack(form)
    urls = [p["url"].rstrip("/").lower() for p in pack]
    assert len(urls) == len(set(urls))
    assert len(pack) <= 5


def test_diff_form_ratings():
    prev = {
        "sections": [
            {
                "questions": [
                    {"id": "2-1", "rating": "splňuje"},
                    {"id": "2-2", "rating": "částečně splňuje"},
                ]
            }
        ]
    }
    cur = {
        "sections": [
            {
                "questions": [
                    {"id": "2-1", "rating": "splňuje"},
                    {"id": "2-2", "rating": "splňuje"},
                    {"id": "2-3", "rating": "nesplňuje"},
                ]
            }
        ]
    }
    changes = diff_form_ratings(cur, prev)
    assert changes == [{"id": "2-2", "from": "částečně splňuje", "to": "splňuje"}]


def test_infer_library_type_default():
    assert infer_library_type({"meta": {"repo": "acme/lib"}}) == "softwarová knihovna"
