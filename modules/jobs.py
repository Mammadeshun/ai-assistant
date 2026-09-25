"""Server jobs the phone app may ask for, from a fixed whitelist.

The webapp runs under systemd with ProtectHome=read-only and must never start
Chrome or a long job itself, so the split is:

    webapp      request(key)  inserts one row into job_requests, nothing else
    main.py     poll()        every minute: if nothing is running, claim the
                              oldest queued request and run it in a thread

Only the keys in JOBS exist. At most one queued-or-running request per key,
enforced by a partial unique index (see leads.MIGRATIONS), so a double tap or
two open tabs cannot queue the same scan twice.

Statuses: queued -> running -> done | error.
"""

import sqlite3
import datetime
import threading

from . import leads as store

# key -> what the app calls it. Nothing outside this dict can be requested.
JOBS = {
    "scan_pending": "Scansiona siti in attesa",
    "verify_no_site": "Verifica attività senza sito",
}
LABEL_STATUS = {"queued": "In coda", "running": "In esecuzione", "done": "Completato", "error": "Errore"}

# Chrome is the memory hog on a 4 GB box: the 03:00 scan in main.py and a
# requested scan take this lock, so two browsers never run at once.
HEAVY_LOCK = threading.Lock()

_worker = {"thread": None}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _row(r):
    if r is None:
        return None
    d = dict(r)
    d["label"] = JOBS.get(d["key"], d["key"])
    d["status_label"] = LABEL_STATUS.get(d["status"], d["status"])
    return d


def request(key):
    """Queue one whitelisted job. Returns (http_status, payload)."""
    if key not in JOBS:
        return 404, {"error": "lavoro sconosciuto"}
    try:
        with store.connect() as conn:
            cur = conn.execute("INSERT INTO job_requests (key, requested_at, status) VALUES (?,?,'queued')",
                               (key, _now()))
            row = conn.execute("SELECT * FROM job_requests WHERE id = ?", (cur.lastrowid,)).fetchone()
            return 200, _row(row)
    except sqlite3.IntegrityError:
        return 409, {"error": "già in coda o in esecuzione", "job": active(key)}


def active(key):
    with store.connect() as conn:
        return _row(conn.execute("SELECT * FROM job_requests WHERE key = ? AND status IN ('queued','running')"
                                 " ORDER BY id DESC LIMIT 1", (key,)).fetchone())


def overview(history=8):
    """For the app: each job's latest request, plus the recent history."""
    with store.connect() as conn:
        latest = {}
        for key in JOBS:
            latest[key] = _row(conn.execute("SELECT * FROM job_requests WHERE key = ? ORDER BY id DESC LIMIT 1",
                                            (key,)).fetchone())
        recent = [_row(r) for r in conn.execute("SELECT * FROM job_requests ORDER BY id DESC LIMIT ?", (history,))]
    return {"jobs": [{"key": k, "label": v, "last": latest[k]} for k, v in JOBS.items()], "recent": recent}


def claim_next():
    """Move the oldest queued request to running and return it, or None.
    The UPDATE's own WHERE is the claim: a request another poller took first
    matches nothing."""
    with store.connect() as conn:
        row = conn.execute("SELECT * FROM job_requests WHERE status = 'queued' ORDER BY id LIMIT 1").fetchone()
        if not row:
            return None
        cur = conn.execute("UPDATE job_requests SET status = 'running', started_at = ?"
                           " WHERE id = ? AND status = 'queued'", (_now(), row["id"]))
        if cur.rowcount != 1:
            return None
        return dict(conn.execute("SELECT * FROM job_requests WHERE id = ?", (row["id"],)).fetchone())


def finish(job_id, status, summary):
    with store.connect() as conn:
        conn.execute("UPDATE job_requests SET status = ?, finished_at = ?, summary = ? WHERE id = ?",
                     (status, _now(), (summary or "")[:1000], job_id))


def recover_interrupted():
    """A restart kills the worker thread mid-job. Left as 'running', the row
    would hold the single-flight index for that key forever."""
    with store.connect() as conn:
        cur = conn.execute("UPDATE job_requests SET status = 'error', finished_at = ?,"
                           " summary = 'Interrotto: il servizio è stato riavviato' WHERE status = 'running'",
                           (_now(),))
        return cur.rowcount


def _summarise_scan(text):
    text = (text or "").strip()
    lines = [l for l in text.splitlines()[1:] if l.strip()]
    if not lines:
        return text or "Niente da scansionare."
    clean = sum("nessun problema trovato" in l for l in lines)
    return f"Controllati {len(lines)}: {len(lines) - clean} con un problema, {clean} senza."


def _summarise_verify(result):
    r = result or {}
    return (f"Controllati {r.get('checked', 0)}: {r.get('found_site', 0)} con un sito, "
            f"{r.get('no_site_confirmed', 0)} senza sito confermato, {r.get('inconclusive', 0)} incerti, "
            f"{r.get('error', 0)} errori.")


def run_job(key):
    """Run one whitelisted job in this process and return its summary. The
    imports stay in here: the webapp imports this module for request() and
    must never load Selenium or the search client."""
    import os
    if key == "scan_pending":
        from . import commands
        return _summarise_scan(commands.scan_pending(limit=int(os.environ.get("SCAN_BATCH", "25"))))
    if key == "verify_no_site":
        from . import site_search
        return _summarise_verify(site_search.run(int(os.environ.get("VERIFY_NO_SITE_BATCH", "200"))))
    raise ValueError(f"not a whitelisted job: {key}")


def _work(job):
    try:
        with HEAVY_LOCK:
            summary = run_job(job["key"])
        finish(job["id"], "done", summary)
    except Exception as e:
        print(f"job {job['key']} failed: {type(e).__name__}: {e}")
        finish(job["id"], "error", f"{type(e).__name__}: {e}"[:500])


def poll():
    """Called every minute by main.py's scheduler. Never raises: an exception
    escaping a `schedule` job stops the assistant's main loop."""
    try:
        thread = _worker["thread"]
        if thread is not None and thread.is_alive():
            return None
        job = claim_next()
        if not job:
            return None
        print(f"job {job['key']} (#{job['id']}) starting")
        thread = threading.Thread(target=_work, args=(job,), daemon=True, name=f"job-{job['key']}")
        _worker["thread"] = thread
        thread.start()
        return job
    except Exception as e:
        print(f"job poll failed: {type(e).__name__}: {e}")
        return None
