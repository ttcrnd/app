#!/usr/bin/env python3
"""Compatibility wrapper — implementation lives in pipeline.sections."""
from __future__ import annotations

from pipeline.sections.section_04_documentation import *  # noqa: F403
from pipeline.sections.section_04_documentation import main

if __name__ == "__main__":
    raise SystemExit(main())
