#!/usr/bin/env sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON_BIN=${GRAVITY_PYTHON:-"$PROJECT_ROOT/.venv/bin/python"}
if [ ! -x "$PYTHON_BIN" ]; then
  printf '%s\n' 'Gravity Python environment is missing. Run ./scripts/setup-gravity.sh first.' >&2
  exit 1
fi
cd "$PROJECT_ROOT"
if [ "$#" -gt 1 ]; then
  printf '%s\n' 'Usage: smoke-gravity.sh [base-url]' >&2
  exit 2
fi
if [ "$#" -eq 1 ]; then
  exec "$PYTHON_BIN" -m server.gravity --smoke --smoke-base-url "$1"
fi
exec "$PYTHON_BIN" -m server.gravity --smoke
