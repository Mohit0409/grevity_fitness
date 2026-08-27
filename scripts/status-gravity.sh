#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RUNTIME_DIR=${GRAVITY_RUNTIME_DIR:-"$PROJECT_ROOT/.gravity"}
PID_FILE="$RUNTIME_DIR/gravity.pid"
PYTHON_BIN=${GRAVITY_PYTHON:-"$PROJECT_ROOT/.venv/bin/python"}
if [ ! -f "$PID_FILE" ] || ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  printf '%s\n' 'Gravity Fitness is stopped.'
  exit 1
fi
if [ ! -x "$PYTHON_BIN" ]; then
  printf '%s\n' 'Gravity Python environment is missing.' >&2
  exit 2
fi
cd "$PROJECT_ROOT"
BASE_URL=$($PYTHON_BIN -c 'from server.gravity.config import Settings; print(Settings.load().app_base_url)')
"$PYTHON_BIN" -c 'import json,sys,urllib.request; d=json.load(urllib.request.urlopen(sys.argv[1]+"/api/health",timeout=3)); print(json.dumps(d,separators=(",",":"))); raise SystemExit(0 if d.get("status")=="ok" and d.get("database")=="ok" else 2)' "$BASE_URL"
printf 'Gravity Fitness is running with PID %s.\n' "$(cat "$PID_FILE")"
