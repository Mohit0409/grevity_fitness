#!/data/data/com.termux/files/usr/bin/bash
set -u
LOG="$HOME/.local/state/gravity/logs/boot.log"
mkdir -p "$(dirname "$LOG")"
exec >> "$LOG" 2>&1
echo "$(date -Iseconds) Gravity boot recovery requested"
termux-wake-lock || true
source "$PREFIX/etc/profile.d/start-services.sh"
sv up gravity gravity-health gravity-notifications || true
if [ -f "$HOME/.config/gravity/enable-tunnel" ]; then
  sv up gravity-tunnel || true
fi
echo "$(date -Iseconds) Gravity boot recovery completed"
