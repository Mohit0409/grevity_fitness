#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
umask 077

INSTALL_PACKAGES=false
ENABLE_TUNNEL=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --install-packages) INSTALL_PACKAGES=true ;;
    --enable-tunnel) ENABLE_TUNNEL=true ;;
    *) echo "usage: install-termux.sh [--install-packages] [--enable-tunnel]" >&2; exit 2 ;;
  esac
  shift
done

case "${PREFIX:-}" in
  /data/data/com.termux/files/usr) ;;
  *) echo 'This installer must run inside the official Termux environment.' >&2; exit 1 ;;
esac

REPO="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
CONFIG_DIR="$HOME/.config/gravity"
CONFIG="$CONFIG_DIR/gravity.env"
STATE="$HOME/.local/state/gravity"
DATA="$HOME/.local/share/gravity"
SERVICE_ROOT="$PREFIX/var/service"

if $INSTALL_PACKAGES; then
  pkg update
  pkg install -y python git termux-services curl rclone cloudflared
fi
for command in python3 git curl sv svlogd; do
  command -v "$command" >/dev/null 2>&1 || { echo "Missing command: $command" >&2; exit 1; }
done

mkdir -p "$CONFIG_DIR" "$STATE/logs" "$DATA/data" "$DATA/backups" "$HOME/.termux/boot" "$SERVICE_ROOT"
chmod 700 "$CONFIG_DIR" "$STATE" "$STATE/logs" "$DATA" "$DATA/data" "$DATA/backups"
printf '%s\n' "$REPO" > "$CONFIG_DIR/repository"
chmod 600 "$CONFIG_DIR/repository"
CREATED_CONFIG=false
if [ ! -e "$CONFIG" ]; then
  cp "$REPO/deploy/termux/gravity.env.example" "$CONFIG"
  chmod 600 "$CONFIG"
  CREATED_CONFIG=true
  echo "Created $CONFIG; fill verified values before starting Gravity."
else
  chmod 600 "$CONFIG"
fi

if $CREATED_CONFIG; then
  echo 'Installation paused before enabling services. Complete the private config and rerun this command.'
  exit 2
fi

python3 "$REPO/scripts/gravity-env.py" --config "$CONFIG" -- python3 -c '
import os
from urllib.parse import urlparse
if os.environ.get("GRAVITY_HOST", "127.0.0.1") != "127.0.0.1":
    raise SystemExit("GRAVITY_HOST must be 127.0.0.1")
if urlparse(os.environ.get("APP_BASE_URL", "")).scheme != "https":
    raise SystemExit("APP_BASE_URL must be the stable HTTPS production URL")
if len(os.environ.get("SECRET_KEY", "")) < 32:
    raise SystemExit("SECRET_KEY must contain at least 32 characters")
'
PYTHON="$(python3 "$REPO/scripts/gravity-env.py" --config "$CONFIG" --print GRAVITY_PYTHON)"
PYTHON="${PYTHON:-$REPO/.venv/bin/python}"
[ -x "$PYTHON" ] || { echo "Gravity Python is missing: $PYTHON; run scripts/setup-gravity.sh first." >&2; exit 1; }

install_service() {
  name=$1
  source=$2
  target="$SERVICE_ROOT/$name"
  if [ -e "$target" ] && [ ! -f "$target/.gravity-managed" ]; then
    echo "Refusing to replace existing service: $target" >&2
    exit 1
  fi
  mkdir -p "$target/log"
  cp "$source/run" "$target/run"
  cp "$source/log/run" "$target/log/run"
  chmod 700 "$target/run" "$target/log/run"
  touch "$target/.gravity-managed"
}
install_service gravity "$REPO/deploy/termux/services/gravity"
install_service gravity-health "$REPO/deploy/termux/services/gravity-health"
install_service gravity-tunnel "$REPO/deploy/termux/services/gravity-tunnel"
ln -sfn "$REPO/deploy/termux/termux-boot-gravity.sh" "$HOME/.termux/boot/gravity-fitness"

source "$PREFIX/etc/profile.d/start-services.sh"
sv-enable gravity
sv-enable gravity-health
if $ENABLE_TUNNEL; then
  command -v cloudflared >/dev/null 2>&1 || { echo 'cloudflared is required for --enable-tunnel.' >&2; exit 1; }
  cloudflared_version="$(cloudflared --version 2>&1 | sed -n 's/^cloudflared version \([0-9][0-9.]*\).*/\1/p')"
  [ -n "$cloudflared_version" ] || { echo 'Could not identify the cloudflared version.' >&2; exit 1; }
  oldest="$(printf '%s\n%s\n' '2025.4.0' "$cloudflared_version" | sort -V | head -n 1)"
  [ "$oldest" = '2025.4.0' ] || { echo 'cloudflared 2025.4.0+ is required for --token-file.' >&2; exit 1; }
  [ -s "$CONFIG_DIR/cloudflared-token" ] || { echo 'Create the mode-600 Cloudflare token file before --enable-tunnel.' >&2; exit 1; }
  touch "$CONFIG_DIR/enable-tunnel"
  chmod 600 "$CONFIG_DIR/enable-tunnel" "$CONFIG_DIR/cloudflared-token"
  sv-enable gravity-tunnel
else
  sv-disable gravity-tunnel >/dev/null 2>&1 || true
fi

echo 'Termux services installed. Complete gravity.env, then run:'
echo '  sv up gravity gravity-health'
echo '  deploy/termux/network-audit.sh'
echo 'Enable the tunnel only after loopback health and the Cloudflare ingress are verified.'
