from __future__ import annotations

import pytest

pytest.importorskip("httpx2")

from server import _resolve_pdf_identification


def test_pdf_identification_uses_explicit_meta_values() -> None:
    form = {
        "meta": {
            "name": "OpenSSL",
            "type": "crypto library",
            "publisher": "OpenSSL Software Foundation",
            "url": "https://github.com/openssl/openssl",
            "version": "3.5.1",
        },
        "sections": [],
    }

    ident = _resolve_pdf_identification(form)
    assert ident["Název knihovny"] == "OpenSSL"
    assert ident["Typ knihovny"] == "crypto library"
    assert ident["Správce/vydavatel"] == "OpenSSL Software Foundation"
    assert ident["URL"] == "https://github.com/openssl/openssl"
    assert ident["Verze knihovny"] == "3.5.1"


def test_pdf_identification_falls_back_to_section_meta_repo_and_ref() -> None:
    form = {
        "meta": {"repo": ""},
        "sections": [
            {
                "id": "1",
                "meta": {
                    "repo": "openssl/openssl",
                    "effective_ref": "openssl-3.5.1",
                },
            }
        ],
    }

    ident = _resolve_pdf_identification(form)
    assert ident["Název knihovny"] == "openssl"
    assert ident["Správce/vydavatel"] == "openssl"
    assert ident["URL"] == "https://github.com/openssl/openssl"
    assert ident["Verze knihovny"] == "openssl-3.5.1"
