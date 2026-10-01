# Review Repo

This repository contains evaluation pipeline sections (`pipeline/sections/`), thin compatibility wrappers (`scripts/1.py`–`scripts/5.py`), an orchestrator (`run_all.py`), and a FastAPI server (`server.py`) with a simple web UI.

## Quickstart

1) Create and populate a virtual environment:

```sh
./setup.sh
```

2) Activate it in your shell (optional for convenience):

```sh
source .venv/bin/activate
```

3) Run any script, for example:

```sh
.venv/bin/python scripts/4.py --help
```

## Orchestration: run all scripts

To run all scripts (1.py through 5.py) sequentially for a given GitHub repository, use the coordinator:

```sh
.venv/bin/python run_all.py owner/repo
```

Examples:

```sh
# Using owner/repo
.venv/bin/python run_all.py openssl/openssl

# Using full URL (token is auto‑loaded from .env or environment variables)
.venv/bin/python run_all.py https://github.com/openssl/openssl

# Using a specific branch/tag ref from URL
.venv/bin/python run_all.py https://github.com/openssl/openssl/tree/openssl-3.5.1
```

By default, the coordinator uses `assets/questions.json` as a template, creates a working copy under `./data/runs/<run_id>/`, and each script incrementally fills its section into the same file. The final aggregated result is a single JSON file:

- `data/form_<owner>_<repo>_<id>.json` — convenience alias of the consolidated output.

Raw evidence snapshots (when collected) are stored under `data/raw/`.

When input URL contains `/tree/<ref>`, pipeline evaluates using that reference where supported and stores it in output metadata (`meta.requested_ref`, `meta.effective_ref`, `meta.evaluated_repo_version`).

After aggregation, the coordinator performs:
- Evidence normalization (all `dukaz` fields become newline‑separated strings),
- JSON Schema validation (non‑blocking; reports PASS/FAIL), and
- Summary scoring (must‑have cutoffs + weighted section scores) added under the top‑level key `summary` in the final JSON, e.g.:
  - `summary.cutoffs` — must‑have cutoff result across sections 1–5,
  - `summary.section_scores` — per‑section percentages (0–100),
  - `summary.overall_score` — weighted total (0–100),
  - `summary.grade` — one of `cutoff-fail`, `fail`, `pass`, `good`, `excellent`,
  - `summary.calibration` — active scoring calibration profile (rating points, category weights, benchmark band).

## Web server + simple UI

There is a lightweight server and UI in this repository so you can run the pipeline from a browser.

The FastAPI app lives in the `review_app/` package (`create_app()` in `review_app/main.py`,
routers under `review_app/api/routes/`). `server.py` remains a thin entrypoint so
`uvicorn server:app` and existing tests keep working.

Runtime settings are centralized in `review_app.settings.AppSettings` (loads `.env` once).
Copy env from `.env.example` only (`.example.env` is deprecated).

Persistence helpers live in `db/repos/` (`db/repository.py` is a compatibility facade).

Shared Python code is split by layer — `auth/`, `services/`, `integrations/`, `domain/` —
with thin re-exports left under `utils/` for older import paths.

Frontend JS entry is `web/app.js` (ES module) which loads `web/js/main.js`. Feature modules:
`auth.js`, `catalog.js`, `work.js`, `pipeline.js`, `autosave.js`, `form-details.js`,
`form-question.js`, plus `runtime.js` / `deps.js` / `form-utils.js`.

Ops helpers live in `scripts/ops/` (backup, lint, test, format, dev); `scripts/*.sh` remain thin wrappers.

Start the server (locally):

```sh
make setup
make dev
```

Then open in your browser:

- http://127.0.0.1:8000/

How it works:

- Enter a URL or `owner/repo` and click "Run".
- The server launches the orchestrator (`run_all.py`) in the background and streams progress to the UI via SSE.
- Once finished, the server reads the run artifact under `data/` and the UI renders it on the right (including the `summary`).
- The `Výsledek` panel explicitly marks the raw JSON as the final output file and links it to the `Stáhnout JSON` action.

