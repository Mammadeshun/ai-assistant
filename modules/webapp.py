"""The phone app: a small JSON API plus one static page, standard library only.

    python -m modules.webapp          # serves 127.0.0.1:8787

Caddy terminates TLS in front of it; it never listens on a public interface.

Sign-in works like pairing an Apple TV: /app in Telegram replies with a
six-digit code, valid ten minutes, five tries. A code rather than a link,
because an iPhone home-screen app keeps its own cookies apart from Safari -
a login link opened in Safari would not sign in the installed app.
"""

import os
import json
import time
import secrets
import socket
import hashlib
import datetime
import threading
import http.server
import urllib.parse

from . import leads as store

HOST = os.environ.get("WEBAPP_HOST", "127.0.0.1")
PORT = int(os.environ.get("WEBAPP_PORT", "8787"))
STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webapp")
DAILY_GOAL = int(os.environ.get("DAILY_CALL_GOAL", "20"))
SHOTS_DIR = os.environ.get("SCAN_SHOTS_DIR", "data/shots")
SESSION_DAYS = 90
# Thirty, not ten: the code arrives in Telegram and has to be carried to
# another app, and the first pairing failed on exactly that - it expired
# before the page loaded. Six digits and five tries still leave a guesser
# one chance in 200,000.
CODE_MINUTES = 30
CODE_TRIES = 5

_cache = {}
_cache_lock = threading.Lock()
# One email send at a time, so the already-sent check and the send cannot
# interleave: a double tap on a slow connection must not mail a studio twice.
_email_lock = threading.Lock()
# Read-check-write on the pairing code. Without it, parallel guesses each read
# the same try count: an audit got 22-32 guesses past a limit of 5.
_pair_lock = threading.Lock()


def cached(key, seconds, compute):
    """Site and system data are slow to compute and fine slightly stale."""
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < seconds:
            return hit[1]
    value = compute()
    with _cache_lock:
        _cache[key] = (time.time(), value)
    return value


# ── pairing & sessions ─────────────────────────────────────────────────────

def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def new_pairing_code():
    """Called by /app in Telegram."""
    code = f"{secrets.randbelow(10**6):06d}"
    store.set_setting("webapp_code", json.dumps({
        "hash": _digest(code), "expires": time.time() + CODE_MINUTES * 60, "tries": 0}))
    return code


def redeem_code(code):
    with _pair_lock:
        return _redeem(code)


def _redeem(code):
    raw = store.get_setting("webapp_code")
    if not raw:
        return None
    pending = json.loads(raw)
    if time.time() > pending["expires"] or pending["tries"] >= CODE_TRIES:
        store.set_setting("webapp_code", "")
        return None
    if not secrets.compare_digest(_digest(code.strip()), pending["hash"]):
        pending["tries"] += 1
        store.set_setting("webapp_code", json.dumps(pending))
        return None
    store.set_setting("webapp_code", "")          # single use
    token = secrets.token_urlsafe(32)
    sessions = json.loads(store.get_setting("webapp_sessions", "[]"))
    now = time.time()
    sessions = [s for s in sessions if s["expires"] > now]
    sessions.append({"hash": _digest(token), "expires": now + SESSION_DAYS * 86400})
    store.set_setting("webapp_sessions", json.dumps(sessions[-10:]))
    return token


def valid_session(token):
    if not token:
        return False
    sessions = json.loads(store.get_setting("webapp_sessions", "[]"))
    now, digest = time.time(), _digest(token)
    return any(secrets.compare_digest(s["hash"], digest) and s["expires"] > now for s in sessions)


# ── data for the four tabs ─────────────────────────────────────────────────

PROBLEM_TONE = {"site_down": "critical", "ssl_expired": "critical", "not_mobile": "serious",
                "ssl_expiring": "warning", "slow": "warning", "no_website": "neutral",
                "no_site_found": "neutral", "mobile_overflow": "neutral",
                "listed_page_gone": "neutral"}


