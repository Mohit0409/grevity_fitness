#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON_BIN=${GRAVITY_PYTHON:-"$PROJECT_ROOT/.venv/bin/python"}
if [ ! -x "$PYTHON_BIN" ]; then
  printf '%s\n' 'Gravity Python environment is missing. Create .venv with Python 3.11+ first.' >&2
  exit 1
fi
cd "$PROJECT_ROOT"
exec "$PYTHON_BIN" -m server.gravity --provider-canaries
