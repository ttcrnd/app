from __future__ import annotations

from pathlib import Path

# Package lives in review/app/review_app → project root is parent.
ROOT = Path(__file__).resolve().parent.parent

# Versioned source assets (templates, fixtures, fonts).
ASSETS_DIR = ROOT / "assets"
QUESTIONS_PATH = ASSETS_DIR / "questions.json"
EXAMPLE_DIR = ASSETS_DIR / "example"
FONTS_DIR = ASSETS_DIR / "fonts"

# Runtime (gitignored) — db, drafts, pipeline outputs, artifacts.
DATA_DIR = ROOT / "data"
DRAFTS_DIR = DATA_DIR / "drafts"
RAW_DIR = DATA_DIR / "raw"
RUNS_DIR = DATA_DIR / "runs"
ARTIFACTS_DIR = DATA_DIR / "artifacts"
# Convenience aliases written by run_all (form_<owner>_<repo>_<id>.json).
PIPELINE_OUT_DIR = DATA_DIR

# Legacy locations kept for one-shot migration / older docs.
LEGACY_OUT_DIR = ROOT / "out"
LEGACY_DRAFTS_DIR = LEGACY_OUT_DIR / "drafts"
LEGACY_QUESTIONS_PATH = ROOT / "questions.json"


def resolve_questions_path() -> Path:
    """Prefer assets/; fall back to root for older checkouts."""
    if QUESTIONS_PATH.exists():
        return QUESTIONS_PATH
    if LEGACY_QUESTIONS_PATH.exists():
        return LEGACY_QUESTIONS_PATH
    return QUESTIONS_PATH


WEB_DIR = ROOT / "web"
FORM_SCHEMA_PATH = ROOT / "schema" / "form_schema.json"
TERMINAL_EVAL_STATUSES = frozenset({"completed", "not_recommended"})
