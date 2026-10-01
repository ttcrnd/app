#!/usr/bin/env bash
# Install the review FastAPI server as a systemd service on Debian/Ubuntu.
# Usage: sudo ./install_service.sh [SERVICE_USER=custom] [REVIEW_SERVICE_PORT=9000]
set -euo pipefail

SERVICE_NAME="${REVIEW_SERVICE_NAME:-security-review.service}"
SERVICE_HOST="${REVIEW_SERVICE_HOST:-0.0.0.0}"
SERVICE_PORT="${REVIEW_SERVICE_PORT:-18765}"

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (tip: sudo ./install_service.sh)." >&2
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl is required but was not found on PATH." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
SETUP_SCRIPT="$PROJECT_ROOT/setup.sh"
VENV_DIR="$PROJECT_ROOT/.venv"

if [[ ! -f "$SETUP_SCRIPT" ]]; then
  echo "Cannot find setup.sh in $PROJECT_ROOT." >&2
  exit 1
fi

detect_service_user() {
  if [[ -n "${SERVICE_USER:-}" ]]; then
    TARGET_USER="$SERVICE_USER"
    return
  fi
  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER:-}" != "root" ]]; then
    TARGET_USER="$SUDO_USER"
    return
  fi
  OWNER="$(stat -c '%U' "$PROJECT_ROOT" 2>/dev/null || true)"
  if [[ -n "$OWNER" && "$OWNER" != "root" ]]; then
    TARGET_USER="$OWNER"
    return
  fi
  TARGET_USER="root"
  echo "SERVICE_USER not provided; defaulting to root." >&2
}

detect_service_user
SERVICE_USER="$TARGET_USER"

if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  echo "User '$SERVICE_USER' does not exist. Create it first or set SERVICE_USER." >&2
  exit 1
fi

SERVICE_GROUP="$(id -gn "$SERVICE_USER")"

echo ">> Ensuring virtual environment is ready (this may take a moment) ..."
runuser -u "$SERVICE_USER" -- bash -lc "cd '$PROJECT_ROOT' && ./setup.sh"

SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME"
echo ">> Writing systemd unit to $SERVICE_FILE"

cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Review pipeline FastAPI server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_ROOT
User=$SERVICE_USER
Group=$SERVICE_GROUP
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-$PROJECT_ROOT/.env
ExecStart=$VENV_DIR/bin/python -m uvicorn server:app --host $SERVICE_HOST --port $SERVICE_PORT
Restart=on-failure
RestartSec=5
TimeoutStartSec=30

[Install]
WantedBy=multi-user.target
EOF

chmod 644 "$SERVICE_FILE"

echo ">> Reloading systemd daemon"
systemctl daemon-reload

echo ">> Enabling and starting $SERVICE_NAME"
systemctl enable --now "$SERVICE_NAME"

echo "Service installed."
echo "Status:"
systemctl --no-pager status "$SERVICE_NAME"

echo
echo "Next steps:"
echo "  • Place your GitHub token into $PROJECT_ROOT/.env (GITHUB_TOKEN=...)."
echo "  • The API/UI listens on http://$SERVICE_HOST:$SERVICE_PORT/."
echo "  • Manage the service with: sudo systemctl [status|restart|stop] $SERVICE_NAME"
