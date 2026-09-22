"""/sito: how switchers.events is doing, from the two sources that count.

Visitors come from the Caddy access log via the existing visitor report, run
through a sudoers rule fixed to one exact command line - the log holds
visitor IPs and stays unreadable to this service. Search comes from Google
Search Console through Composio.
"""

import os
import datetime
import subprocess

GSC_PROPERTY = os.environ.get("SITE_GSC_PROPERTY", "sc-domain:switchers.events")
REPORT_CMD = ["sudo", "-n", "/usr/bin/python3", "/opt/visitor-report/visitor_report.py",
              "--days", "7"]


def visitors():
    try:
        out = subprocess.run(REPORT_CMD, capture_output=True, text=True, timeout=60).stdout
    except (subprocess.SubprocessError, OSError) as e:
        return f"visitatori: non disponibili ({e})"
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

    return (f"Google, ultimi 7 giorni (vs 7 prima):\n"
            f"  clic {now_c:.0f}{trend(now_c, was_c)} · impressioni {now_i:.0f}{trend(now_i, was_i)}\n"
            f"  posizione media {now_p:.1f}" + (f" (era {was_p:.1f})" if was_p else ""))


def report():
    parts = ["🌐 switchers.events", "━" * 24, visitors(), ""]
    try:
        parts.append(search())
    except Exception as e:
        parts.append(f"Google: non disponibile ({str(e)[:100]})")
    return "\n".join(parts)