Notes:

- The token (`GITHUB_TOKEN`/`GH_TOKEN`) is loaded automatically the same way as for CLI runs (from the environment or `.env`).
- The UI now shows a live pipeline state card with step tracker (`0`-`5` + `F` finalization), animated running indicator, and progress bar.
- You can load your own local evaluation file via `Nebo nahraj vlastní JSON`; the app validates JSON syntax and schema before rendering.
- If uploaded JSON is invalid, UI shows a user-friendly explanation (where validation failed and what to fix).
- PDF export fills library identification from form metadata with fallbacks (`meta` -> `sections[*].meta` -> `repo/effective_ref`), so name/version/URL/publisher stay populated even when top-level metadata is incomplete.
- Log stream uses readable prefixes:
  - `[START]` job or phase start,
  - `[STEP]` pipeline phase boundaries,
  - `[INFO]` current activity details,
  - `[WARN]` recoverable problems / degraded path,
  - `[DONE]` successful completion of step or whole pipeline.
- In question ratings, `nehodnoceno` means "not evaluated yet", `nesplňuje` means a confirmed failure, and `nevztahuje se` closes the row without claiming methodology MEETS (excluded from section averages; does not fail must-have cutoffs).
- Default queue **K vyřízení** walks must-have and low-confidence items first (`N` / Další).
- Pipeline enrichment (best-effort, never invents MEETS on API errors): OpenSSF Scorecard, branch protection, Dependabot/Renovate, SECURITY.md parse, deps.dev notes, OpenSSF Best Practices Badge, package/registry+Sigstore hints, CMVP search, PR review sample, misuse scan, language crypto profiles.
- External enrichment quotas: set `GITHUB_TOKEN`/`GH_TOKEN` for GitHub GraphQL/REST; deps.dev and Badge APIs are public but rate-limited — offline runs stay green without them.
- Workflow badges in question detail:
  - `Vyžaduje potvrzení` = automation found evidence, but user confirmation is required.
  - `Ručně vyhodnotit` = automation cannot confirm the outcome, so user must rate it manually.
  - `Hotovo` = the question is already confirmed.
  - `Automaticky` / `Manuálně` = indicates whether confirmation came from automation or manual review.
  - Rating badge (`Splňuje`, `Částečně`, `Nesplňuje`, `Nehodnoceno`) shows the final outcome.
- Question detail is split into `Kontext otázky` and `Akce hodnotitele` so required user actions are visible immediately.
- Details toolbar supports combined filtering: fulltext search (ID/text/category/note/evidence), rating chips, and evaluation-type chips.
- Use `Obnovit výchozí filtry` to return to the default view; `Vymazat` next to search clears only fulltext.

## Shared utilities

- `httputils.py`
  - Thin HTTP helpers (GET/HEAD/POST JSON) preferring `requests` with `urllib` as a fallback.
  - Functions: `http_get`, `http_head`, `http_post_json`, `get_json`, `get_text`.

- `githubutils.py`
  - Unified GitHub REST v3 calls: headers, GET with params, pagination, code search, and repo contents.
  - Functions: `default_headers`, `get`, `paginate`, `get_full_url_json`, `http_get_full`, `search_code`, `repo_file_exists`, `list_dir`, `get_file`, `actions_exists`.

### Tokens: automatic loading
- The coordinator first checks exported env vars `GITHUB_TOKEN` or `GH_TOKEN`.
- If not set, it tries to load `.env` in the project root and read `GITHUB_TOKEN` or `GH_TOKEN` from there.

Create your `.env` from the template:

```sh
cp .env.example .env
echo "GITHUB_TOKEN=ghp_xxx" >> .env
```

## Developer workflow

Core commands:

```sh
make setup   # create/update .venv + install dependencies
make check   # lint + tests
make fix     # auto-fix + format + tests
make dev     # run FastAPI server with reload
make clean   # remove out/, data pipeline scratch, and local caches (alias: make clear); keeps .venv and review.db
```

Terminal screen wipe is the shell command `clear`, not Make.
Direct scripts (if needed):

