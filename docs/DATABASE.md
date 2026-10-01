# Database (krok 7)

## Layout

| Path | Role |
| --- | --- |
| `db/models.py` | SQLAlchemy models |
| `db/session.py` | Engine / session factory |
| `db/repos/` | Domain repositories (`users`, `libraries`, `evaluations`, …) |
| `db/repository.py` | Compatibility re-exports (`from db.repository import …`) |
| `alembic/` | Schema migrations |

## Default (SQLite)

No extra process. The app creates `data/review.db` automatically:

```text
DATABASE_URL=sqlite:////absolute/path/to/review/app/data/review.db
```

If `DATABASE_URL` is unset, the server uses `data/review.db` under the app root.

## Postgres later

1. Create a database and user.
2. Install a Postgres driver in the venv, e.g. `pip install "psycopg[binary]"`.
3. Set:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
```

4. Run migrations:

```sh
cd review/app
.venv/bin/alembic upgrade head
```

No router or model rewrite is required — only the URL (and driver) change.

## Migrations

```sh
.venv/bin/alembic upgrade head
.venv/bin/alembic revision --autogenerate -m "describe change"
```

Dev bootstrap also calls `init_db()` / `create_all` so a fresh clone works without Alembic, but Alembic remains the source of truth for schema history.

## Entities

- `User` — role `viewer` | `reviewer` | `admin` (krok 13 / `docs/ROLES.md`)
- `AuditEvent` — login, správa uživatelů, mazání (krok 13)
- `Library` / `LibraryVersion`
- `Evaluation` — form JSON + status
- `EvaluationEvent` — audit trail
- `Artifact` — file paths (`form`, later `pdf`, `log`) under `data/artifacts/`

## API

- `GET/POST /api/evaluations` — primary
- `GET/POST /api/drafts` — alias (same handlers)
- `GET /api/libraries`, `GET /api/libraries/{id}`
