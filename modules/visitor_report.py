"""Visitor analytics for switchers.events, built on Caddy's JSON access log.

Reads Caddy access logs, strips bots and static assets, and produces a human
summary: unique visitors per day, top pages, top referrers. Can print the
report or send it to Telegram.

Runs on the web server itself (the log is local there) and depends only on the
standard library, so it needs no pip install.

Usage:
    python3 visitor_report.py                      # yesterday + 7-day context
    python3 visitor_report.py --days 30            # last 30 days
    python3 visitor_report.py --date 2026-09-09    # one specific day
    python3 visitor_report.py --send               # also send to Telegram

Telegram credentials come from the environment, never from source:
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

from __future__ import annotations

import argparse
import glob
import gzip
import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_LOG = "/var/log/caddy/access.log"
DEFAULT_TZ = "Europe/Rome"
TELEGRAM_LIMIT = 4096

# Caddy writes rotated files alongside the live one as access-<timestamp>.log
ROTATED_GLOB = "{stem}-*{ext}"

# Matched against User-Agent. Covers search engines, SEO crawlers, AI scrapers,
# uptime monitors, headless browsers and scripted clients.
BOT_PATTERN = re.compile(
    r"""
    bot\b | \bbots\b | spider | crawl | slurp | scraper | fetcher | archiver
    # Vendor names must be matched in their CRAWLER form only. Bare "google",
    # "duckduck" or "pinterest" also appear in the User-Agents of real in-app
    # browsers (the Google app, the DuckDuckGo browser, Pinterest's webview),
    # and matching those silently deletes real visitors from every report.
    | googlebot | googleother | google-inspectiontool | google-read-aloud
    | mediapartners-google | apis-google | feedfetcher-google | googleweblight
    | bingpreview | yandex\w*bot | baiduspider | duckduckbot | exabot
    | facebookexternalhit | facebot | twitterbot | slackbot | telegrambot | discordbot
    | whatsapp/ | linkedinbot | pinterestbot | redditbot | embedly | quorabot
    | skypeuripreview
    | semrush | ahrefs | mj12 | dotbot | blexbot | dataforseo | serpstat | seokicks
    | petalbot | bytespider | applebot | amazonbot | ia_archiver | archive\.org
    | gptbot | claudebot | claude-web | anthropic | ccbot | perplexity | youbot
    | oai-searchbot | chatgpt | cohere | diffbot | omgili | timpibot | imagesiftbot
    | headlesschrome | phantomjs | selenium | playwright | puppeteer | lighthouse
    | python-requests | python-urllib | aiohttp | httpx | go-http-client | okhttp
    | java/ | libwww | lwp- | perl | ruby | curl/ | wget/ | powershell | winhttp
    | uptime | pingdom | statuscake | monitoring | newrelic | datadog | zabbix | nagios
    | site24x7 | uptimerobot | betteruptime | hetrixtools | prometheus
    | masscan | nmap | zgrab | nuclei | censys | shodan | expanse | paloalto
    | caddy-log-selftest
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Fallback when the response carried no Content-Type (e.g. 304s on some setups).
ASSET_EXT = {
    ".css", ".js", ".mjs", ".map", ".json", ".xml", ".txt",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif", ".ico", ".bmp",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp4", ".webm", ".mov", ".mp3", ".wav", ".ogg",
    ".zip", ".gz", ".br", ".zst", ".pdf", ".wasm", ".glb", ".gltf", ".hdr",
}

# Noise paths that are technically HTML-ish but are never a real pageview.
NOISE_PATHS = {
    "/favicon.ico", "/robots.txt", "/sitemap.xml", "/ads.txt",
    "/.env", "/wp-login.php", "/xmlrpc.php",
}

SELF_HOSTS = ("switchers.events",)

# Nearly every crawler UA starts with "Mozilla/5.0", so the product token has to
# be dug out of the middle of the string rather than taken from the front.
BOT_NAME_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9_\-\.]*(?:bot|spider|crawler|scraper|archiver)"
    r"[A-Za-z0-9_\-\.]*)",
    re.IGNORECASE,
)

