"""/sito: how switchers.events is doing, from the two sources that count.

Visitors come from the Caddy access log via the existing visitor report,
which a root timer (deploy/site-stats.timer) runs every 20 minutes into a
readable file - the log holds visitor IPs and stays unreadable to this
service. Search comes from Google Search Console through Composio.
"""

import os
import datetime
import subprocess

GSC_PROPERTY = os.environ.get("SITE_GSC_PROPERTY", "sc-domain:switchers.events")
# Written every 20 minutes by site-stats.timer, as root: the raw Caddy log
# holds visitor IPs and stays unreadable to this service. (A sudo rule was the
# first attempt; NoNewPrivileges=true in the unit - correctly - blocks sudo.)
STATS_FILE = os.environ.get("SITE_STATS_FILE", "/var/lib/assistant-site/stats.txt")


def _report_text():
    try:
        with open(STATS_FILE) as f:
            return f.read()
    except OSError:
        return ""


def visitor_stats():
    """Per-day visitors for the app's chart, parsed from the same report."""
    out = _report_text()
    if not out:
        return None
    days, stats, section, contacts = [], {}, None, {}
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("Unique visitors"):
            stats["visitors"] = int(s.split(":")[1])
        elif s.startswith("Pageviews"):
            stats["pageviews"] = int(s.split(":")[1])
        elif s.startswith("Per day"):
            section = "days"
        elif s == "Contact clicks":
            section = "contacts"
        elif s in ("Top pages", "Top referrers", "Broken links (404)") or s.startswith("Filtered"):
            section = None
        elif section == "days" and s[:4].isdigit():
            parts = s.split()
            days.append({"date": parts[0], "visitors": int(parts[1]), "views": int(parts[3])})
        elif section == "contacts" and s:
            n, _, what = s.partition(" ")
            if n.isdigit():
                contacts[what.strip()] = int(n)
    stats["days"] = days
    stats["contacts"] = contacts
    return stats


def visitors():
    out = _report_text()
    if not out:
        return "visitatori: statistiche non ancora disponibili"
    keep, section = [], None
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith(("Unique visitors", "Pageviews")):
            keep.append(stripped)
        elif stripped in ("Contact clicks", "Top referrers"):
            section = stripped
            keep.append(stripped + ":")
        elif section and stripped and line.startswith("  ") and len(keep) < 14:
            keep.append("  " + stripped)
        elif not stripped:
            section = None
    return "\n".join(keep) or "visitatori: nessun dato"


def search():
    from . import composio_mcp
    today = datetime.date.today()
    data = composio_mcp.execute(
        "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY",
        {"site_url": GSC_PROPERTY, "dimensions": ["date"], "data_state": "all",
         "start_date": (today - datetime.timedelta(days=28)).isoformat(),
         "end_date": today.isoformat(), "row_limit": 60},
        thought="weekly search performance for the site owner")
    rows = {r["keys"][0]: r for r in data.get("rows", [])}

    def window(start, end):
        c = i = w = 0.0
        for n in range((end - start).days):
            r = rows.get((start + datetime.timedelta(days=n)).isoformat())
            if r:
                c += r["clicks"]; i += r["impressions"]; w += r["position"] * r["impressions"]
        return c, i, (w / i if i else 0)

    # Search Console lags two to three days, so "this week" ends three days ago.
    end = today - datetime.timedelta(days=2)
    now_c, now_i, now_p = window(end - datetime.timedelta(days=7), end)
    was_c, was_i, was_p = window(end - datetime.timedelta(days=14), end - datetime.timedelta(days=7))

    def trend(now, was):
        if not was:
            return ""
        change = (now - was) / was * 100
        return f" ({'+' if change >= 0 else ''}{change:.0f}%)"

    search.last = {"clicks": now_c, "impressions": now_i, "position": now_p,
                   "prev_clicks": was_c, "prev_impressions": was_i, "prev_position": was_p}
    return (f"Google, ultimi 7 giorni (vs 7 prima):\n"
            f"  clic {now_c:.0f}{trend(now_c, was_c)} · impressioni {now_i:.0f}{trend(now_i, was_i)}\n"
            f"  posizione media {now_p:.1f}" + (f" (era {was_p:.1f})" if was_p else ""))


search.last = None


def search_stats():
    search()
    return search.last


def report():
    parts = ["🌐 switchers.events", "━" * 24, visitors(), ""]
    try:
        parts.append(search())
    except Exception as e:
        parts.append(f"Google: non disponibile ({str(e)[:100]})")
    return "\n".join(parts)