def lead_view(lead, full=False):
    from . import outreach
    findings = store.findings_of(lead)
    view = {
        "id": lead["id"], "name": lead["name"], "category": lead.get("category"),
        "city": lead.get("city"), "phone": lead.get("phone"), "email": lead.get("email"),
        "website": lead.get("website"), "state": lead["state"],
        "problem": outreach.describe(findings) or None,
        "tone": PROBLEM_TONE.get(findings[0]["code"], "neutral") if findings else "neutral",
        "attempts": lead.get("attempts") or 0,
    }
    if full:
        # The WhatsApp text is built fresh rather than read from `draft`: the
        # stored drafts are the model's email-style openers, several are
        # empty, and an empty one made a wa.me link that opened a blank chat.
        # The same rules the queue uses, applied here too. The Lead screen
        # used to offer a first message to anyone with a number, including
        # leads already contacted, parked as a stale duplicate, or marked
        # "not interested".
        open_channels = store.channels_open(lead["id"])
        message = (outreach.whatsapp_message(lead, findings)
                   if lead.get("whatsapp") and {"whatsapp", "follow"} & open_channels else None)
        wa_capped = bool(message) and lead["state"] == "NEW" and \
            whatsapp_today() >= outreach.MAX_WHATSAPP_PER_DAY
        send_wa = message and not wa_capped
        body = (outreach.email_message(lead, findings)
                if lead.get("email") and "email" in open_channels else None)
        # "draft" is the call script. Built fresh like the messages: the stored
        # model drafts describe findings that have since been corrected.
        view.update(draft=outreach.call_script(lead, findings), notes=lead.get("notes"), message=message,
                    mobile=lead.get("whatsapp"),
                    whatsapp=outreach.whatsapp_link(lead, message) if send_wa else None,
                    wa_app=outreach.whatsapp_app_link(lead, message) if send_wa else None,
                    wa_capped=wa_capped,
                    # A follow-up opens the chat empty: the first message
                    # again, days after talking to them, would be absurd.
                    wa_chat=f"whatsapp://send?phone={lead['whatsapp'].lstrip('+')}" if lead.get("whatsapp") else None,
                    email_subject=outreach.subject_for(lead, findings) if body else None,
                    email_body=body, email_footer=outreach.email_footer().strip() if body else None,
                    email_sent=already_emailed(lead["id"]) if body else False,
                    email_capped=bool(body) and emails_today() >= outreach.MAX_EMAIL_PER_DAY,
                    shot=os.path.exists(os.path.join(SHOTS_DIR, f"lead-{lead['id']}.png")),
                    problems=[f["code"] for f in findings])
    return view


def calls_today():
    today = datetime.date.today().isoformat()
    with store.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(DISTINCT lead_id) n FROM events WHERE at >= ? AND"
            " (kind = 'attempt' OR (kind LIKE 'state:%' AND detail LIKE 'chiamata%'))",
            (today,)).fetchone()
    return row["n"]


def _sent_today(state):
    """Distinct practices moved into `state` today, from the app or Telegram."""
    today = datetime.date.today().isoformat()
    with store.connect() as conn:
        row = conn.execute("SELECT COUNT(DISTINCT lead_id) n FROM events WHERE at >= ?"
                           " AND kind = ?", (today, f"state:{state}")).fetchone()
    return row["n"]


def whatsapp_today():
    return _sent_today("WHATSAPP_SENT")


def emails_today():
    return _sent_today("EMAIL_SENT")


def already_emailed(lead_id):
    with store.connect() as conn:
        return conn.execute("SELECT 1 FROM events WHERE lead_id = ? AND kind = 'state:EMAIL_SENT'",
                            (lead_id,)).fetchone() is not None


CHANNELS = ("whatsapp", "email", "call", "follow")


def queues():
    """What to do next, in Momo's order: WhatsApp, email, a call, then the one
    follow-up each practice he has spoken to is owed.

    New WhatsApp and email contacts stop at their daily caps. Past a cap that
    queue is empty rather than shorter: new contacts per day is what gets a
    number reported or a Gmail account flagged, and neither is undone easily.
    Returns ({channel: [leads]}, {"messages": n, "emails": n}).
    """
    from . import callmode, outreach
    buckets = store.due_leads()
    sent = {"messages": whatsapp_today(), "emails": emails_today()}
    fresh = lambda rows: [l for l in rows if l["id"] not in callmode._skipped]
    q = {ch: [] for ch in CHANNELS}
    if sent["messages"] < outreach.MAX_WHATSAPP_PER_DAY:
        q["whatsapp"] = [l for l in fresh(buckets["to_whatsapp"])
                         if outreach.whatsapp_message(l, store.findings_of(l))]
    if sent["emails"] < outreach.MAX_EMAIL_PER_DAY:
        q["email"] = [l for l in fresh(buckets["to_email"])
                      if l.get("email") and outreach.email_message(l, store.findings_of(l))]
    q["call"] = fresh(buckets["to_call"])
    q["follow"] = fresh(buckets["to_follow_up"])
    return q, sent


