# Running the assistant on the server

Moves the assistant off your laptop and onto the Hetzner box, so the 08:00
briefing arrives whether or not your PC is awake.

Target: `ubuntu-4gb-hel1-1` — 2 vCPU, 4 GB RAM, 80 GB disk, Helsinki.

---

## The two tiers

| Tier | Model | Runs | Used for |
|---|---|---|---|
| **Volume** | Groq / Gemini (free) | Unattended, 24/7, on the server | Summarising, classifying, drafting — everything high-volume |
| **Brain** | Claude Opus (your subscription) | Interactive, when you SSH in | Judgement calls, building, anything that has to be right |

Two ways to connect them:

1. **Through 9router** — it puts the subscription at the top of a
   subscription → cheap → free chain and drops down a tier when quota runs
   out. Best for *coding* work, where you want the brain first and a cheaper
   model rather than a dead end. See the 9router section below.
2. **Through the escalation queue** — for the Python app's own unattended
   jobs. A timer runs at 03:00 with nobody watching, so the cheap tier does
   the work and writes anything it can't judge to a queue you drain later
   with `./deploy/brain.sh`.

Use both. The router handles interactive coding; the queue handles the
unattended jobs, where an escalation has to wait for a human anyway.

The volume tier falls through providers on rate limits (`groq` → `gemini` →
`groq-small`), the same way the router does for Claude Code. One capped free
tier doesn't end the night's run.

---

## Install

### 1. Bootstrap the box

As root:

```bash
git clone -b <branch> <your-repo> /tmp/setup && cd /tmp/setup
bash deploy/bootstrap.sh
```

Sets the timezone to `Europe/Rome`, adds 4 GB swap, installs Python, Node 22
and Google Chrome, creates the `agent` user, and gives that user root's
`authorized_keys` so `ssh agent@` and the `scp` in step 4 work.

Safe to run twice.

**Firewall:** the script installs and enables `ufw` *only* on a host that
isn't already running `iptables-persistent`. On this box it is, because a
saved `DOCKER-USER` rule is what keeps the browserless container (port 3000,
no auth) off the internet — and installing `ufw` makes apt remove
`iptables-persistent`, which would drop that rule at the next reboot. `ufw`
cannot filter Docker-published ports anyway. Check before and after any
firewall change:

```bash
iptables -S DOCKER-USER
```

**SSH hardening is opt-in** (`--harden-ssh`) and already in effect on this
box: `PasswordAuthentication no`, `PermitRootLogin prohibit-password`. The
script refuses if it can't find an `authorized_keys`, so it won't lock you out.

### 2. Deploy the code

`bootstrap.sh` creates `/opt/ai-assistant` (and `data/` inside it), so a plain
`git clone` into that path fails with "destination path already exists". Point
an empty repo at the remote instead:

```bash
sudo -u agent -i
cd /opt/ai-assistant
git init -b <branch>
git remote add origin <your-repo>
git fetch origin <branch>
git checkout -B <branch> --track origin/<branch>

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`requirements.txt` is the Linux set. `requirements-windows.txt` adds the
janitor's Windows-only packages — don't install it here.

### 3. Secrets

```bash
cp .env.example .env
nano .env
chmod 600 .env
```

Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `VOLUME_API_KEY` (issued by
the 9router dashboard, see below). `VOLUME_BASE_URL`, `VOLUME_MODEL` and
`CHROME_BINARY` already have working values.

**Provider keys do not go here.** Groq, Gemini, the cheap tiers and both
subscriptions are connected once, in the 9router dashboard. The app only
holds the router's address and one router API key.

`UNIPV_USERNAME` / `UNIPV_PASSWORD` are commented out on purpose: the Kiro
scraper stays dormant — and Chrome never starts — until both are set. Set
them and restart the service to switch it on.

The router's own secrets live in `/etc/9router.env` (root-owned, 0600), not
in this file: `EnvironmentFile=` hands over the whole file, and the router has
no business holding your Telegram token or portal password.

> systemd parses `.env` itself — plain `KEY=value`, no `export`, no quotes
> around values, no `${VAR}` expansion.

### 4. Gmail — the step that silently blocks everything

`email_reader.py` calls `flow.run_local_server()`, which opens a browser.
There isn't one on the server, so authenticate **on your laptop** and copy the
result over:

```bash
# on your PC, in the project folder
python -c "from modules.email_reader import authenticate_gmail; authenticate_gmail()"

