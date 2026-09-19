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

They do not mix, for one concrete reason: **the subscription login is
interactive and cannot be scripted.** So the brain never runs from a timer.
Instead the volume tier writes anything it can't confidently judge to a queue,
and you drain that queue with `./deploy/brain.sh`.

The volume tier falls through providers on rate limits (`groq` → `gemini` →
`groq-small`), the same way the router does for Claude Code. One capped free
tier doesn't end the night's run.

---

## Install

### 1. Bootstrap the box

As root:

```bash
git clone <your-repo> /tmp/setup && cd /tmp/setup
bash deploy/bootstrap.sh
```

Sets the timezone to `Europe/Rome`, adds 4 GB swap, installs Python, Node 22
and Google Chrome, creates the `agent` user, and opens 22/80/443.

Safe to run twice. **SSH hardening is opt-in** — once you've confirmed your key
works, re-run with `--harden-ssh` to disable password login. The script refuses
if it can't find an `authorized_keys`, so it won't lock you out.

### 2. Deploy the code

```bash
sudo -u agent -i
git clone <your-repo> /opt/ai-assistant
cd /opt/ai-assistant
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

Set at minimum: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GROQ_API_KEY`,
`GEMINI_API_KEY`, `UNIPV_USERNAME`, `UNIPV_PASSWORD`.

Add these too, so the scraper stops re-downloading a driver every run:

```
CHROME_BINARY=/usr/bin/google-chrome
```

> systemd parses `.env` itself — plain `KEY=value`, no `export`, no quotes
> around values.

### 4. Gmail — the step that silently blocks everything

`email_reader.py` calls `flow.run_local_server()`, which opens a browser. There
isn't one on the server, so the morning routine hangs on first run.

Authenticate **on your laptop**, then copy the result over:

```bash
# on your PC, in the project folder
python -c "from modules.email_reader import authenticate_gmail; authenticate_gmail()"

# then
scp token.json agent@<server-ip>:/opt/ai-assistant/token.json
```

Both `token.json` and `credentials.json` are gitignored. Keep them that way.

### 5. Services

```bash
sudo cp deploy/assistant.service /etc/systemd/system/
sudo cp deploy/ccr.service       /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now assistant
```

Check it:

```bash
systemctl status assistant
journalctl -u assistant -f
```

You should get a Telegram message when you send the bot `good morning`.

---

## The router

```bash
sudo npm install -g @musistudio/claude-code-router
ccr -h          # confirm the serve subcommand for your version
```

`ccr.service` uses `ccr serve --no-open`. Older releases use `ccr start` —
**check `ccr -h` and fix `ExecStart` before enabling the unit.**

```bash
sudo systemctl enable --now ccr
```

It binds to localhost. Leave it that way: an exposed router port is an open
endpoint for draining your API keys. If you need it remotely, tunnel it:

```bash
ssh -L 3456:127.0.0.1:3456 agent@<server-ip>
```

Then, on the server:

- `ccr code` — Claude Code on free models, for grunt work
- `claude` — Claude Code on your subscription, for the brain work

---

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
