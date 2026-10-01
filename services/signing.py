"""Ed25519 signed evaluation export (krok 12 / D14)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KEY_DIR = ROOT / "data" / "signing"
PRIVATE_KEY_NAME = "ed25519_private.pem"
PUBLIC_KEY_NAME = "ed25519_public.pem"

# UI / volatile fields excluded from the signed payload.
_DROP_TOP_LEVEL_PREFIXES = ("_",)
_DROP_META_KEYS = {
    "ai_note_pending",
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def strip_volatile(obj: Any) -> Any:
    """Remove UI-only / volatile fields before canonicalization."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if any(key.startswith(p) for p in _DROP_TOP_LEVEL_PREFIXES):
                continue
            if key == "meta" and isinstance(value, dict):
                meta = {
                    mk: strip_volatile(mv)
                    for mk, mv in value.items()
                    if mk not in _DROP_META_KEYS and not str(mk).startswith("_")
                }
                out[key] = meta
                continue
            out[key] = strip_volatile(value)
        return out
    if isinstance(obj, list):
        return [strip_volatile(item) for item in obj]
    return obj


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    cleaned = strip_volatile(payload)
    text = json.dumps(cleaned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return text.encode("utf-8")


def key_id_from_public_raw(raw: bytes) -> str:
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return f"sha256:{digest}"


def _load_private_key_pem(pem: bytes) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Očekáván Ed25519 private key")
    return key


def _load_public_key_pem(pem: bytes) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Očekáván Ed25519 public key")
    return key


def ensure_signing_keys(root: Path | None = None) -> tuple[Ed25519PrivateKey, Path, Path]:
    """
    Load private key from env/file, or generate a pilot keypair under data/signing/.
    Env:
      SIGNING_PRIVATE_KEY_PEM — PEM text (\\n escaped ok)
      SIGNING_KEY_PATH — path to private PEM
    """
    base = root or ROOT
    pem_env = (os.environ.get("SIGNING_PRIVATE_KEY_PEM") or "").strip()
    if pem_env:
        pem = pem_env.replace("\\n", "\n").encode("utf-8")
        private = _load_private_key_pem(pem)
        key_dir = base / "data" / "signing"
        key_dir.mkdir(parents=True, exist_ok=True)
        pub_path = key_dir / PUBLIC_KEY_NAME
        if not pub_path.exists():
            pub_path.write_bytes(_public_pem(private.public_key()))
        return private, key_dir / PRIVATE_KEY_NAME, pub_path

    path_env = (os.environ.get("SIGNING_KEY_PATH") or "").strip()
    if path_env:
        priv_path = Path(path_env).expanduser()
        pub_path = priv_path.with_name(PUBLIC_KEY_NAME)
        if priv_path.exists():
            private = _load_private_key_pem(priv_path.read_bytes())
            if not pub_path.exists():
                pub_path.write_bytes(_public_pem(private.public_key()))
            return private, priv_path, pub_path
        priv_path.parent.mkdir(parents=True, exist_ok=True)
        private = Ed25519PrivateKey.generate()
        priv_path.write_bytes(
            private.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        pub_path.write_bytes(_public_pem(private.public_key()))
        try:
            priv_path.chmod(0o600)
        except OSError:
            pass
        return private, priv_path, pub_path

    key_dir = DEFAULT_KEY_DIR if root is None else (base / "data" / "signing")
    key_dir.mkdir(parents=True, exist_ok=True)
    priv_path = key_dir / PRIVATE_KEY_NAME
    pub_path = key_dir / PUBLIC_KEY_NAME
    if priv_path.exists():
        private = _load_private_key_pem(priv_path.read_bytes())
        if not pub_path.exists():
            pub_path.write_bytes(_public_pem(private.public_key()))
        return private, priv_path, pub_path

    private = Ed25519PrivateKey.generate()
    priv_path.write_bytes(
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    pub_path.write_bytes(_public_pem(private.public_key()))
    try:
        priv_path.chmod(0o600)
    except OSError:
        pass
    return private, priv_path, pub_path


def _public_pem(public: Ed25519PublicKey) -> bytes:
    return public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def public_key_info(root: Path | None = None) -> dict[str, str]:
    private, _priv_path, pub_path = ensure_signing_keys(root)
    public = private.public_key()
    raw = public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "alg": "ed25519",
        "key_id": key_id_from_public_raw(raw),
        "public_key_pem": _public_pem(public).decode("utf-8"),
        "public_key_path": str(pub_path),
    }


def sign_payload(form_obj: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    """Return signed wrapper {payload, sig}. Does not mutate the original form."""
    private, _, _ = ensure_signing_keys(root)
    public = private.public_key()
    raw_pub = public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    payload = strip_volatile(form_obj)
    if not isinstance(payload.get("meta"), dict):
        payload["meta"] = {}
    # Human approval text stays in payload (krok 8 completion note).
    message = canonical_json_bytes(payload)
    signature = private.sign(message)
    sig = {
        "alg": "ed25519",
        "key_id": key_id_from_public_raw(raw_pub),
        "value": base64.b64encode(signature).decode("ascii"),
        "signed_at": _utcnow_iso(),
    }
    return {"payload": payload, "sig": sig}


def verify_signed_export(
    wrapper: dict[str, Any],
    *,
    public_key_pem: str | bytes | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(wrapper, dict):
        raise ValueError("Očekáván JSON objekt s payload a sig")
    payload = wrapper.get("payload")
    sig = wrapper.get("sig")
    if not isinstance(payload, dict) or not isinstance(sig, dict):
        raise ValueError("Chybí payload nebo sig")
    alg = str(sig.get("alg") or "").lower()
    if alg != "ed25519":
        raise ValueError(f"Nepodporovaný alg: {alg}")
    value_b64 = str(sig.get("value") or "")
    try:
        signature = base64.b64decode(value_b64, validate=True)
    except Exception as e:
        raise ValueError("Neplatný base64 podpis") from e

    if public_key_pem:
        pem = public_key_pem.encode("utf-8") if isinstance(public_key_pem, str) else public_key_pem
        public = _load_public_key_pem(pem)
    else:
        private, _, _ = ensure_signing_keys(root)
        public = private.public_key()

    message = canonical_json_bytes(payload)
    try:
        public.verify(signature, message)
        ok = True
        error = ""
    except InvalidSignature:
        ok = False
        error = "Podpis neodpovídá payload (obsah byl změněn nebo jiný klíč)."
    except Exception as e:
        ok = False
        error = str(e)

    raw_pub = public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    expected_kid = key_id_from_public_raw(raw_pub)
    kid_match = str(sig.get("key_id") or "") in {"", expected_kid}
    return {
        "valid": ok and kid_match,
        "alg": "ed25519",
        "key_id": expected_kid,
        "signed_at": sig.get("signed_at") or "",
        "error": error if not ok else ("" if kid_match else "key_id nesouhlasí"),
    }
