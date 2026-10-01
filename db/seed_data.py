"""Pilot library + evaluation seed (krok 8–9 / D10)."""

from __future__ import annotations

# Human-facing seed aligned with knihovny-pilot.md.
PILOT_LIBRARIES: list[dict[str, str]] = [
    {
        "repo": "openssl/openssl",
        "name": "OpenSSL",
        "ref": "openssl-3.3.0",
        "blurb": "Referenční C kryptografická knihovna — povinná v pilotní sadě.",
    },
    {
        "repo": "rpgp/rpgp",
        "name": "rPGP",
        "ref": "v0.19.0",
        "blurb": "OpenPGP v Rustu — jiný ekosystém než C (D7).",
    },
    {
        "repo": "jedisct1/libsodium",
        "name": "libsodium",
        "ref": "1.0.20-RELEASE",
        "blurb": "Kandidát ke srovnání / případnému odmítnutí vůči OpenSSL-like stacku.",
    },
]

# Fixed evaluation IDs so seed is idempotent across restarts.
PILOT_EVALUATIONS: list[dict[str, str]] = [
    {
        "id": "pilot-openssl-330",
        "repo": "openssl/openssl",
        "ref": "openssl-3.3.0",
        "example": "form_openssl_openssl.json",
        "outcome": "completed",
        "note": "Pilotní Hotovo (D10): referenční C knihovna z pipeline ukázky; finální expertní doladění přes UI Domů → Pokračovat.",
    },
    {
        "id": "pilot-rpgp-019",
        "repo": "rpgp/rpgp",
        "ref": "v0.19.0",
        "example": "form_rpgp_rpgp.json",
        "outcome": "completed",
        "note": "Pilotní Hotovo (D10): Rust OpenPGP; sekce 5 dle D7 spíš ručně — empirie CONFIRM u API.",
    },
    {
        "id": "pilot-libsodium-1020",
        "repo": "jedisct1/libsodium",
        "ref": "1.0.20-RELEASE",
        "example": "",
        "outcome": "not_recommended",
        "note": "Pilotní Nedoporučeno (D10): pro interní stack preferujeme OpenSSL-like cestu; libsodium zůstává jako srovnávací kandidát k odmítnutí.",
    },
]
