#!/usr/bin/env bash
# Remove the review FastAPI server systemd service.
set -euo pipefail

SERVICE_NAME="${REVIEW_SERVICE_NAME:-security-review.service}"

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (tip: sudo ./uninstall_service.sh)." >&2
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl is required but was not found on PATH." >&2
  exit 1
fi

SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"

echo ">> Stopping $SERVICE_NAME (if running)"
if systemctl list-unit-files | grep -q "^$SERVICE_NAME"; then
  systemctl stop "$SERVICE_NAME" || true
  systemctl disable "$SERVICE_NAME" || true
fi

if [[ -f "$SERVICE_FILE" ]]; then
  echo ">> Removing $SERVICE_FILE"
  rm -f "$SERVICE_FILE"
else
  echo ">> Service file $SERVICE_FILE not found; skipping removal"
fi

systemctl daemon-reload
systemctl reset-failed "$SERVICE_NAME" || true

echo "Service $SERVICE_NAME removed."
