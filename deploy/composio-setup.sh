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

# A key file wins over the prompt: pasting a long key into a hidden prompt is
# error-prone, and nano handles it reliably.
KEY_FILE="${KEY_FILE:-$HOME/.composio-key}"
if [[ -s "$KEY_FILE" ]]; then
  COMPOSIO_API_KEY="$(cat "$KEY_FILE")"
  echo "using the key in $KEY_FILE"
else
  read -rsp "Composio API key: " COMPOSIO_API_KEY; echo
fi
# A pasted key often carries a trailing newline or space, which the API then
# rejects as invalid - indistinguishable from a wrong key in the 401.
COMPOSIO_API_KEY="${COMPOSIO_API_KEY//[[:space:]]/}"
[[ -n "$COMPOSIO_API_KEY" ]] || { echo "nothing entered, aborting" >&2; exit 1; }

# Echo only what the API itself echoes back in errors, so you can compare it
# with the dashboard without exposing the key.
printf 'read %d characters: %s…%s\n' "${#COMPOSIO_API_KEY}" \
  "${COMPOSIO_API_KEY:0:3}" "${COMPOSIO_API_KEY: -4}"
# Prefix, not length, tells you whether this is the right kind of key:
#   ak_  project API key  <- the v3 API and the SDK want this one
#   oak_ / uak_           organisation / user keys
#   ck_  consumer key from the Connect & Sessions pages, which every v3
#        endpoint rejects as "Invalid API key" no matter the header used.
# An ak_ key is also 23 characters, so length proves nothing.
case "$COMPOSIO_API_KEY" in
  ak_*|oak_*|uak_*) ;;
  ck_*) echo "warning: ck_ is a consumer key from Connect/Sessions, not a" >&2
        echo "         project API key. Settings -> API Keys gives an ak_ one." >&2 ;;
  *)    echo "warning: unrecognised key prefix; expected ak_" >&2 ;;
esac

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
