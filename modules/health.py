"""Everything you would ssh in to check, gathered for a phone screen.

Read-only and cheap: /status should answer in a second or two, so it is worth
sending when you are wondering rather than only when something looks wrong.
"""

import os
import time
import json
import shutil
import sqlite3
import datetime
import subprocess

import requests

UNITS = ("assistant", "9router", "caddy", "docker")
ROUTER_DB = os.environ.get("ROUTER_DB", "/home/agent/.9router/db/data.sqlite")
BACKUP_DIR = os.environ.get("BACKUP_DIR", "/root/backups/9router")


def _run(args, timeout=5):
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def services():
    """Unit state, one systemctl call for all of them."""
    out = _run(["systemctl", "is-active"] + list(UNITS))
    states = out.splitlines()
    return dict(zip(UNITS, states + ["unknown"] * (len(UNITS) - len(states))))


def memory():
    values = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                key, _, rest = line.partition(":")
                values[key] = int(rest.split()[0]) * 1024
    except OSError:
        return None
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    swap_total = values.get("SwapTotal", 0)
    swap_free = values.get("SwapFree", 0)
    return {
        "total_gb": total / 1e9,
        "used_gb": (total - available) / 1e9,
        "percent": 100 * (total - available) / total if total else 0,
        "swap_used_mb": (swap_total - swap_free) / 1e6,
    }


def disk(path="/"):
    usage = shutil.disk_usage(path)
    return {"used_gb": usage.used / 1e9, "total_gb": usage.total / 1e9,
            "percent": 100 * usage.used / usage.total}


def uptime():
    try:
        with open("/proc/uptime") as f:
            seconds = float(f.read().split()[0])
    except (OSError, ValueError):
        return "?"
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    return f"{days}g {hours}h" if days else f"{hours}h {rest // 60}m"


def router_usage(days=1):
    """Today's traffic per provider, straight from the router's database."""
    if not os.path.exists(ROUTER_DB):
        return {}
    since = (datetime.date.today() - datetime.timedelta(days=days - 1)).isoformat()
    try:
        conn = sqlite3.connect(f"file:{ROUTER_DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT provider, SUM(requests) requests, SUM(inputTokens + outputTokens) tokens"
            " FROM usageDaily WHERE date >= ? GROUP BY provider ORDER BY requests DESC",
            (since,)).fetchall()
        conn.close()
        return {r["provider"]: {"requests": r["requests"] or 0, "tokens": r["tokens"] or 0}
                for r in rows}
    except sqlite3.Error:
        return {}


def model_check():
    """Is the volume tier actually answering? Times the round trip."""
    from .llm import ask_volume, VolumeLLMError
    started = time.time()
    try:
        ask_volume("Rispondi solo: ok", max_tokens=200)
        return {"ok": True, "seconds": time.time() - started}
    except VolumeLLMError as e:
        return {"ok": False, "error": str(e)[:120], "seconds": time.time() - started}


def gmail_check():
    """Can the briefing still read mail? Cheap: asks for one message."""
    try:
        from . import composio_mcp
        composio_mcp.execute("GMAIL_FETCH_EMAILS",
                             {"max_results": 1, "verbose": False, "include_payload": False},
                             thought="health check",
                             account=os.environ.get("COMPOSIO_GMAIL_ACCOUNT") or None)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def last_backup():
    try:
        files = [os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR)]
    except OSError:
        return None
    if not files:
        return None
    newest = max(files, key=os.path.getmtime)
    age_hours = (time.time() - os.path.getmtime(newest)) / 3600
    return {"name": os.path.basename(newest), "age_hours": age_hours}


def next_jobs():
    """What the scheduler will do next, and when."""
    import schedule
    return sorted((job.next_run, str(job.job_func).split("function ")[-1].split(" at")[0])
                  for job in schedule.jobs)


def summary():
    """The /status message."""
    svc = services()
    mem = memory() or {}
    dsk = disk()
    model = model_check()
    from . import leads as store

    icon = {"active": "🟢"}.get
    lines = ["📟 Stato del server", "━" * 24]

    lines.append(" ".join(f"{icon(state, '🔴')}{unit}" for unit, state in svc.items()))
    lines.append(f"⏱ acceso da {uptime()}")
    if mem:
        lines.append(f"🧠 RAM {mem['used_gb']:.1f}/{mem['total_gb']:.1f} GB "
                     f"({mem['percent']:.0f}%) · swap {mem['swap_used_mb']:.0f} MB")
    lines.append(f"💾 disco {dsk['used_gb']:.0f}/{dsk['total_gb']:.0f} GB ({dsk['percent']:.0f}%)")

    lines.append("")
    if model["ok"]:
        lines.append(f"🤖 modelli: ok ({model['seconds']:.1f}s)")
    else:
        lines.append(f"🤖 modelli: NON RISPONDONO\n   {model.get('error')}")

    usage = router_usage()
    if usage:
        lines.append("📊 oggi: " + " · ".join(
            f"{p} {v['requests']}req" for p, v in list(usage.items())[:4]))

    counts = store.counts()
    if counts:
        lines.append("📋 lead: " + " · ".join(f"{k.lower()}:{v}" for k, v in sorted(counts.items())))
    else:
        lines.append("📋 lead: nessuno ancora (/import per aggiungerli)")

    backup = last_backup()
    if backup:
        lines.append(f"💽 backup: {backup['age_hours']:.0f}h fa")

    try:
        jobs = next_jobs()
        if jobs:
            when, what = jobs[0]
            lines.append(f"⏭ prossimo: {what} alle {when.strftime('%H:%M')}")
    except Exception:
        pass

    return "\n".join(lines)
