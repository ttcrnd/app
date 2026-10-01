#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing virtualenv python at $PYTHON_BIN. Run ./setup.sh first." >&2
  exit 1
fi

"$PYTHON_BIN" -m ruff check . --fix
"$PYTHON_BIN" -m black .
