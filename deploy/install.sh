#!/usr/bin/env bash
# Install the daily visitor report on the web server (run as root on the VPS).
#
#   TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... ./install.sh
#
# Idempotent: safe to re-run after editing visitor_report.py.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR=/opt/visitor-report
ENV_FILE=/etc/visitor-report.env
LOG=/var/log/caddy/access.log

[ "$(id -u)" -eq 0 ] || { echo "must run as root" >&2; exit 1; }

echo "==> installing module to $APP_DIR"
install -d -m 755 "$APP_DIR"
install -m 750 "$SRC_DIR/../modules/visitor_report.py" "$APP_DIR/visitor_report.py"

echo "==> writing $ENV_FILE"
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
  umask 077
  cat > "$ENV_FILE" <<EOF
TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID
EOF
  chmod 600 "$ENV_FILE"
  echo "    credentials written (mode 600)"
elif [ -f "$ENV_FILE" ]; then
  echo "    keeping existing $ENV_FILE"
else
  echo "ERROR: $ENV_FILE missing and no TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID given" >&2
  exit 1
fi

echo "==> checking Caddy access log"
if [ ! -s "$LOG" ]; then
  echo "    WARNING: $LOG is empty or missing - is the 'log' block active in the Caddyfile?"
else
  echo "    $(wc -l < "$LOG") lines present"
fi

echo "==> installing systemd units"
install -m 644 "$SRC_DIR/visitor-report.service" /etc/systemd/system/
install -m 644 "$SRC_DIR/visitor-report.timer"   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now visitor-report.timer

echo "==> next run"
systemctl list-timers visitor-report.timer --no-pager

echo
echo "Done. Send a report right now with:"
echo "  systemctl start visitor-report.service && journalctl -u visitor-report -n 20 --no-pager"
