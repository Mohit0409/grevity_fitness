#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/gravity-common.sh"
gravity_init
gravity_capture "$GRAVITY_PYTHON_BIN" "$GRAVITY_PROJECT_ROOT/scripts/admin-health-check.py" \
  --root "$GRAVITY_PROJECT_ROOT" \
  --runtime-dir "$GRAVITY_RUNTIME" \
  --base-url "http://127.0.0.1:$GRAVITY_MANAGED_PORT" \
  --scheduler-max-age-minutes "${GRAVITY_SCHEDULER_MAX_AGE_MINUTES:-90}"
