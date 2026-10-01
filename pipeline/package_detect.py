"""Detect package ecosystem + name from common manifest files (best-effort)."""

from __future__ import annotations

import re
from typing import Any


def detect_package(owner: str, repo: str, file_texts: dict[str, str]) -> dict[str, Any]:
    """
    file_texts: path -> content for manifests that exist.
    Returns {system, name, version_hint, source_path} or empty dict.
    """
    cargo = file_texts.get("Cargo.toml") or file_texts.get("cargo.toml")
    if cargo:
        name = _toml_str(cargo, "name") or repo
        ver = _toml_str(cargo, "version")
        return {"system": "cargo", "name": name, "version_hint": ver, "source_path": "Cargo.toml"}

    pyproject = file_texts.get("pyproject.toml")
    if pyproject:
        name = _toml_str(pyproject, "name") or repo
        ver = _toml_str(pyproject, "version")
        return {"system": "pypi", "name": name, "version_hint": ver, "source_path": "pyproject.toml"}

    pkg = file_texts.get("package.json")
    if pkg:
        name_m = re.search(r'"name"\s*:\s*"([^"]+)"', pkg)
        ver_m = re.search(r'"version"\s*:\s*"([^"]+)"', pkg)
        return {
            "system": "npm",
            "name": (name_m.group(1) if name_m else repo),
            "version_hint": ver_m.group(1) if ver_m else None,
            "source_path": "package.json",
        }

    return {}


def _toml_str(text: str, key: str) -> str | None:
    m = re.search(rf'(?m)^{re.escape(key)}\s*=\s*"([^"]+)"', text or "")
    if m:
        return m.group(1)
    m = re.search(rf"(?m)^{re.escape(key)}\s*=\s*'([^']+)'", text or "")
    return m.group(1) if m else None


def release_has_sigstore_assets(assets: list[dict[str, Any]] | None) -> list[str]:
    """Return URLs of sig/provenance-like release assets."""
    out: list[str] = []
    for asset in assets or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "").lower()
        url = asset.get("browser_download_url") or asset.get("url")
        if not url:
            continue
        if any(
            x in name
            for x in (
                ".sig",
                ".pem",
                "attestation",
                "provenance",
                "cosign",
                "sbom",
                ".spdx",
                "cyclonedx",
            )
        ):
            out.append(str(url))
    return out
