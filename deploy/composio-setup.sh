#!/usr/bin/env bash
#
# Wire Composio into both places it is useful here:
#
#   1. the assistant, so the morning briefing reads Gmail through Composio's
#      OAuth grant instead of a token.json generated on a laptop
#   2. Claude Code on this box, so an interactive session can use the
#      connected apps
#
# Run as the agent user:  bash deploy/composio-setup.sh
#
# Composio has two unrelated credentials, and picking the wrong one costs an
# afternoon:
#   ak_  platform project API key -> the v3 REST API and the python SDK
#   ck_  consumer key             -> connect.composio.dev/mcp, header
#                                    x-consumer-api-key
# A ck_ key returns "Invalid API key" from every v3 endpoint no matter the
# header, which reads exactly like a wrong key. This script uses ck_, because
# that is what the Connect dashboard (For You -> Connect -> Settings ->
# Sessions & API Key) hands you.

set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-/opt/ai-assistant/.env}"
MCP_URL="${MCP_URL:-https://connect.composio.dev/mcp}"
KEY_FILE="${KEY_FILE:-$HOME/.composio-key}"

if [[ -s "$KEY_FILE" ]]; then
  KEY="$(tr -d '[:space:]' < "$KEY_FILE")"
  echo "using the key in $KEY_FILE"
else
  read -rsp "Composio consumer key (ck_...): " KEY; echo
  KEY="${KEY//[[:space:]]/}"
fi
[[ -n "$KEY" ]] || { echo "nothing entered, aborting" >&2; exit 1; }
case "$KEY" in
  ck_*) ;;
  ak_*|oak_*|uak_*) echo "that is a platform key; this script wants the ck_ consumer key" >&2; exit 1 ;;
  *) echo "unrecognised key prefix; expected ck_" >&2; exit 1 ;;
esac

say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

say "Checking the key against $MCP_URL"
code=$(curl -s -m 30 -o /tmp/composio-probe.$$ -w '%{http_code}' -X POST "$MCP_URL" \
  -H "x-consumer-api-key: $KEY" -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"setup","version":"1"}}}')
rm -f /tmp/composio-probe.$$
[[ "$code" == "200" ]] || { echo "endpoint returned $code, not 200 - key rejected" >&2; exit 1; }
echo "authenticated"

say "Writing the key into $ENV_FILE"
python3 - "$KEY" "$ENV_FILE" <<'PY'
import pathlib, re, sys
key, path = sys.argv[1], pathlib.Path(sys.argv[2])
s = re.sub(r"(?m)^COMPOSIO_[A-Z_]*=.*$\n?", "", path.read_text())
path.write_text(s.rstrip() + "\n"
    "\n# Composio: Gmail for the briefing, over its MCP endpoint.\n"
    f"COMPOSIO_CONSUMER_KEY={key}\n"
    "# Which mailbox to read when several are connected (alias or account id).\n"
    "COMPOSIO_GMAIL_ACCOUNT=\n")
path.chmod(0o600)
PY
echo "written - set COMPOSIO_GMAIL_ACCOUNT if more than one mailbox is connected"

say "Registering the endpoint with Claude Code"
export PATH="$HOME/.local/bin:$PATH"
claude mcp remove composio --scope user >/dev/null 2>&1 || true
claude mcp add --scope user --transport http composio "$MCP_URL" -H "x-consumer-api-key: $KEY"

say "Done - restart the assistant to pick up the key"
echo "  sudo systemctl restart assistant"
