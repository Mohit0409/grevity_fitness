#!/usr/bin/env sh
set -eu

. "$(dirname -- "$0")/gravity-common.sh"
gravity_init
pid=$(gravity_pid 2>/dev/null || true)
if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
  printf '%s\n' 'Gravity Fitness is stopped.'
  exit 1
fi
if ! gravity_managed_pid "$pid"; then
  printf 'PID %s is live but is not provably owned by this Gravity checkout.\n' "$pid" >&2
  exit 2
fi
if ! gravity_healthy; then
  printf 'Gravity Fitness PID %s is running but unhealthy.\n' "$pid" >&2
  exit 2
fi
printf 'Gravity Fitness is healthy (PID %s) at %s.\n' "$pid" "$GRAVITY_HEALTH_URL"
