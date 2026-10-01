#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
HOST="${REVIEW_SERVICE_HOST:-127.0.0.1}"
PORT="${REVIEW_SERVICE_PORT:-8000}"
RELOAD="${REVIEW_SERVER_RELOAD:-true}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing virtualenv python at $PYTHON_BIN. Run ./setup.sh first." >&2
  exit 1
fi

reload_flag=()
if [[ "$RELOAD" == "1" || "$RELOAD" == "true" || "$RELOAD" == "yes" ]]; then
  reload_flag=(--reload)
fi

exec "$PYTHON_BIN" -m uvicorn server:app --host "$HOST" --port "$PORT" "${reload_flag[@]}"
