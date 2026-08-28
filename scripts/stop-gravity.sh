#!/usr/bin/env sh
set -eu

. "$(dirname -- "$0")/gravity-common.sh"
gravity_init
pid=$(gravity_pid 2>/dev/null || true)
if [ -z "$pid" ]; then
  gravity_remove_stale_state
  printf '%s\n' 'Gravity Fitness is already stopped.'
  exit 0
fi
if ! kill -0 "$pid" 2>/dev/null; then
  gravity_remove_stale_state
  printf '%s\n' 'Removed stale Gravity runtime state.'
  exit 0
fi
gravity_managed_pid "$pid" || { printf 'Refusing to stop untrusted live PID %s.\n' "$pid" >&2; exit 1; }
kill "$pid"
attempt=0
while kill -0 "$pid" 2>/dev/null && [ "$attempt" -lt 15 ]; do
  attempt=$((attempt + 1))
  sleep 1
done
if kill -0 "$pid" 2>/dev/null; then
  printf 'Gravity Fitness PID %s did not stop within 15 seconds.\n' "$pid" >&2
  exit 1
fi
gravity_remove_stale_state
printf '%s\n' 'Gravity Fitness stopped.'
