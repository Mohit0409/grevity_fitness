#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RUNTIME_DIR=${GRAVITY_RUNTIME_DIR:-"$PROJECT_ROOT/.gravity"}
PID_FILE="$RUNTIME_DIR/gravity.pid"
PYTHON_BIN=${GRAVITY_PYTHON:-"$PROJECT_ROOT/.venv/bin/python"}

mkdir -p "$RUNTIME_DIR"
if [ ! -x "$PYTHON_BIN" ]; then
  printf '%s\n' 'Gravity Python environment is missing. Create .venv with Python 3.11+ first.' >&2
  exit 1
fi
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  printf 'Gravity Fitness is already running with PID %s.\n' "$(cat "$PID_FILE")" >&2
  exit 1
fi

cd "$PROJECT_ROOT"
nohup "$PYTHON_BIN" -m server.gravity >>"$RUNTIME_DIR/gravity.stdout.log" 2>>"$RUNTIME_DIR/gravity.stderr.log" &
SERVER_PID=$!
printf '%s\n' "$SERVER_PID" >"$PID_FILE"
sleep 1
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
  printf '%s\n' 'Gravity Fitness exited during startup. Check .gravity/gravity.stderr.log.' >&2
  exit 1
fi
printf 'Gravity Fitness started with PID %s.\n' "$SERVER_PID"