def today():
    from . import outreach
    q, sent = queues()
    channel = next((ch for ch in CHANNELS if q[ch]), None)
    nxt = dict(lead_view(q[channel][0], full=True), channel=channel) if channel else None
    called = calls_today()
    return {"next": nxt, "remaining": sum(len(v) for v in q.values()),
            "done": sent["messages"] + sent["emails"] + called, "goal": DAILY_GOAL,
            "messages": sent["messages"], "message_cap": outreach.MAX_WHATSAPP_PER_DAY,
            "emails": sent["emails"], "email_cap": outreach.MAX_EMAIL_PER_DAY, "calls": called,
            "queued": {ch: len(v) for ch, v in q.items()},
            "counts": store.counts(),
            "date": datetime.date.today().isoformat()}


def send_lead_email(lead_id, subject, body):
    """Send one practice its email, on Momo's tap, with the text he read and
    possibly edited on screen. Returns (status, payload).

    The app is the last screen before this leaves - unlike WhatsApp, where
    WhatsApp itself shows the text before send - so the text sent is exactly
    the text shown, and the footer with the signature and the opt-out line is
    added here, where the phone cannot drop it.
    """
    from . import outreach
    lead = store.get(lead_id)
    subject, body = (subject or "").strip()[:200], (body or "").strip()[:6000]
    if not lead or not lead.get("email"):
        return 404, {"error": "questo studio non ha un'email"}
    if not subject or len(body) < 40:
        return 400, {"error": "oggetto o testo mancante"}
    if "email" not in store.channels_open(lead_id):
        return 409, {"error": "questo studio non è in coda per l'email"}
    with _email_lock:
        if already_emailed(lead_id):
            return 409, {"error": "a questo studio l'email è già partita"}
        if emails_today() >= outreach.MAX_EMAIL_PER_DAY:
            return 429, {"error": f"limite di {outreach.MAX_EMAIL_PER_DAY} email per oggi, il resto domani"}
        try:
            outreach.send_email(lead, subject, body)
        except RuntimeError as e:          # no signature, no address: say which
            return 400, {"error": str(e)[:200]}
        except Exception as e:
            # Gmail may well have accepted it and the failure happened on the
            # way back. "Riprova tra poco" invited a second copy to the same
            # studio, so the lead is marked and the doubt is stated.
            print(f"email to lead {lead_id} unclear: {type(e).__name__}: {e}")
            store.add_note(lead_id, f"invio email incerto ({type(e).__name__}): controlla Gmail Inviati")
            store.set_state(lead_id, "EMAIL_SENT", note="email: esito incerto, da verificare in Gmail")
            return 502, {"error": "Non so se è partita: controlla Posta inviata in Gmail prima di riprovare"}
        store.set_state(lead_id, "EMAIL_SENT", note="email: inviata dall'app")
    # Keep what was actually sent: rebuilding it from the template later shows
    # today's wording, not the words the studio read.
    store.add_note(lead_id, f"EMAIL INVIATA — oggetto: {subject}\n{body}")
    return 200, {"ok": True, "today": today()}


def leads_list(state=None, q=None):
    if state in ("todo", "call"):
        # Exactly the order Oggi serves them - WhatsApp, email, calls, then
        # follow-ups, worst problem first within each - rather than id order,
        # which buried the dead sites.
        queue, _ = queues()
        rows = [dict(r, channel=ch) for ch in CHANNELS for r in queue[ch]]
    else:
        rows = store.list_leads(limit=1000)
    if state and state not in ("all", "todo", "call"):
        rows = [r for r in rows if r["state"] == state]
    if q:
        needle = q.lower()
        rows = [r for r in rows if needle in (r["name"] or "").lower()
                or needle in (r.get("category") or "").lower()]
    return [dict(lead_view(r), channel=r.get("channel")) for r in rows[:300]]


def site_data():
    from . import site
    def compute():
        visitors = site.visitor_stats()
        try:
            search = site.search_stats()
        except Exception as e:
            search = {"error": str(e)[:120]}
        return {"visitors": visitors, "search": search}
    return cached("site", 900, compute)


