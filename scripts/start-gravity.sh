#!/usr/bin/env sh
set -eu

. "$(dirname -- "$0")/gravity-common.sh"
gravity_init
mkdir -p "$GRAVITY_RUNTIME"
chmod 700 "$GRAVITY_RUNTIME" 2>/dev/null || true
[ -x "$GRAVITY_PYTHON_BIN" ] || { printf 'Gravity Python environment is missing: %s\n' "$GRAVITY_PYTHON_BIN" >&2; exit 1; }

pid=$(gravity_pid 2>/dev/null || true)
if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
  gravity_managed_pid "$pid" || { printf 'Refusing to replace untrusted live PID %s.\n' "$pid" >&2; exit 1; }
  if gravity_healthy; then
    printf 'Gravity Fitness is already healthy with PID %s.\n' "$pid"
    exit 0
  fi
  printf 'Gravity PID %s is running but unhealthy. Use restart-gravity.sh.\n' "$pid" >&2
  exit 1
fi
gravity_remove_stale_state

stdout_log="$GRAVITY_RUNTIME/gravity.stdout.log"
stderr_log="$GRAVITY_RUNTIME/gravity.stderr.log"
gravity_rotate_log "$stdout_log"
gravity_rotate_log "$stderr_log"
cd "$GRAVITY_PROJECT_ROOT"
if [ -n "$GRAVITY_CONFIG_ARGUMENTS" ]; then
  nohup python3 "$GRAVITY_PROJECT_ROOT/scripts/gravity-env.py" --config "$GRAVITY_CONFIG_FILE" -- \
    "$GRAVITY_PYTHON_BIN" -m server.gravity --host 127.0.0.1 --port "$GRAVITY_MANAGED_PORT" \
    >>"$stdout_log" 2>>"$stderr_log" &
else
  nohup "$GRAVITY_PYTHON_BIN" -m server.gravity --host 127.0.0.1 --port "$GRAVITY_MANAGED_PORT" \
    >>"$stdout_log" 2>>"$stderr_log" &
fi
started_pid=$!

attempt=0
while [ "$attempt" -lt 40 ]; do
  if ! kill -0 "$started_pid" 2>/dev/null; then
    gravity_remove_stale_state
    printf 'Gravity Fitness exited during startup. Check %s.\n' "$stderr_log" >&2
    exit 1
  fi
  pid=$(gravity_pid 2>/dev/null || true)
  if [ "$pid" = "$started_pid" ] && gravity_managed_pid "$pid" && gravity_healthy; then
    printf 'Gravity Fitness started with PID %s.\n' "$pid"
    printf 'Local health: %s\n' "$GRAVITY_HEALTH_URL"
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 1
done
if gravity_managed_pid "$started_pid"; then kill "$started_pid" 2>/dev/null || true; fi
gravity_remove_stale_state
printf 'Gravity Fitness did not become healthy on loopback. Check %s.\n' "$stderr_log" >&2
exit 1