# Per-run salt: visitor identity is stable within one report, unrecoverable after.
_SALT = os.urandom(16)


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------

def log_paths(primary: str) -> list[str]:
    """The live log plus any rotated siblings, oldest first.

    Rotated files may be gzipped, so those are matched too - missing them would
    drop whole days from the window without any visible error.
    """
    stem, ext = os.path.splitext(primary)
    found = set(glob.glob(ROTATED_GLOB.format(stem=stem, ext=ext)))
    found |= set(glob.glob(ROTATED_GLOB.format(stem=stem, ext=ext) + ".gz"))
    if os.path.exists(primary):
        found.add(primary)
    return sorted(found)


def _open_log(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", errors="replace")
    return open(path, "r", errors="replace")


def _header(headers: dict, name: str) -> str:
    """Caddy logs headers as {"Name": ["value"]} - index the list, not the dict."""
    v = headers.get(name)
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def iter_records(paths, tz):
    """Yield normalised request records from Caddy JSON access logs."""
    for path in paths:
        try:
            fh = _open_log(path)
        except OSError as e:
            print(f"warning: cannot read {path}: {e}", file=sys.stderr)
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line or line[0] != "{":
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("msg") != "handled request":
                    continue

                req = e.get("request") or {}
                headers = req.get("headers") or {}
                resp = e.get("resp_headers") or {}

                ts = e.get("ts")
                if not isinstance(ts, (int, float)):
                    continue
                when = datetime.fromtimestamp(ts, timezone.utc).astimezone(tz)

                uri = req.get("uri") or "/"
                path_only = urllib.parse.urlsplit(uri).path or "/"

                yield {
                    "when": when,
                    "day": when.date(),
                    "ip": req.get("client_ip") or req.get("remote_ip") or "",
                    "ua": _header(headers, "User-Agent"),
                    "referer": _header(headers, "Referer"),
                    "host": req.get("host") or "",
                    "method": req.get("method") or "",
                    "uri": uri,
                    "path": path_only,
                    "status": e.get("status") or 0,
                    "size": e.get("size") or 0,
                    "ctype": (_header(resp, "Content-Type") or "").split(";")[0].strip().lower(),
                }


# --------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------

def is_bot(rec) -> bool:
    ua = rec["ua"]
    if not ua:
        return True  # no UA at all is a scanner, not a person
    return bool(BOT_PATTERN.search(ua))


def bot_name(ua: str) -> str:
    """Best-effort product name for a crawler, for the 'what hit us' line."""
    if not ua:
        return "(no user-agent)"
    m = BOT_NAME_RE.search(ua)
    if m:
        return m.group(1)
    m = BOT_PATTERN.search(ua)
    if m:
        return m.group(0).strip(" /")
    return ua.split("/")[0][:24]


def is_pageview(rec) -> bool:
    """A human-visible HTML page load, as opposed to an asset or a probe."""
    if rec["method"] != "GET":
        return False
    if rec["status"] not in (200, 304):
        return False
    if rec["path"] in NOISE_PATHS:
        return False
    ctype = rec["ctype"]
    if ctype:
        return ctype == "text/html"
    # No Content-Type recorded: fall back to the extension.
    ext = os.path.splitext(rec["path"])[1].lower()
    return ext not in ASSET_EXT


def visitor_id(rec) -> str:
    h = hashlib.sha256()
    h.update(_SALT)
    h.update(rec["ip"].encode())
    h.update(b"|")
    h.update(rec["ua"].encode())
    return h.hexdigest()[:16]


def normalise_path(p: str) -> str:
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    return p or "/"


def referrer_domain(ref: str) -> str | None:
    if not ref:
        return None
    try:
        host = urllib.parse.urlsplit(ref).netloc.lower()
    except ValueError:
        return None
    if not host:
        return None
    host = host.split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    if any(host == s or host.endswith("." + s) for s in SELF_HOSTS):
        return None  # internal navigation, not a referral
    return host


# --------------------------------------------------------------------------
# aggregation
# --------------------------------------------------------------------------

def analyze(records, start_day, end_day):
    """Aggregate records within [start_day, end_day] inclusive."""
    per_day_visitors = defaultdict(set)
    per_day_views = Counter()
    pages = Counter()
    referrers = Counter()
    bot_uas = Counter()
    bot_full_uas = Counter()  # kept in full for --show-bots audits
    statuses = Counter()
    not_found = Counter()
    all_visitors = set()

    totals = {"lines": 0, "bots": 0, "assets": 0, "pageviews": 0, "bytes": 0}

    for rec in records:
        day = rec["day"]
        if day < start_day or day > end_day:
            continue
        totals["lines"] += 1
        statuses[rec["status"]] += 1
        totals["bytes"] += rec["size"]

        if is_bot(rec):
            totals["bots"] += 1
            bot_uas[bot_name(rec["ua"])] += 1
            bot_full_uas[rec["ua"] or "(no user-agent)"] += 1
            continue

        if rec["status"] == 404:
            not_found[normalise_path(rec["path"])] += 1

        if not is_pageview(rec):
            totals["assets"] += 1
            continue

        totals["pageviews"] += 1
        vid = visitor_id(rec)
        per_day_visitors[day].add(vid)
        all_visitors.add(vid)
        per_day_views[day] += 1
        pages[normalise_path(rec["path"])] += 1

        dom = referrer_domain(rec["referer"])
        if dom:
            referrers[dom] += 1

    return {
        "totals": totals,
        "per_day_visitors": {d: len(v) for d, v in per_day_visitors.items()},
        "per_day_views": dict(per_day_views),
        "pages": pages,
        "referrers": referrers,
        "bot_uas": bot_uas,
        "bot_full_uas": bot_full_uas,
        "statuses": statuses,
        "not_found": not_found,
        "unique_total": len(all_visitors),
    }


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def _bar(n, peak, width=12):
    if peak <= 0:
        return ""
    return "#" * max(1, round(n / peak * width)) if n else ""


def format_report(stats, start_day, end_day, title="switchers.events"):
    t = stats["totals"]
    out = []
    span = (f"{start_day}" if start_day == end_day
            else f"{start_day} -> {end_day}")
    out.append(f"{title} - visitors")
    out.append(span)
    out.append("")

    if t["lines"] == 0:
        out.append("No requests logged in this period.")
        return "\n".join(out)

    out.append(f"Unique visitors : {stats['unique_total']}")
    out.append(f"Pageviews       : {t['pageviews']}")
    out.append(f"Bandwidth (all) : {t['bytes'] / 1_048_576:.1f} MB")
    out.append("")

    days = sorted(stats["per_day_visitors"])
    if days:
        peak = max(stats["per_day_visitors"].values())
        out.append("Per day (unique / views)")
        d = start_day
        while d <= end_day:
            u = stats["per_day_visitors"].get(d, 0)
            v = stats["per_day_views"].get(d, 0)
            out.append(f"  {d}  {u:>4} / {v:<5} {_bar(u, peak)}")
            d += timedelta(days=1)
        out.append("")

    if stats["pages"]:
        out.append("Top pages")
        for p, c in stats["pages"].most_common(8):
            out.append(f"  {c:>5}  {p[:52]}")
        out.append("")

    out.append("Top referrers")
    if stats["referrers"]:
        for r, c in stats["referrers"].most_common(8):
            out.append(f"  {c:>5}  {r[:52]}")
    else:
        out.append("  (none - all traffic was direct or untagged)")
    out.append("")

    if stats["not_found"]:
        out.append("Broken links (404)")
        for p, c in stats["not_found"].most_common(5):
            out.append(f"  {c:>5}  {p[:52]}")
        out.append("")

    out.append(f"Filtered out: {t['bots']} bot/crawler, {t['assets']} asset requests")
    if stats["bot_uas"]:
        top = ", ".join(f"{name}({c})" for name, c in stats["bot_uas"].most_common(3))
        out.append(f"Top crawlers: {top}")

    return "\n".join(out)


# --------------------------------------------------------------------------
# telegram
# --------------------------------------------------------------------------

def _post_telegram(token, payload, timeout):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return bool(json.loads(resp.read()).get("ok", False))


def send_telegram(message: str, token=None, chat_id=None, timeout=20) -> bool:
    """Send the report via the Telegram Bot API using only the stdlib.

    Sent inside a <pre> block: the report is column-aligned with a bar chart,
    and Telegram's default proportional font would leave it ragged. Falls back
    to plain text if the formatted send is rejected, so a markup problem can
    never cost the whole report.
    """
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("error: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in environment",
              file=sys.stderr)
        return False

    # Leave room for the <pre> wrapper and for HTML escaping to expand the text.
    budget = TELEGRAM_LIMIT - 200
    if len(message) > budget:
        message = message[:budget] + "\n... (truncated)"

    formatted = {
        "chat_id": chat_id,
        "text": f"<pre>{html.escape(message)}</pre>",
        "parse_mode": "HTML",
    }
    try:
        if _post_telegram(token, formatted, timeout):
            return True
        print("warning: formatted send rejected, retrying as plain text",
              file=sys.stderr)
    except Exception as e:
        print(f"warning: formatted send failed ({e}), retrying as plain text",
              file=sys.stderr)

    try:
        return _post_telegram(token, {"chat_id": chat_id, "text": message}, timeout)
    except Exception as e:  # network, auth, rate limit
        print(f"error: telegram send failed: {e}", file=sys.stderr)
        return False


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def build_report(log=DEFAULT_LOG, days=7, date=None, tzname=DEFAULT_TZ, end_offset=0):
    """end_offset=0 ends the window today; 1 ends it yesterday (whole days only)."""
    tz = ZoneInfo(tzname)
    today = datetime.now(tz).date()

    if date:
        start_day = end_day = datetime.strptime(date, "%Y-%m-%d").date()
    else:
        end_day = today - timedelta(days=end_offset)
        start_day = end_day - timedelta(days=days - 1)

    paths = log_paths(log)
    if not paths:
        return None, f"No log files found matching {log}"

    stats = analyze(iter_records(paths, tz), start_day, end_day)
    return stats, format_report(stats, start_day, end_day)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Caddy visitor report for switchers.events")
    ap.add_argument("--log", default=DEFAULT_LOG, help="path to Caddy JSON access log")
    ap.add_argument("--days", type=int, default=7, help="number of days back, ending today")
    ap.add_argument("--date", help="report a single day (YYYY-MM-DD)")
    ap.add_argument("--yesterday", action="store_true", help="report yesterday only")
    ap.add_argument("--daily", action="store_true",
                    help="scheduled mode: last 7 complete days, ending yesterday")
    ap.add_argument("--tz", default=DEFAULT_TZ, help="timezone for day boundaries")
    ap.add_argument("--send", action="store_true", help="send the report to Telegram")
    ap.add_argument("--show-bots", action="store_true",
                    help="list every filtered User-Agent, to audit for false positives")
    ap.add_argument("--quiet", action="store_true", help="do not print to stdout")
    args = ap.parse_args(argv)

    date = args.date
    if args.yesterday:
        date = (datetime.now(ZoneInfo(args.tz)).date() - timedelta(days=1)).isoformat()

    # --daily reports whole days only, so a morning run never shows a stub "today".
    end_offset = 1 if args.daily else 0
    days = 7 if args.daily else args.days

    stats, report = build_report(args.log, days, date, args.tz, end_offset)

    if not args.quiet:
        print(report)

    # The filter can only be trusted if you can see what it removed. In-app
    # browsers (Instagram, WhatsApp) send odd User-Agents; if one ever matches
    # the bot pattern, a real visitor disappears with no other trace.
    if args.show_bots and stats:
        print("\nFiltered User-Agents (check for real visitors caught by mistake)")
        if not stats["bot_full_uas"]:
            print("  (none)")
        for ua, c in stats["bot_full_uas"].most_common():
            print(f"  {c:>5}  {ua}")

    if args.send:
        return 0 if send_telegram(report) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