# then
scp token.json agent@<server-ip>:/opt/ai-assistant/token.json
sudo systemctl restart assistant
```

Notes:

* The server needs `token.json` only. `credentials.json` stays on your laptop;
  the client id and secret needed for a refresh are inside `token.json`.
* The restart matters: the unit binds `token.json` into the sandbox at start,
  so a file that appears later is read-only until the service restarts.
* If your Google Cloud OAuth app is still in **Testing**, Google expires the
  refresh token after 7 days and the briefing breaks weekly. Publish the app
  ("In production") before generating the token.
* Both `token.json` and `credentials.json` are gitignored. Keep them that way.

### 4b. Gmail without a token, via Composio

If Composio holds a Gmail grant, `read_emails()` uses it and step 4 becomes
unnecessary - no browser, no scp, no weekly expiry:

```bash
bash deploy/composio-setup.sh      # as agent; needs the ck_ consumer key
sudo systemctl restart assistant
```

Two credentials exist and only one works here:

| Key | Where it comes from | What accepts it |
|---|---|---|
| `ak_` | Platform → Settings → API Keys | the v3 REST API and the python SDK |
| `ck_` | For You → Connect → Settings → Sessions & API Key | `connect.composio.dev/mcp`, header `x-consumer-api-key` |

A `ck_` key fails against every v3 endpoint with `Invalid API key` whatever
header you send, which is indistinguishable from a wrong key. The app talks
MCP directly for that reason. `COMPOSIO_GMAIL_ACCOUNT` picks the mailbox when
several are connected; leave it empty and Composio chooses its default.

The same endpoint is registered with Claude Code on the server, so an
interactive session there can reach the connected apps.

### 5. Services

```bash
sudo cp deploy/assistant.service /etc/systemd/system/
sudo cp deploy/9router.service    /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemd-analyze verify /etc/systemd/system/assistant.service
sudo systemctl enable --now 9router
sudo systemctl enable --now assistant     # after .env has real values
```

Check it:

```bash
systemctl status assistant
journalctl -u assistant -f
```

You should get a Telegram message when you send the bot `good morning`.

**What the unit's sandbox needs, and why** (all verified with `systemd-run`
using the unit's own properties):

| Setting | Without it |
|---|---|
| `CacheDirectory=ai-assistant` + `HOME=/var/cache/ai-assistant` | `ProtectHome=true` hides `/home`, so webdriver-manager cannot cache a driver and Chrome refuses to start: `PermissionError: '/home/agent'`. A `ReadWritePaths` under an inaccessible parent does not help. |
| `ReadWritePaths=-/opt/ai-assistant/token.json` | `ProtectSystem=strict` makes the app directory read-only, so each Gmail token refresh throws, `read_emails()` swallows it, and the briefing claims an empty inbox. |
| `StartLimit*` in `[Unit]` | systemd ignores them under `[Service]`, so crash-loop protection is silently off. |

`ProtectHome=true` stays on purpose: `/home/agent/.9router` holds live OAuth
credentials, and this service parses untrusted mail and web pages.

---

## 9router

[9router](https://github.com/decolua/9router) routes CLI tools and this app
through a **subscription → cheap → free** fallback chain, and trims tokens on
the way past.

```bash
sudo npm install -g 9router
which 9router          # confirm it matches ExecStart in the unit file
sudo systemctl enable --now 9router
```

Dashboard on `http://127.0.0.1:20128`. Reach it from your laptop over a
tunnel — forward **both** ports, because the Codex (ChatGPT) OAuth callback
listens on 1455:

```bash
ssh -L 20128:127.0.0.1:20128 -L 1455:127.0.0.1:1455 agent@<server-ip>
```

First login uses `INITIAL_PASSWORD` from `/etc/9router.env`
(`sudo grep INITIAL_PASSWORD /etc/9router.env`). Change it in the dashboard.

### Binding: use the flag, not the environment

**`Environment=HOSTNAME=127.0.0.1` does nothing.** `cli.js` parses `--host`
itself (default `0.0.0.0`) and then spawns the server with `HOSTNAME=<host>`,
overwriting whatever the unit set. The unit therefore runs:

```
ExecStart=/usr/bin/9router --host 127.0.0.1 --port 20128 --no-browser --log --skip-update
```

Without that flag the dashboard — and the OAuth tokens behind it — would
listen on the public IP, and this host's `INPUT` policy is `ACCEPT`. Verify
after any change:

```bash
ss -tlnp | grep 20128          # must be 127.0.0.1:20128, never 0.0.0.0
curl -m 5 http://<public-ip>:20128/dashboard   # must fail
```

### Defaults worth changing

`/etc/9router.env` sets these; all were weak or absent by default:

| Variable | Default | Why it's set |
|---|---|---|
| `REQUIRE_API_KEY` | `false` | Without it, anything reaching the port can spend your subscriptions. Enforced on `/v1/chat/completions` and `/v1/messages`; `/v1/models` stays open as a catalogue. |
| `INITIAL_PASSWORD` | `123456` | Dashboard login. |
| `API_KEY_SECRET` | a value published in the upstream README | HMAC secret the router's own API keys are derived from. |
| `JWT_SECRET`, `MACHINE_ID_SALT` | auto/published | Dashboard session signing, machine id. |

### Combos: which chain each client uses

A combo is a named fallback chain, selected by putting its name in the
`model` field. Create them in Dashboard → Combos:

| Combo | Chain | Used by |
|---|---|---|
| `brain` | Claude subscription (`cc/claude-opus-5`) → ChatGPT/Codex (`cx/gpt-6-astra`) → cheap → free | Claude Code, `brain.sh`, interactive work |
| `volume` | cheap (GLM, MiniMax, Kimi) → free (Kiro, OpenCode, Vertex) | this app — `VOLUME_MODEL=volume` in `.env` |

