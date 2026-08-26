#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PID_FILE=${GRAVITY_RUNTIME_DIR:-"$PROJECT_ROOT/.gravity"}/gravity.pid
if [ ! -f "$PID_FILE" ] || ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  printf '%s\n' 'Gravity Fitness is stopped.'
  exit 1
fi
curl --fail --silent --show-error "${APP_BASE_URL:-http://127.0.0.1:8787}/api/health"
printf '\nGravity Fitness is running with PID %s.\n' "$(cat "$PID_FILE")"
