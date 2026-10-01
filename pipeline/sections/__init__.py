"""Per-section evaluation runners (formerly scripts/1.py … 5.py)."""

from __future__ import annotations

from pathlib import Path

SECTIONS_DIR = Path(__file__).resolve().parent

SECTION_MODULES = {
    "1": "section_01_prerequisites.py",
    "2": "section_02_oss_quality.py",
    "3": "section_03_code_quality.py",
    "4": "section_04_documentation.py",
    "5": "section_05_security_api.py",
}


def section_script_path(step_id: str) -> Path:
    name = SECTION_MODULES[str(step_id)]
    return SECTIONS_DIR / name