Keep unattended traffic on `volume`. Auto-fallback only drops a tier when
quota runs *out*, so a subscription at the top of the bot's chain would spend
Opus on Telegram messages and leave you on a cheap model when you sit down to
work. It also keeps 24/7 automation off a consumer subscription.

The app sends `X-9Router-Token-Saver: off`: Caveman and Ponytail are applied
globally by injecting system prompts, which suits a coding CLI but mangles an
Italian briefing or a client-facing draft.

### Point Claude Code at it

**Not** `~/.claude/config.json` / `anthropic_api_base` — Claude Code doesn't
read those, it silently keeps using your subscription directly. Use the `env`
block of `~/.claude/settings.json`, and no `/v1` suffix (Claude Code appends
`/v1/messages` itself, which this router does serve):

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:20128",
    "ANTHROPIC_AUTH_TOKEN": "<your 9router api key>"
  }
}
```

State (accounts, tokens, quota counters) lives in
`~/.9router/db/data.sqlite`. Re-authenticating every provider by hand is what
a backup saves you:

```bash
sudo install -m 700 deploy/9router-backup /usr/local/bin/9router-backup
sudo cp deploy/9router-backup.service deploy/9router-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now 9router-backup.timer
```

Daily at 04:30 Europe/Rome into `/root/backups/9router/`, seven kept, taken
with SQLite's online backup API so it's safe while the router is running. Same
disk as the original, so it covers corruption and mistakes, not disk loss.

### The app's API key

`REQUIRE_API_KEY=true` means the app needs a key. Keys are validated by a
plain lookup (`SELECT isActive FROM apiKeys WHERE key = ?`), not a signature,
so one can be inserted directly when the dashboard isn't reachable — that's
how the `assistant-app` key in `.env` was created. To rotate it: delete the
key in Dashboard → API Keys, issue a new one, and update `VOLUME_API_KEY` in
`.env` plus `ANTHROPIC_AUTH_TOKEN` in `/home/agent/.claude/settings.json`.

### What it gives you

| Feature | Effect |
|---|---|
| Auto fallback | Subscription → cheap (GLM, MiniMax, Kimi) → free (Kiro, OpenCode, Vertex) when quota exhausts |
| Multi-account | Several accounts per provider, round-robin or priority |
| Quota tracking | Live consumption and reset countdowns in the dashboard |
| RTK token saver | Compresses `git diff`, `grep`, `ls` output before it hits the model |
| Caveman / Ponytail | Cuts output tokens and biases toward minimal diffs |

**One thing to weigh yourself:** routing a subscription's OAuth credential
through third-party software is not obviously within Anthropic's or OpenAI's
terms, and the downside if it's judged not to be lands on your account. Your
call; just make it knowingly rather than by accident.

## Daily use

```bash
ssh agent@<server-ip>
tmux new -s work          # so it survives a dropped connection
cd /opt/ai-assistant
./deploy/brain.sh         # drain what the cheap tier flagged
```

`brain.sh` prints the queue, then opens Claude with it as context. Empty queue
means it just opens a normal session.

From Python, either side of the split:

```python
from modules.llm import ask_volume          # free tier, falls through on limits
from modules.escalate import escalate       # hand it to the brain instead

summary = ask_volume("Summarise these 15 emails: ...")
escalate("lead_ambiguous", "Studio Rossi: site fine but GBP unclaimed",
         context={"url": "..."}, priority="high")
```

---

## What does not run here

`file_janitor` is Windows-only and now no-ops on Linux with a printed notice,
rather than crashing the whole app at import. That was the actual blocker:
`main.py` imports it at module level, and `winshell` doesn't exist on Linux.

Leave the janitor on your PC. A job that deletes everything it finds in a list
of cache directories has no business running on the box that also hosts client
sites.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Briefing arrives at 10:00 | Timezone still UTC — `timedatectl set-timezone Europe/Rome` |
| Service dies at startup, `ImportError: winshell` | Old `file_janitor.py`; pull the current one |
| Morning routine hangs forever | `token.json` missing — see step 4 |
| `session not created: This version of ChromeDriver...` | Driver/Chrome mismatch; set `CHROME_BINARY`, clear `~/.wdm` |
| Scraper killed mid-run | Out of memory — confirm swap is on with `free -h` |
| Volume tier raises `whole volume chain refused` | Every free provider capped. Check keys, or wait for the daily reset |
| Briefing says "I could not read your Gmail" | `token.json` missing, expired (7-day Testing-mode limit) or unwritable — `journalctl -u assistant -n 50` has the real error |
| Service won't start, `226/NAMESPACE` | A `ReadWritePaths=` path doesn't exist; prefix it with `-` or create it |
| Bot replies "Kiro is switched off" | `UNIPV_USERNAME`/`UNIPV_PASSWORD` unset — deliberate, set them and restart |
| Volume calls return `401 Missing API key` | `VOLUME_API_KEY` in `.env` isn't a key issued by the dashboard |
| `ss -tlnp` shows `0.0.0.0:20128` | The `--host 127.0.0.1` flag is missing from `ExecStart` |
