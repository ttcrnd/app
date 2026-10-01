#!/usr/bin/env python3
"""Compatibility wrapper — prefer scripts/ops/verify_signed_export.py."""
from pathlib import Path
import runpy
import sys
sys.argv[0] = str(Path(__file__).resolve().parent / "ops" / "verify_signed_export.py")
runpy.run_path(sys.argv[0], run_name="__main__")
