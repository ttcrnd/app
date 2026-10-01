from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_script5():
    # Ensure package imports (pipeline, utils) resolve when loading section 5.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    path = ROOT / "pipeline" / "sections" / "section_05_security_api.py"
    spec = importlib.util.spec_from_file_location("script5_mod", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["script5_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_c_openssl_profile_when_c_share_high():
    mod = _load_script5()
    profile = mod.classify_crypto_api_profile({"C": 80, "Python": 20}, {})
    assert profile["mode"] == "c_openssl"


def test_manual_profile_for_unknown_ecosystem():
    mod = _load_script5()
    profile = mod.classify_crypto_api_profile({"Java": 90, "Shell": 10}, {})
    assert profile["mode"] == "manual"
    assert "D7" in profile["reason"] or "ruční" in profile["reason"]


def test_rust_profile_when_rust_dominant():
    mod = _load_script5()
    profile = mod.classify_crypto_api_profile({"Rust": 90, "Shell": 10}, {})
    assert profile["mode"] == "rust"


def test_openssl_headers_force_c_profile():
    mod = _load_script5()
    headers = {"evp.h": {"path": "include/openssl/evp.h"}}
    profile = mod.classify_crypto_api_profile({"Rust": 100}, headers)
    assert profile["mode"] == "c_openssl"
