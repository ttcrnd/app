#!/usr/bin/env bash
# Setup a local virtual environment and install dependencies
# Usage: ./setup.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
PYTHON_BIN=""

choose_python() {
  # Prefer python3 if available, else fallback to python
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "Error: Python is not installed or not on PATH." >&2
    echo "Please install Python 3.9+ and re-run this script." >&2
    exit 1
  fi
}

create_venv() {
  if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR ..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  else
    echo "Virtual environment already exists at $VENV_DIR"
  fi
}

upgrade_pip() {
  echo "Upgrading pip/setuptools/wheel ..."
  "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
}

ensure_pip() {
  if "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then
    return
  fi
  echo "pip not found in the virtual environment, bootstrapping via ensurepip ..."
  "$VENV_DIR/bin/python" -m ensurepip --upgrade
}

install_requirements() {
  if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    echo "Installing dependencies from requirements.txt ..."
    "$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
  else
    echo "No requirements.txt found; skipping dependency install."
  fi
}

print_success() {
  echo "\n✅ Environment ready."
  echo "To activate it in your shell:"
  echo "  source .venv/bin/activate"
  echo "\nTo run project checks:"
  echo "  make check"
  echo "\nTo run a script (example for scripts/4.py):"
  echo "  .venv/bin/python scripts/4.py --help"
}

choose_python
create_venv
ensure_pip
upgrade_pip
install_requirements
print_success
