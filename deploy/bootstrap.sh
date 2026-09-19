#!/usr/bin/env bash
#
# One-time setup for the Hetzner box. Run as root:
#
#   bash deploy/bootstrap.sh
#
# Safe to run twice — every step checks before it acts. SSH hardening is opt-in
# (--harden-ssh) and refuses to run if it would lock you out.

set -euo pipefail

APP_USER="${APP_USER:-agent}"
APP_DIR="${APP_DIR:-/opt/ai-assistant}"
SWAP_SIZE="${SWAP_SIZE:-4G}"
TIMEZONE="${TIMEZONE:-Europe/Rome}"
HARDEN_SSH=0

for arg in "$@"; do
  case "$arg" in
    --harden-ssh) HARDEN_SSH=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "Run this as root: sudo bash deploy/bootstrap.sh" >&2
  exit 1
fi

say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

# ── Timezone ────────────────────────────────────────────────────────────────
# Hetzner images default to UTC. The assistant schedules jobs at 08:00 local,
# so without this the morning briefing arrives at 10:00 Italian time.
say "Timezone -> $TIMEZONE"
timedatectl set-timezone "$TIMEZONE"
timedatectl | sed -n '1,3p'

# ── Swap ────────────────────────────────────────────────────────────────────
# 4 GB of RAM with headless Chrome in it is tight. Swap is what stops the OOM
# killer picking off the bot mid-run.
say "Swap"
if swapon --show | grep -q '/swapfile'; then
  echo "swapfile already active, leaving it alone"
else
  fallocate -l "$SWAP_SIZE" /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "created ${SWAP_SIZE} swapfile"
fi
free -h

# ── Packages ────────────────────────────────────────────────────────────────
say "Base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  python3 python3-venv python3-pip \
  git curl ca-certificates gnupg tmux ufw unzip

# ── Google Chrome (for the Selenium scraper) ────────────────────────────────
# Ubuntu's chromium is a snap on recent releases, which does not play well with
# headless Selenium. The Google .deb is the boring, reliable option.
say "Google Chrome"
if command -v google-chrome >/dev/null 2>&1; then
  echo "already installed: $(google-chrome --version)"
else
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
    | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg
  echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list
  apt-get update -qq
  apt-get install -y -qq google-chrome-stable
  echo "installed: $(google-chrome --version)"
fi

# ── Node 22 (the router needs it) ───────────────────────────────────────────
say "Node.js 22"
if command -v node >/dev/null 2>&1 && [[ "$(node -v)" == v2[2-9]* ]]; then
  echo "already installed: $(node -v)"
else
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y -qq nodejs
  echo "installed: $(node -v)"
fi

# ── Service user ────────────────────────────────────────────────────────────
# Nothing here needs root. An agent with shell access on a public box should
# own exactly its own directory and nothing else.
say "Service user: $APP_USER"
if id "$APP_USER" >/dev/null 2>&1; then
  echo "user already exists"
else
  adduser --disabled-password --gecos "" "$APP_USER"
fi

install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR/data"

# ── Firewall ────────────────────────────────────────────────────────────────
# Belt and braces alongside the Hetzner Cloud Firewall. The router port is
# deliberately absent: it binds to localhost and must stay unreachable.
say "Firewall"
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status verbose

# ── SSH hardening (opt-in) ──────────────────────────────────────────────────
say "SSH hardening"
if [[ $HARDEN_SSH -eq 1 ]]; then
  KEYS_FOUND=0
  for f in /root/.ssh/authorized_keys "/home/$APP_USER/.ssh/authorized_keys"; do
    [[ -s "$f" ]] && KEYS_FOUND=1
  done

  if [[ $KEYS_FOUND -eq 0 ]]; then
    echo "REFUSING: no authorized_keys found. Disabling password login now"
    echo "would lock you out of your own server. Add your key first:"
    echo "  ssh-copy-id root@<server-ip>"
    exit 1
  fi

  cat > /etc/ssh/sshd_config.d/99-hardening.conf <<'CONF'
PasswordAuthentication no
PermitRootLogin prohibit-password
CONF
  sshd -t
  systemctl reload ssh || systemctl reload sshd
  echo "password login disabled, keys only"
else
  echo "skipped (pass --harden-ssh once your SSH key works)"
fi

say "Done"
cat <<NEXT

Next steps — see deploy/README.md for the detail:

  1. Deploy the code:
       git clone <your-repo> $APP_DIR   # as $APP_USER
  2. Create $APP_DIR/.env from .env.example (chmod 600)
  3. Copy token.json from your laptop — Gmail OAuth cannot run headless
  4. Install the services:
       cp deploy/assistant.service /etc/systemd/system/
       cp deploy/ccr.service       /etc/systemd/system/
       systemctl daemon-reload
       systemctl enable --now assistant ccr

NEXT