def system_data():
    from . import health
    def compute():
        model = health.model_check()
        return {"services": health.services(), "memory": health.memory(),
                "disk": health.disk(), "uptime": health.uptime(),
                "model": model, "backup": health.last_backup(),
                "usage": health.router_usage()}
    return cached("system", 60, compute)


# ── Agenti: what the model-driven lab jobs are up to ───────────────────────

# The server-side lab scripts (~/portfolio-lab/ask.py, pilot/common.py -
# not in this repo) append one JSON line here at the start of every router
# call and one at the end, joined by "id". Not the assistant's own router
# usage (that is system_data()/router_usage) - these are Momo's own model
# jobs: pipelines, evals, drafting scripts he runs by hand or from cron.
AGENTS_RUNS_DIR = os.environ.get("AGENTS_RUNS_DIR", "/home/agent/portfolio-lab/runs")
AGENTS_EVENTS_FILE = os.path.join(AGENTS_RUNS_DIR, "events.jsonl")
AGENTS_STALE_SECONDS = 30 * 60
AGENTS_ROUTER_HOST = os.environ.get("ROUTER_HOST", "127.0.0.1")
AGENTS_ROUTER_PORT = int(os.environ.get("ROUTER_PORT", "20128"))


def agents_view(lines, now=None):
    """Pure function: turns the raw lines of events.jsonl into the shape the
    dashboard wants. Tolerant of junk lines, a truncated first line after a
    rotation, and an end line whose start line never arrived (or vice versa).

    Returns {"running": [...], "recent": [...(newest first, capped 60)],
    "pipelines": [{"name", "last_activity", "ok", "errors", "running"}]}.
    """
    now = time.time() if now is None else now
    events, order = {}, []
    for raw in lines:
        raw = (raw or "").strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError):
            continue
        eid = obj.get("id")
        if not eid:
            continue
        if eid not in events:
            events[eid] = {}
            order.append(eid)
        events[eid].update(obj)

    running, recent = [], []
    pipelines = {}

    def bucket(name):
        return pipelines.setdefault(name, {"name": name, "last_activity": 0,
                                           "ok": 0, "errors": 0, "running": 0})

    for eid in order:
        ev = events[eid]
        status = ev.get("status")
        name = ev.get("pipeline") or "unknown"
        p = bucket(name)
        p["last_activity"] = max(p["last_activity"], ev.get("ts_end") or ev.get("ts") or 0)
        if status == "running":
            started = ev.get("ts") or now
            item = dict(ev, pipeline=name, elapsed=round(now - started, 1),
                       stale=(now - started) > AGENTS_STALE_SECONDS)
            running.append(item)
            p["running"] += 1
        elif status in ("ok", "error"):
            started, ended = ev.get("ts"), ev.get("ts_end")
            item = dict(ev, pipeline=name, duration=round(ended - started, 1) if started and ended else None)
            recent.append(item)
            p["ok" if status == "ok" else "errors"] += 1

    running.sort(key=lambda e: e.get("ts") or 0, reverse=True)
    recent.sort(key=lambda e: e.get("ts_end") or e.get("ts") or 0, reverse=True)
    pipeline_list = sorted(pipelines.values(), key=lambda p: p["last_activity"], reverse=True)
    return {"running": running, "recent": recent[:60], "pipelines": pipeline_list}


