from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from domain.scoring import calculate_summary

ROOT = Path(__file__).resolve().parents[1]


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module {module_name} from {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_reference_form() -> dict:
    from db.repos.seed import synthetic_complete_form

    return synthetic_complete_form("openssl/openssl", "openssl-3.3.0")


def test_calibration_profile_lifts_reference_score():
    form = _load_reference_form()
    summary = calculate_summary(form)

    assert summary["overall_score"] >= 70.0
    assert summary.get("calibration", {}).get("profile") == "mature-oss-v1"
    assert summary.get("calibration", {}).get("reference_position") in {
        "reference-min",
        "reference-good",
        "reference-excellent",
    }


def test_server_summary_parity_with_shared_scoring():
    forms_mod = _load_module("forms_mod", ROOT / "review_app" / "forms.py")
    form = _load_reference_form()
    expected = calculate_summary(json.loads(json.dumps(form)))
    actual = forms_mod.calc_summary(json.loads(json.dumps(form)))

    assert actual == expected
