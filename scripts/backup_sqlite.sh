#!/usr/bin/env bash
# Compatibility wrapper — implementation lives in scripts/ops/
exec "$(cd "$(dirname "$0")" && pwd)/ops/backup_sqlite.sh" "$@"