def _read_events_tail(path, max_bytes=8 * 1024 * 1024):
    """The file can grow between events.jsonl's own rotations; read at most
    the tail of it, dropping a first line that landed mid-write."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()
            data = f.read()
        return data.decode("utf-8", "replace").splitlines()
    except OSError:
        return []


def router_active():
    try:
        with socket.create_connection((AGENTS_ROUTER_HOST, AGENTS_ROUTER_PORT), timeout=1):
            return True
    except OSError:
        return False


def scheduled_jobs():
    """The assistant's own scheduled jobs, if this process happens to have
    them (health.next_jobs() reads an in-process `schedule` registry, so it
    is empty unless something in this process has registered jobs)."""
    try:
        from . import health
        return [{"when": when.isoformat(), "what": what} for when, what in health.next_jobs()]
    except Exception:
        return []


def agents_data():
    view = agents_view(_read_events_tail(AGENTS_EVENTS_FILE))
    view["router"] = {"active": router_active()}
    view["jobs"] = scheduled_jobs()
    return view


# ── HTTP ───────────────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):
    # Without this a client that dribbles its request body holds a thread
    # open indefinitely, and there is no limit on threads.
    timeout = 15

    server_version = "assistant"

    def log_message(self, fmt, *args):   # quiet: no request log in the journal
        pass

    def _cookie(self, name):
        for part in (self.headers.get("Cookie") or "").split(";"):
            key, _, value = part.strip().partition("=")
            if key == name:
                return value
        return None

    def _send(self, status, body, content_type="application/json", headers=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _static(self, name, content_type):
        path = os.path.join(STATIC, name)
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            return self._send(404, {"error": "not found"})
        headers = {"Content-Security-Policy":
                   "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                   "script-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                   "frame-ancestors 'none'"} if name.endswith(".html") else {}
        self._send(200, body, content_type, headers)

    def _authed(self):
        return valid_session(self._cookie("s"))

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 10000:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return {}

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        query = dict(urllib.parse.parse_qsl(url.query))
        statics = {"/": ("index.html", "text/html; charset=utf-8"),
                   "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
                   "/icon.svg": ("icon.svg", "image/svg+xml"),
                   "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
                   "/icon-512.png": ("icon-512.png", "image/png"),
                   "/icon-192.png": ("icon-192.png", "image/png"),
                   "/icon-maskable.png": ("icon-maskable.png", "image/png"),
                   # Android will not offer "Install app" without one.
                   "/sw.js": ("sw.js", "text/javascript")}
        if url.path in statics:
            return self._static(*statics[url.path])
        if url.path == "/api/me":
            return self._send(200, {"authed": self._authed()})
        if not self._authed():
            return self._send(401, {"error": "sign in"})
        try:
            if url.path == "/api/today":
                return self._send(200, today())
            if url.path == "/api/leads":
                return self._send(200, leads_list(query.get("state"), query.get("q")))
            if url.path.startswith("/api/lead/"):
                lead = store.get(int(url.path.rsplit("/", 1)[1]))
                return self._send(200, lead_view(lead, full=True) if lead else {"error": "not found"})
            if url.path.startswith("/api/shot/"):
                # The phone screenshot the scanner took: the proof Momo can
                # look at before writing, and attach to the message.
                path = os.path.join(SHOTS_DIR, f"lead-{int(url.path.rsplit('/', 1)[1])}.png")
                if not os.path.exists(path):
                    return self._send(404, {"error": "not found"})
                with open(path, "rb") as f:
                    return self._send(200, f.read(), "image/png")
            if url.path == "/api/site":
                return self._send(200, site_data())
            if url.path == "/api/system":
                return self._send(200, system_data())
            if url.path == "/api/agents":
                return self._send(200, agents_data())
        except Exception as e:
            print(f"webapp error on {url.path}: {e}")
            return self._send(500, {"error": "server error"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        # CSRF: SameSite=Strict on the cookie, plus a header a cross-site form
        # cannot set.
        if self.headers.get("X-Requested-With") != "app":
            return self._send(403, {"error": "forbidden"})
        body = self._body()

        if url.path == "/api/pair":
            token = redeem_code(str(body.get("code", "")))
            if not token:
                return self._send(401, {"error": "codice non valido o scaduto"})
            cookie = (f"s={token}; Max-Age={SESSION_DAYS * 86400}; Path=/; HttpOnly; "
                      "Secure; SameSite=Strict")
            return self._send(200, {"ok": True}, headers={"Set-Cookie": cookie})

        if not self._authed():
            return self._send(401, {"error": "sign in"})
        try:
            if url.path == "/api/outcome":
                from . import callmode
                channel = body.get("channel")
                label = callmode.apply(int(body["id"]), str(body["action"]),
                                       channel if channel in ("whatsapp", "email") else "call")
                return self._send(200, {"label": label, "today": today()})
            if url.path == "/api/email":
                return self._send(*send_lead_email(int(body["id"]), body.get("subject"), body.get("body")))
            if url.path == "/api/note":
                store.add_note(int(body["id"]), str(body["text"])[:1000])
                return self._send(200, lead_view(store.get(int(body["id"])), full=True))
        except (KeyError, ValueError) as e:
            return self._send(400, {"error": str(e)[:100]})
        except Exception as e:
            print(f"webapp error on {url.path}: {e}")
            return self._send(500, {"error": "server error"})
        self._send(404, {"error": "not found"})


def main():
    server = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"webapp on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
