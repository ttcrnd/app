# Role a autentizace (krok 13)

Plné role **viewer / reviewer / admin** nad pilotním přístupovým kódem (krok 5 / D8).

## Režimy

| Env | Chování |
| --- | --- |
| žádný kód, `USER_AUTH_ENABLED=false` | otevřený lokální režim (jako dřív) |
| `PILOT_ACCESS_CODE` + `PILOT_CODE_ENABLED=true` | gate kódem; session role `reviewer` |
| `USER_AUTH_ENABLED=true` | login jménem + heslem (PBKDF2); správa uživatelů |
| kód + `USER_AUTH_ENABLED=true` | kód = **nouzový bootstrap admin**; lze vypnout `PILOT_CODE_ENABLED=false` |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | bootstrap admin při startu, pokud účet chybí |

## Oprávnění

| Role | Katalog | Run / edit | Uživatelé | Mazání hodnocení |
| --- | --- | --- | --- | --- |
| viewer | Hotovo / Nedoporučeno (read) | ne | ne | ne |
| reviewer | + vlastní drafty | ano, **jen vlastní** (D11) | ne | ne |
| admin | vše | ano, všechna | ano | ano |

## API

- `POST /api/auth/login` — `{username, password}`
- `POST /api/auth/enter` — přístupový kód (bootstrap)
- `GET|POST|PATCH|DELETE /api/users` — jen admin
- Session cookie `nukib_pilot_session` (v2: user_id, username, role, method)

## Audit

Tabulka `audit_events`: `login`, `login_failed`, `user_created`, `user_updated`, `user_deleted`, mazání hodnocení.

## UI

- Gate: taby **Kód** / **Účet**
- Header: badge role + Odhlásit
- Navigace **Uživatelé** jen pro admin
- Viewer: skryté CTA Nové / Spustit / Dokončit
