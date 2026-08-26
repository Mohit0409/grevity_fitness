#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PID_FILE=${GRAVITY_RUNTIME_DIR:-"$PROJECT_ROOT/.gravity"}/gravity.pid
if [ ! -f "$PID_FILE" ]; then
  printf '%s\n' 'Gravity Fitness is already stopped.'
  exit 0
fi

SERVER_PID=$(cat "$PID_FILE")
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
  rm -f "$PID_FILE"
  printf '%s\n' 'Removed a stale Gravity PID file.'
  exit 0
fi
case "$(ps -p "$SERVER_PID" -o args= 2>/dev/null || true)" in
  *server.gravity*) ;;
  *) printf 'Refusing to stop PID %s because it is not the Gravity server.\n' "$SERVER_PID" >&2; exit 1 ;;
esac
kill "$SERVER_PID"
attempt=0
while kill -0 "$SERVER_PID" 2>/dev/null && [ "$attempt" -lt 20 ]; do
  attempt=$((attempt + 1))
  sleep 1
done
if kill -0 "$SERVER_PID" 2>/dev/null; then
  printf 'Gravity Fitness PID %s did not stop cleanly.\n' "$SERVER_PID" >&2
  exit 1
fi
rm -f "$PID_FILE"
printf '%s\n' 'Gravity Fitness stopped.'
