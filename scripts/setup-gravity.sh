#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
GRAVITY_PYTHON_BIN=${GRAVITY_PYTHON:-python3}

"$GRAVITY_PYTHON_BIN" -m venv "$PROJECT_ROOT/.venv"
"$PROJECT_ROOT/.venv/bin/python" -m pip install --disable-pip-version-check -e "$PROJECT_ROOT[firebase]"
"$PROJECT_ROOT/.venv/bin/python" -m server.gravity --root "$PROJECT_ROOT" --check-db

echo "Gravity Fitness setup is ready."
echo "Start with: ./scripts/start-gravity.sh"
