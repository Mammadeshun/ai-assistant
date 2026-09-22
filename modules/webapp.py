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
SESSION_DAYS = 90
CODE_MINUTES = 10
CODE_TRIES = 5

_cache = {}
_cache_lock = threading.Lock()


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
                "ssl_expiring": "warning", "slow": "warning", "no_website": "neutral"}


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
        view.update(draft=lead.get("draft"), notes=lead.get("notes"),
                    whatsapp=outreach.whatsapp_link(lead, lead.get("draft") or "") if lead.get("whatsapp") else None,
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


def today():
    from . import callmode
    queue = callmode._queue()
    return {"next": lead_view(queue[0], full=True) if queue else None,
            "remaining": len(queue), "done": calls_today(), "goal": DAILY_GOAL,
            "counts": store.counts(),
            "date": datetime.date.today().isoformat()}


def leads_list(state=None, q=None):
    if state == "call":
        # Priority order - worst problem first - exactly as call mode serves
        # them, rather than id order, which buried the dead sites.
        rows = store.due_leads()["to_call"]
    else:
        rows = store.list_leads(limit=1000)
    if state and state not in ("all", "call"):
        rows = [r for r in rows if r["state"] == state]
    if q:
        needle = q.lower()
        rows = [r for r in rows if needle in (r["name"] or "").lower()
                or needle in (r.get("category") or "").lower()]
    return [lead_view(r) for r in rows[:300]]


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


# ── HTTP ───────────────────────────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):
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
                   "/icon-512.png": ("icon-512.png", "image/png")}
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
            if url.path == "/api/site":
                return self._send(200, site_data())
            if url.path == "/api/system":
                return self._send(200, system_data())
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
                label = callmode.apply(int(body["id"]), str(body["action"]))
                return self._send(200, {"label": label, "today": today()})
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
