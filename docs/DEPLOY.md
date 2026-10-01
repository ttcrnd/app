# Nasazení MVP (krok 10)

Veřejné demo do oponentury: HTTPS + přístupový kód + záloha SQLite.  
Kroky 11–13 (AI, podpis, plné role) **neblokují** kontrolní den.

## Co běží

| Komponenta | Poznámka |
| --- | --- |
| FastAPI + UI | `server:app` (uvicorn) |
| SQLite | `data/review.db` (v Dockeru volume `/data/review.db`) |
| Auth | `PILOT_ACCESS_CODE` (D8); volitelně `USER_AUTH_ENABLED` + role (krok 13, `docs/ROLES.md`) |
| Public read | Domů bez kódu = jen **Hotovo / Nedoporučeno** |
| Health | `GET /healthz` |

## Rychlý start (Docker)

```sh
cd review/app
cp .env.example .env
# povinné:
#   PILOT_ACCESS_CODE=...
#   PUBLIC_BASE_URL=https://demo.example.org
#   PILOT_COOKIE_SECURE=true
# doporučené:
#   GITHUB_TOKEN=...
#   PILOT_SESSION_SECRET=...   # stabilní mezi restarty

docker compose -f docker-compose.prod.yml up -d --build
curl -fsS http://127.0.0.1:8000/healthz
```

HTTPS: nasaď Caddy podle `Caddyfile` (Let's Encrypt automaticky) nebo vlastní reverse proxy s TLS.

## Záloha SQLite

```sh
./scripts/backup_sqlite.sh                 # → data/backups/review-YYYYMMDD….db
# (implementation: scripts/ops/backup_sqlite.sh)
# cron např. denně:
# 15 2 * * * cd /opt/nukib-review/app && ./scripts/backup_sqlite.sh /var/backups/nukib-review
```

Obnova: zastav app, zkopíruj `.db` na cestu z `DATABASE_URL`, spusť znovu.

## Checklist před oponenturou

1. `PILOT_ACCESS_CODE` nastaven; otevřený režim vypnutý.
2. `PILOT_COOKIE_SECURE=true` za HTTPS.
3. Domů bez kódu ukáže Hotovo/Nedoporučeno (seed D10).
4. Po kódu jde otevřít ukázku → K vyřízení → Hotovo → PDF koncept (viz [`demo-skript.md`](../../demo-skript.md)).
5. Záloha DB běží (cron / manuální).
6. Veřejná URL zapsaná níže.

## Veřejná URL

| Pole | Hodnota |
| --- | --- |
| URL | _doplň po nasazení — např. `https://demo.example.org`_ |
| Režim | chráněný pilot (kód na zápis; katalog completed veřejně číst) |
| Backup | `scripts/ops/backup_sqlite.sh` (wrapper: `scripts/backup_sqlite.sh`) |

## systemd (alternativa bez Dockeru)

Stávající `install_service.sh` + reverse proxy (Caddy/nginx) na `127.0.0.1:18765`.  
Nastav env v unit souboru: `PILOT_ACCESS_CODE`, `DATABASE_URL`, `PILOT_COOKIE_SECURE=true`.
