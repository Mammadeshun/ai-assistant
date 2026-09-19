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
sudo cp deploy/9router.service    /etc/systemd/system/
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

## 9router

[9router](https://github.com/decolua/9router) routes CLI tools through a
**subscription → cheap → free** fallback chain, and trims tokens on the way
past. Your Claude subscription sits at the top of that chain as an OAuth
provider, so it is the brain by default and the cheaper tiers catch the
overflow automatically when quota runs out.

```bash
sudo npm install -g 9router
which 9router          # confirm it matches ExecStart in the unit file

sudo cp deploy/9router.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now 9router
```

Dashboard on `http://127.0.0.1:20128`. Reach it from your laptop over a tunnel:

```bash
ssh -L 20128:127.0.0.1:20128 agent@<server-ip>
```

**Do not set `HOSTNAME=0.0.0.0`.** The upstream docs offer it for VPS use, but
that dashboard holds live OAuth tokens for every account you connect — Claude,
Copilot, Cursor. On a public IP the only thing between those tokens and the
internet is `JWT_SECRET`. The tunnel costs nothing and removes the question.
Set a long random `JWT_SECRET` in `.env` regardless.

### Point Claude Code at it

```json
// ~/.claude/config.json
{
  "anthropic_api_base": "http://127.0.0.1:20128/v1",
  "anthropic_api_key": "<your 9router api key>"
}
```

State (accounts, tokens, quota counters) lives in `~/.9router/db/data.sqlite`.
Back that up — re-authenticating every provider is tedious.

### What it gives you

| Feature | Effect |
|---|---|
| Auto fallback | Subscription → cheap (GLM, MiniMax, Kimi) → free (Kiro, OpenCode, Vertex) when quota exhausts |
| Multi-account | Several accounts per provider, round-robin or priority |
| Quota tracking | Live consumption and reset countdowns in the dashboard |
| RTK token saver | Compresses `git diff`, `grep`, `ls` output before it hits the model |
| Caveman / Ponytail | Cuts output tokens and biases toward minimal diffs |

**One thing to weigh yourself:** routing a subscription's OAuth credential
through third-party software is not obviously within Anthropic's terms, and the
downside if it's judged not to be lands on your account. The volume tier in
`modules/llm.py` is unaffected either way — it calls provider APIs with your own
keys. Your call; just make it knowingly rather than by accident.

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
