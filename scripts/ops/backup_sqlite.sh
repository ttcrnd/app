#!/usr/bin/env bash
# Backup SQLite review DB (+ optional artifacts snapshot).
# Usage: ./scripts/backup_sqlite.sh [DEST_DIR]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="${1:-$ROOT/data/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$DEST"

DB_PATH="${REVIEW_SQLITE_PATH:-$ROOT/data/review.db}"
if [[ ! -f "$DB_PATH" ]]; then
  # Resolve relative sqlite URL style paths
  if [[ -f "$ROOT/data/review.db" ]]; then
    DB_PATH="$ROOT/data/review.db"
  else
    echo "SQLite DB not found at $DB_PATH" >&2
    exit 1
  fi
fi

OUT="$DEST/review-$STAMP.db"
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB_PATH" ".backup '$OUT'"
else
  cp -a "$DB_PATH" "$OUT"
fi

# Keep WAL companions if present (copy mode)
for side in "-wal" "-shm"; do
  if [[ -f "${DB_PATH}${side}" ]]; then
    cp -a "${DB_PATH}${side}" "${OUT}${side}" || true
  fi
done

echo "Backup written: $OUT"

# Optional prune: keep last 14 backups
ls -1t "$DEST"/review-*.db 2>/dev/null | tail -n +15 | while read -r old; do
  rm -f "$old" "${old}-wal" "${old}-shm"
done
