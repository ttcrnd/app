# Podepsaný export hodnocení (krok 12 / D14)

Ed25519 wrapper nad canonical JSON formuláře. Podpis je **volitelný** po Hotovo / Nedoporučeno.

## Formát

```json
{
  "payload": { "...formulář bez UI-only polí..." },
  "sig": {
    "alg": "ed25519",
    "key_id": "sha256:…",
    "value": "<base64>",
    "signed_at": "2026-09-19T12:00:00+00:00"
  }
}
```

V `payload.meta` zůstává lidský text **`approved_label` / `completion_note`** („Schválil: …“). Crypto je navíc.

## Klíče (pilot)

| Zdroj | Env / cesta |
| --- | --- |
| PEM v env | `SIGNING_PRIVATE_KEY_PEM` |
| Soubor | `SIGNING_KEY_PATH=/path/ed25519_private.pem` |
| Auto (dev) | `data/signing/ed25519_private.pem` + `ed25519_public.pem` |

Veřejný klíč: `GET /api/signing/public-key`.

## API

- `POST /api/evaluations/{id}/sign` — po completed / not_recommended
- `GET /api/evaluations/{id}/signed-export`
- `POST /api/evaluations/verify` — tělo = wrapper (nebo `{ "wrapper": …, "public_key_pem": … }`)

Selhání podpisu **nesmí** smazat hodnocení (API vrací chybu, DB zůstává).

## Ověření (oponentura)

```sh
.venv/bin/python scripts/verify_signed_export.py data/artifacts/<id>/signed_export.json \
  --public-key data/signing/ed25519_public.pem
```

Exit code `0` = valid. Změna jednoho `rating` v payload → verify fail.
