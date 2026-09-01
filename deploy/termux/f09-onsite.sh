#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
umask 077

MODE="${1:-status}"
CONFIG="${GRAVITY_ENV_FILE:-$HOME/.config/gravity/gravity.env}"
REPO="$(cat "$HOME/.config/gravity/repository")"
PYTHON="${GRAVITY_PYTHON:-$REPO/.venv/bin/python}"
APPROVAL="$HOME/.config/gravity/f09-approval.json"
REQUIREMENTS="$REPO/scripts/requirements-biometric-driver.txt"
RUNNER="$REPO/deploy/termux/f09-onsite.py"

[ -x "$PYTHON" ] || { echo "Gravity Python missing: $PYTHON" >&2; exit 1; }
[ -f "$RUNNER" ] || { echo "F09 tablet runner missing: $RUNNER" >&2; exit 1; }

case "$MODE" in
  prepare)
    "$PYTHON" -m pip install --disable-pip-version-check --require-hashes -r "$REQUIREMENTS"
    "$PYTHON" -c 'from zk import ZK; print("f09Driver=ready")'
    echo 'F09 driver prepared locally. No fingerprint machine was contacted.'
    ;;
  status|preflight)
    exec "$PYTHON" "$RUNNER" preflight --config "$CONFIG" --approval-file "$APPROVAL"
    ;;
  configure)
    [ -f "$APPROVAL" ] || {
      echo 'Explicit owner approval is required before F09 configuration.' >&2
      echo 'Do not create the approval file merely because the tablet joined gym Wi-Fi.' >&2
      exit 2
    }
    echo 'Creating a verified Gravity backup before the one-shot F09 integration...'
    GRAVITY_ENV_FILE="$CONFIG" "$REPO/scripts/backup-gravity.sh" f09-preconfigure >/dev/null
    exec "$PYTHON" "$RUNNER" configure --config "$CONFIG" --approval-file "$APPROVAL"
    ;;
  *)
    echo "Usage: $0 {prepare|status|configure}" >&2
    echo 'prepare: install local pinned driver only; contacts no device' >&2
    echo 'status: read-only host readiness; contacts no F09' >&2
    echo 'configure: requires short-lived explicit owner approval' >&2
    exit 2
    ;;
esac
