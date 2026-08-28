#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/gravity-common.sh"
gravity_init
gravity_capture "$GRAVITY_PYTHON_BIN" "$GRAVITY_PROJECT_ROOT/scripts/run-notifications.py" \
  --root "$GRAVITY_PROJECT_ROOT" \
  --runtime-dir "$GRAVITY_RUNTIME" \
  --python "$GRAVITY_PYTHON_BIN" \
  --status
