#!/usr/bin/env sh
set -eu

if [ "$#" -ne 2 ] || [ "$2" != "--confirm" ]; then
  printf 'Usage: %s BACKUP.zip --confirm\n' "$0" >&2
  printf '%s\n' 'Stop Gravity Fitness before restoring the live database.' >&2
  exit 2
fi
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON_BIN=${GRAVITY_PYTHON:-"$PROJECT_ROOT/.venv/bin/python"}
if [ ! -x "$PYTHON_BIN" ]; then
  printf '%s\n' 'Gravity Python environment is missing.' >&2
  exit 1
fi
cd "$PROJECT_ROOT"
exec "$PYTHON_BIN" -m server.gravity --restore-backup "$1" --confirm-live-restore
