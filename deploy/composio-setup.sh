#!/usr/bin/env bash
#
# Wire Composio into both places it can be useful on this box:
#
#   1. the assistant, so the morning briefing reads Gmail through Composio's
#      OAuth grant instead of a token.json generated on a laptop
#   2. Claude Code on the server, so an interactive session (deploy/brain.sh)
#      can use your connected apps
#
# Run it as the agent user:  bash deploy/composio-setup.sh
#
# It asks for your API key and never echoes it. Get one from
# https://platform.composio.dev  ->  API Keys.

set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-/opt/ai-assistant/.env}"
VENV_PY="${VENV_PY:-/opt/ai-assistant/.venv/bin/python}"

read -rsp "Composio API key: " COMPOSIO_API_KEY; echo
[[ -n "$COMPOSIO_API_KEY" ]] || { echo "nothing entered, aborting" >&2; exit 1; }

# ── 1. the assistant ────────────────────────────────────────────────────────
say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

say "Checking the key and listing connected Gmail accounts"
"$VENV_PY" - "$COMPOSIO_API_KEY" <<'PY'
import sys
from composio import Composio
client = Composio(api_key=sys.argv[1])
accounts = client.connected_accounts.list()
items = getattr(accounts, "items", None) or getattr(accounts, "data", None) or []
print("connected accounts:")
for a in items:
    toolkit = getattr(getattr(a, "toolkit", None), "slug", None) or "?"
    print(f"  {getattr(a, 'id', '?'):24} {toolkit:12} {getattr(a, 'status', '?')}")
PY

say "Writing COMPOSIO_API_KEY into $ENV_FILE"
if grep -q '^COMPOSIO_API_KEY=' "$ENV_FILE"; then
  sed -i "s|^COMPOSIO_API_KEY=.*|COMPOSIO_API_KEY=$COMPOSIO_API_KEY|" "$ENV_FILE"
else
  printf '\n# Composio: Gmail for the briefing, without a laptop-generated token.\nCOMPOSIO_API_KEY=%s\n#COMPOSIO_GMAIL_ACCOUNT_ID=\n#COMPOSIO_USER_ID=default\n' "$COMPOSIO_API_KEY" >> "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"
echo "written (the assistant needs a restart to pick it up)"

# ── 2. Claude Code on this box ──────────────────────────────────────────────
say "Creating a tool-router session for the MCP endpoint"
MCP_URL="$("$VENV_PY" - "$COMPOSIO_API_KEY" <<'PY'
import sys
from composio import Composio
client = Composio(api_key=sys.argv[1])
session = client.sessions.create()
url = None
for path in (("mcp", "url"), ("mcp_url",), ("url",)):
    obj = session
    for part in path:
        obj = getattr(obj, part, None)
        if obj is None:
            break
    if isinstance(obj, str):
        url = obj
        break
print(url or "", end="")
PY
)"

if [[ -z "$MCP_URL" ]]; then
  echo "Could not read an MCP URL from the session object." >&2
  echo "Get it from https://platform.composio.dev -> MCP, then run:" >&2
  echo "  claude mcp add --scope user --transport http composio <URL> -H \"X-API-Key: <key>\"" >&2
  exit 1
fi

say "Registering it with Claude Code"
export PATH="$HOME/.local/bin:$PATH"
claude mcp remove composio --scope user >/dev/null 2>&1 || true
claude mcp add --scope user --transport http composio "$MCP_URL" -H "X-API-Key: $COMPOSIO_API_KEY"
claude mcp list 2>&1 | grep -i composio || true

say "Done"
cat <<'NEXT'
Next:
  sudo systemctl restart assistant     # so the bot picks up the key
  claude                               # new session; the tools appear there

If several Gmail accounts are connected, set COMPOSIO_GMAIL_ACCOUNT_ID in
.env to the one the briefing should read - otherwise Composio picks the
default, which may be the wrong mailbox.
NEXT
