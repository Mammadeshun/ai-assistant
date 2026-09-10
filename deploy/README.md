# switchers.events visitor reporting

Daily traffic summary for switchers.events, delivered to Telegram.

## Why it runs on the VPS, not on the PC

The data source is Caddy's JSON access log at `/var/log/caddy/access.log`, which
only exists on the Hetzner box. The rest of `ai-assistant` runs on Windows, so
pulling the log to the PC would mean an SSH key, a scheduled task and a machine
that happens to be awake at 08:00. The VPS is already always-on and already has
the file, so the report runs there as a systemd timer.

The module is stdlib-only (no `requests`, no `pip`) because the VPS has no pip
installed.

## Install

On the server, as root:

```bash
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... ./deploy/install.sh
```

Credentials land in `/etc/visitor-report.env` (mode 600) and are read by the
systemd unit. They are never committed.

## Use it by hand

```bash
python3 /opt/visitor-report/visitor_report.py                 # last 7 days
python3 /opt/visitor-report/visitor_report.py --days 30       # last 30 days
python3 /opt/visitor-report/visitor_report.py --date 2026-09-14
python3 /opt/visitor-report/visitor_report.py --daily --send  # what the timer sends
```

## Schedule

`visitor-report.timer` fires at 08:00 Europe/Rome and reports the **last 7
complete days**, so a morning run never shows a half-empty "today".

```bash
systemctl list-timers visitor-report.timer
systemctl start visitor-report.service     # send one now
journalctl -u visitor-report -n 30
```

## What gets filtered

- **Bots** — search engines, SEO crawlers, AI scrapers, uptime monitors,
  headless browsers, scripted clients, and any request with no User-Agent.
- **Static assets** — decided by the response `Content-Type` (only `text/html`
  counts as a pageview), falling back to file extension when no type was
  recorded. This is why a CSS file never shows up as a page.
- **Self-referrals** — links from switchers.events to itself are navigation,
  not referrals.

Filtered totals are still printed at the bottom, so you can see how much of the
traffic was crawlers. To audit the filter itself:

```bash
python3 /opt/visitor-report/visitor_report.py --days 30 --show-bots
```

That lists every User-Agent that was removed. Worth a look occasionally: if a
real visitor is ever caught by the bot pattern they vanish from the report with
no other trace, and aggregates alone will never reveal it.

`tests/test_bot_filter.py` guards this. It asserts that 17 real browsers -
including the Instagram, Facebook, Google-app, DuckDuckGo and Pinterest in-app
browsers - are never classified as bots, while 22 known crawlers always are.
An early version of the pattern matched bare `google`, `duckduck` and
`pinterest`, which silently deleted three classes of real mobile visitor; run
the test after touching `BOT_PATTERN`.

```bash
python3 tests/test_bot_filter.py
```

## How a "unique visitor" is counted

A salted hash of `client_ip + User-Agent`, distinct per calendar day in
Europe/Rome. The salt is regenerated every run, so no visitor identifier
survives the process.

This is an approximation, and it is worth knowing which way it errs:

- Several people behind one office or mobile NAT with the same browser count
  as **one** visitor.
- One person on phone and laptop counts as **two**.
- A browser upgrade mid-week makes a returning visitor look new.

For a small marketing site the trend line matters more than the absolute
number, but do not quote these figures as exact.

## Caveats

- **No historical data before 2026-09-10.** Access logging was misconfigured
  until then (the log file was root-owned, so Caddy's config reload failed and
  it silently kept serving with the previous, log-free config). Traffic before
  that date was never written anywhere and cannot be recovered.
- Caddy rotates at 20 MiB, keeping 12 files for 90 days. The report reads
  rotated files too, so a rotation mid-window does not lose days.
- Referrers are only as good as what browsers send; most direct traffic, and
  much app traffic, arrives with no `Referer` at all.