```sh
./scripts/lint.sh
./scripts/format.sh
./scripts/test.sh
./scripts/dev.sh
# (wrappers; implementations live in scripts/ops/)
```

## Running tests

Tests are written with pytest and run offline (no network calls) thanks to monkeypatching, so `GITHUB_TOKEN` isn’t required.

Run all tests:

```sh
.venv/bin/pytest -q
```

Useful variants:

- More verbose output:

  ```sh
  .venv/bin/pytest -vv
  ```

- Run a single file/test:

  ```sh
  # only the orchestrator smoke test
  .venv/bin/pytest -q tests/test_run_all_smoke.py

  # only tests matching a name
  .venv/bin/pytest -q -k test_end_to_end_aggregate
  ```

- Stop after first failure:

  ```sh
  .venv/bin/pytest -x
  ```

Notes:

- Tests use temporary directories and won’t write into `data/` in your working tree.
- To print a list of generated files, run with `-s`:

  ```sh
  .venv/bin/pytest -q -s
  ```

  At the end of each test, a section `[artifacts] ... generated:` is printed with relative paths.

## Notes
- Dependencies are listed in `requirements.txt`.
- The environment is created in `.venv/` and ignored by git.
- Works on macOS/Linux. On Windows (PowerShell), use:
  - Create venv: `py -3 -m venv .venv`
  - Activate: `.venv\\Scripts\\Activate.ps1`
  - Run: `.venv\\Scripts\\python.exe scripts\\4.py --help`

## Deploy as a Debian/Ubuntu service

For the MVP public demo (HTTPS, SQLite backup, access code), see **[`docs/DEPLOY.md`](docs/DEPLOY.md)** and `docker-compose.prod.yml`. Demo walkthrough: [`../demo-skript.md`](../demo-skript.md).  
Optional AI note assist (default off): [`docs/AI.md`](docs/AI.md).  
Signed completed export (Ed25519): [`docs/SIGNING.md`](docs/SIGNING.md) — verify with `scripts/verify_signed_export.py`.

You can also install the FastAPI server as a systemd service so it survives reboots:

1. Ensure `.env` contains `GITHUB_TOKEN=...` (copy from `.env.example` if necessary).
2. From the project root, run:

   ```sh
   sudo ./install_service.sh
   ```

   The script:

   - Detects a non-root account (or honor `SERVICE_USER=<user>`) and runs `./setup.sh` for that user.
   - Installs `/etc/systemd/system/security-review.service` pointing at `.venv/bin/python -m uvicorn server:app`.
   - Enables and starts the service immediately (`http://0.0.0.0:18765/` by default to avoid common ports).

   To adjust defaults, export variables before running the script:

   - `SERVICE_USER=ci` – account that owns the repository and `.venv`
   - `REVIEW_SERVICE_HOST=127.0.0.1` – bind address for uvicorn
   - `REVIEW_SERVICE_PORT=9000` – listening port
   - `REVIEW_SERVICE_NAME=security-review.service` – custom unit name

3. Manage the service with `sudo systemctl [status|restart|stop] security-review.service`.
4. To remove the service cleanly (unit file only; repo and `.venv` remain):

   ```sh
   sudo ./uninstall_service.sh
   ```

## Code style and quality

Tools:

- Formatter: Black (configured in `pyproject.toml`, line length 100)
- Linter + import sorting: Ruff
- Hooks: pre-commit

Install tools together with the project dependencies:

```sh
.venv/bin/python -m pip install -r requirements.txt
```

Manual runs:

```sh
# lint
.venv/bin/python -m ruff check .
.venv/bin/python -m black --check .

# auto-fix + format
.venv/bin/python -m ruff check . --fix
.venv/bin/python -m black .

# pre-commit across repository
.venv/bin/pre-commit run --all-files
```

VS Code is configured to format on save (see `.vscode/settings.json`). For the best experience, install the "Ruff" extension.

## Docker (local)

```sh
docker compose up --build
```

Then open `http://127.0.0.1:8000/`.
