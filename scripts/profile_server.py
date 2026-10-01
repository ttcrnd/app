#!/usr/bin/env python3
"""Compatibility wrapper — prefer scripts/ops/profile_server.py."""
from pathlib import Path
import runpy
import sys
sys.argv[0] = str(Path(__file__).resolve().parent / "ops" / "profile_server.py")
runpy.run_path(sys.argv[0], run_name="__main__")
