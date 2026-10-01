#!/usr/bin/env python3
"""Verify a signed evaluation export (krok 12).

Usage:
  .venv/bin/python scripts/verify_signed_export.py path/to/signed_export.json
  .venv/bin/python scripts/verify_signed_export.py export.json --public-key data/signing/ed25519_public.pem
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.signing import verify_signed_export  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ověř Ed25519 podepsaný export hodnocení")
    parser.add_argument("path", type=Path, help="JSON soubor {payload, sig}")
    parser.add_argument(
        "--public-key",
        type=Path,
        default=None,
        help="PEM veřejného klíče (default: serverový klíč v data/signing/)",
    )
    args = parser.parse_args()
    wrapper = json.loads(args.path.read_text(encoding="utf-8"))
    pem = args.public_key.read_text(encoding="utf-8") if args.public_key else None
    result = verify_signed_export(wrapper, public_key_pem=pem, root=ROOT)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
