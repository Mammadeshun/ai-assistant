"""Dashboard v2: the data and the rules behind /v2 (docs/dashboard-v2/SPEC.md).

The webapp turns HTTP into calls here; everything that decides something
lives in this module, so it can be tested without a server.

What it adds on top of the lead store:

  * settings    caps (WhatsApp 0-30, email 0-20), daily goal, pauses and the
                category/city switches, in the existing settings table
  * the queue   replies to handle, overdue follow-ups, follow-ups due today,
                then new leads - one ordered list for Oggi
  * handoffs    "Apri WhatsApp" -> "Hai inviato il messaggio?". Opening
                WhatsApp records nothing; only "Inviato" does, once
  * actions     skip, later today, follow-up dates, reply logging, contact
                edits, "Non contattare" (permanent after a short undo)
  * results     sends per day, reply rates with n, reply quality, follow-ups

Nothing here sends anything. There is no WhatsApp endpoint at all: the phone
opens WhatsApp with the text, and Momo presses send there himself.
"""

import os
import re
import json
import secrets
import datetime
import threading
import urllib.parse

from . import leads as store

# Hard limits (SPEC hard rule 3): the server rejects anything outside them.
WHATSAPP_CAP_MAX = 30
EMAIL_CAP_MAX = 20
GOAL_MAX = 60
DAILY_GOAL = int(os.environ.get("DAILY_CALL_GOAL", "20"))
SETTINGS_KEY = "dashboard_v2"
CHANNELS = ("whatsapp", "email", "call")
PAUSE_KEYS = ("all",) + CHANNELS

# "Non contattare" is written at once; the app offers a 5-second "Annulla".
# The server allows a little more for a slow connection, then never again.
UNDO_SECONDS = 12
# An unconfirmed "Apri WhatsApp" is forgotten after this long.
HANDOFF_HOURS = 12
# "Più tardi oggi": two hours, never past 19:00.
LATER_HOURS = 2
LATER_LATEST_HOUR = 19
# Reply rates only count contacts old enough to have had an answer. The
# queue itself waits WHATSAPP_WAIT_DAYS (2) before moving on; one day more.
MATURE_DAYS = 3
SMALL_N = 10
# Follow-ups after a first contact: the cascade had WhatsApp -> email -> call,
# two more touches. After the second, the lead goes quiet unless Momo sets one.
MAX_FOLLOW_UPS = 2

REPLY_TYPES = {"positive": "Positiva", "question": "Domanda",
               "not_interested": "Non interessato", "wrong_number": "Numero errato"}
STATUS_LABEL = {"NEW": "Nuovo", "WHATSAPP_SENT": "WhatsApp inviato", "EMAIL_SENT": "Email inviata",
                "CALL_DUE": "Da chiamare", "CONTACTED": "Sentito", "INTERESTED": "Interessato",
                "DEAD": "Chiuso"}
# Short, for chips; the full sentence is outreach.PROBLEM_IT.
PROBLEM_SHORT = {
    "site_down": "Non raggiungibile", "domain_gone": "Dominio non attivo",
    "ssl_expired": "Certificato scaduto", "ssl_expiring": "Certificato in scadenza",
    "ssl_wrong_host": "Certificato errato", "not_mobile": "Non adatto al telefono",
    "no_site_found": "Sito assente", "no_website": "Sito assente (da verificare)",
    "mobile_overflow": "Pagina larga sul telefono", "listed_page_gone": "Pagina sparita",
    "slow": "Sito lento", "no_english": "Solo italiano",
}
PROBLEM_TONE = {"site_down": "critical", "ssl_expired": "critical", "domain_gone": "critical",
                "ssl_wrong_host": "critical", "not_mobile": "serious", "ssl_expiring": "warning",
                "slow": "warning"}

_lock = threading.Lock()


# ── small helpers ──────────────────────────────────────────────────────────

def _now(now=None):
    return now or datetime.datetime.now()


def _iso(dt):
    return dt.isoformat(timespec="seconds") if dt else None


def _dt(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _date(value):
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def business_day(day):
    """Practices are shut at weekends: a default follow-up that lands on one
    moves to Monday."""
    if day.weekday() == 5:
        return day + datetime.timedelta(days=2)
    if day.weekday() == 6:
        return day + datetime.timedelta(days=1)
    return day


def _log(conn, lead_id, kind, detail, now):
    conn.execute("INSERT INTO events (lead_id, at, kind, detail) VALUES (?,?,?,?)",
                 (lead_id, _iso(now), kind, detail))


def _update(lead_id, now, event=None, **fields):
    """Set columns on one lead and optionally log one event, in one commit."""
    with store.connect() as conn:
        if fields:
            cols = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(f"UPDATE leads SET {cols} WHERE id = ?", (*fields.values(), lead_id))
        if event:
            _log(conn, lead_id, event[0], event[1], now)


def _source_label(lead):
    src = lead.get("source") or ""
    if src.startswith("osm:"):
        return "OpenStreetMap"
    if src in ("demo", "manual"):
        return "Inserito a mano" if src == "manual" else "Dati di prova"
    return "Contatti pubblici"


def _problem(lead):
    from . import outreach
    findings = store.findings_of(lead)
    if not findings:
        return None
    # The worst sendable finding names the problem; fall back to the first.
    ranked = sorted(findings, key=lambda f: outreach.severity_now(f), reverse=True)
    code = ranked[0]["code"]
    return {"code": code, "label": PROBLEM_SHORT.get(code, code),
            "text": outreach.PROBLEM_IT.get(code, code),
            "tone": PROBLEM_TONE.get(code, "neutral"),
            "sendable": outreach.severity_now(ranked[0]) >= 2,
            "verified_at": lead.get("scanned_at")}


def _number(lead):
    """What to dial: the listed phone, else the mobile."""
    raw = lead.get("phone") or (("+" + lead["whatsapp"]) if lead.get("whatsapp") else "")
    return "".join(c for c in raw if c.isdigit() or c == "+") or None


# ── settings ───────────────────────────────────────────────────────────────

def _default_settings():
    from . import outreach
    return {"cap_whatsapp": max(0, min(int(outreach.MAX_WHATSAPP_PER_DAY), WHATSAPP_CAP_MAX)),
            "cap_email": max(0, min(int(outreach.MAX_EMAIL_PER_DAY), EMAIL_CAP_MAX)),
            "goal": max(0, min(DAILY_GOAL, GOAL_MAX)),
            "pause": {k: None for k in PAUSE_KEYS},
            "off_categories": [], "off_cities": []}


def settings():
    """Stored settings over the defaults. A stored value outside the limits
    (edited by hand, or from before a limit changed) is clamped, never used."""
    s = _default_settings()
    try:
        stored = json.loads(store.get_setting(SETTINGS_KEY, "{}") or "{}")
    except ValueError:
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
    for key, top in (("cap_whatsapp", WHATSAPP_CAP_MAX), ("cap_email", EMAIL_CAP_MAX), ("goal", GOAL_MAX)):
        if isinstance(stored.get(key), int) and not isinstance(stored.get(key), bool):
            s[key] = max(0, min(stored[key], top))
    pause = stored.get("pause") if isinstance(stored.get("pause"), dict) else {}
    for k in PAUSE_KEYS:
        v = pause.get(k)
        s["pause"][k] = v if (v == "manual" or _dt(v)) else None
    for key in ("off_categories", "off_cities"):
        if isinstance(stored.get(key), list):
            s[key] = [str(x)[:80] for x in stored[key] if isinstance(x, str)][:200]
    return s


def caps():
    s = settings()
    return {"whatsapp": s["cap_whatsapp"], "email": s["cap_email"]}


def paused(channel, s=None, now=None):
    """True when outreach on `channel` is paused, by its own switch or "all"."""
    s = s or settings()
    now = _now(now)
    for key in ("all", channel):
        v = s["pause"].get(key)
        if v == "manual":
            return True
        until = _dt(v)
        if until and now < until:
            return True
    return False


def _as_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d{1,4}", value.strip()):
        return int(value.strip())
    return None


def update_settings(body, now=None):
    """Validate and store a partial update. Returns (status, payload).
    Out-of-range caps are refused, not clamped: 31 WhatsApp is an error."""
    now = _now(now)
    if not isinstance(body, dict):
        return 400, {"error": "richiesta non valida"}
    s = settings()
    errors = {}
    limits = {"cap_whatsapp": (WHATSAPP_CAP_MAX, "WhatsApp: da 0 a 30 al giorno"),
              "cap_email": (EMAIL_CAP_MAX, "Email: da 0 a 20 al giorno"),
              "goal": (GOAL_MAX, "Obiettivo: da 0 a 60 contatti al giorno")}
    for key, (top, message) in limits.items():
        if key in body:
            v = _as_int(body[key])
            if v is None or not 0 <= v <= top:
                errors[key] = message
            else:
                s[key] = v
    if "pause" in body:
        pause = body["pause"]
        if not isinstance(pause, dict):
            errors["pause"] = "pausa non valida"
        else:
            for key, value in pause.items():
                if key not in PAUSE_KEYS:
                    errors["pause"] = "canale sconosciuto"
                    continue
                if value in (None, "", "off"):
                    s["pause"][key] = None
                elif value == "manual":
                    s["pause"][key] = "manual"
                elif value == "today":
                    tomorrow = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    s["pause"][key] = _iso(tomorrow)
                else:
                    day = _date(value) if isinstance(value, str) and len(value) == 10 else None
                    if not day or day <= now.date() or day > now.date() + datetime.timedelta(days=365):
                        errors["pause"] = "data di ripresa non valida"
                    else:
                        s["pause"][key] = _iso(datetime.datetime.combine(day, datetime.time()))
    if "coverage" in body:
        cov = body["coverage"]
        if not isinstance(cov, dict) or cov.get("kind") not in ("category", "city") \
                or not isinstance(cov.get("name"), str) or not cov["name"].strip() \
                or not isinstance(cov.get("on"), bool):
            errors["coverage"] = "interruttore non valido"
        else:
            key = "off_categories" if cov["kind"] == "category" else "off_cities"
            name = cov["name"].strip()[:80]
            off = [x for x in s[key] if x != name]
            if not cov["on"]:
                off.append(name)
            s[key] = off[:200]
    if errors:
        return 400, {"error": next(iter(errors.values())), "fields": errors}
    store.set_setting(SETTINGS_KEY, json.dumps(s))
    return 200, settings_view(now)


def settings_view(now=None):
    now = _now(now)
    s = settings()
    pause = {}
    for key in PAUSE_KEYS:
        v = s["pause"][key]
        until = _dt(v)
        active = v == "manual" or bool(until and now < until)
        pause[key] = {"on": active, "manual": v == "manual", "until": _iso(until) if active and until else None}
    with store.connect() as conn:
        cats = conn.execute("SELECT COALESCE(category, '') name, COUNT(*) n,"
                            " SUM(state = 'NEW') unsent FROM leads GROUP BY 1 ORDER BY n DESC").fetchall()
        cities = conn.execute("SELECT COALESCE(city, '') name, COUNT(*) n,"
                              " SUM(state = 'NEW') unsent FROM leads GROUP BY 1 ORDER BY n DESC").fetchall()

    def switches(rows, off, limit):
        out = [{"name": r["name"], "count": r["n"], "unsent": r["unsent"] or 0, "on": r["name"] not in off}
               for r in rows if r["name"]]
        shown = out[:limit] + [x for x in out[limit:] if not x["on"]]
        return shown
    from . import outreach
    return {"cap_whatsapp": s["cap_whatsapp"], "cap_email": s["cap_email"], "goal": s["goal"],
            "limits": {"cap_whatsapp": WHATSAPP_CAP_MAX, "cap_email": EMAIL_CAP_MAX, "goal": GOAL_MAX},
            "defaults": {"cap_whatsapp": min(int(outreach.MAX_WHATSAPP_PER_DAY), WHATSAPP_CAP_MAX),
                         "cap_email": min(int(outreach.MAX_EMAIL_PER_DAY), EMAIL_CAP_MAX),
                         "goal": min(DAILY_GOAL, GOAL_MAX)},
            "pause": pause,
            "categories": switches(cats, s["off_categories"], 30),
            "cities": switches(cities, s["off_cities"], 40)}


# ── counters ───────────────────────────────────────────────────────────────

# A WhatsApp counts against the day's cap whether it was the first message or
# a follow-up; a reply to someone who wrote first does not.
WA_KINDS = ("state:WHATSAPP_SENT", "send:whatsapp")


def _day_bounds(day):
    return day.isoformat(), (day + datetime.timedelta(days=1)).isoformat()


def count_whatsapp(day):
    lo, hi = _day_bounds(day)
    with store.connect() as conn:
        return conn.execute("SELECT COUNT(DISTINCT lead_id) n FROM events WHERE at >= ? AND at < ?"
                            " AND kind IN (?, ?)", (lo, hi, *WA_KINDS)).fetchone()["n"]


def count_email(day):
    lo, hi = _day_bounds(day)
    with store.connect() as conn:
        return conn.execute("SELECT COUNT(DISTINCT lead_id) n FROM events WHERE at >= ? AND at < ?"
                            " AND kind = 'state:EMAIL_SENT'", (lo, hi)).fetchone()["n"]


def count_calls(day):
    lo, hi = _day_bounds(day)
    with store.connect() as conn:
        return conn.execute(
            "SELECT COUNT(DISTINCT lead_id) n FROM events WHERE at >= ? AND at < ? AND"
            " (kind = 'attempt' OR (kind LIKE 'state:%' AND detail LIKE 'chiamata%'))", (lo, hi)).fetchone()["n"]


def already_emailed(lead_id):
    with store.connect() as conn:
        return conn.execute("SELECT 1 FROM events WHERE lead_id = ? AND kind = 'state:EMAIL_SENT'",
                            (lead_id,)).fetchone() is not None


# ── handoffs ───────────────────────────────────────────────────────────────

def _expire_handoffs(now):
    cutoff = _iso(now - datetime.timedelta(hours=HANDOFF_HOURS))
    with store.connect() as conn:
        conn.execute("UPDATE handoffs SET status = 'expired', resolved_at = ? WHERE status = 'open'"
                     " AND created_at < ?", (_iso(now), cutoff))


def _open_handoff():
    with store.connect() as conn:
        row = conn.execute("SELECT * FROM handoffs WHERE status = 'open' ORDER BY created_at DESC LIMIT 1").fetchone()
        return dict(row) if row else None


def _reserved_whatsapp(now, except_lead=None):
    """Open WhatsApp handoffs that will count once confirmed: they hold a
    place under the cap, so two quick launches cannot both pass at 24/25."""
    with store.connect() as conn:
        rows = conn.execute("SELECT lead_id FROM handoffs WHERE status = 'open' AND channel = 'whatsapp'"
                            " AND kind IN ('first', 'follow_up') AND created_at >= ?",
                            (now.date().isoformat(),)).fetchall()
    return len({r["lead_id"] for r in rows if r["lead_id"] != except_lead})


def pending_view(now=None):
    now = _now(now)
    _expire_handoffs(now)
    h = _open_handoff()
    if not h:
        return None
    lead = store.get(h["lead_id"])
    if not lead:
        return None
    return {"key": h["key"], "channel": h["channel"], "kind": h["kind"], "created_at": h["created_at"],
            "lead_id": lead["id"], "name": lead["name"],
            "number": _number(lead) if h["channel"] == "call" else lead.get("whatsapp"),
            "link": _handoff_links(lead, h["channel"], h["message"])[0],
            "web_link": _handoff_links(lead, h["channel"], h["message"])[1]}


def _handoff_links(lead, channel, text):
    if channel == "call":
        number = _number(lead)
        return (f"tel:{number}" if number else None), None
    number = (lead.get("whatsapp") or "").lstrip("+").replace(" ", "")
    if not number:
        return None, None
    if text:
        q = urllib.parse.quote(text)
        return f"whatsapp://send?phone={number}&text={q}", f"https://wa.me/{number}?text={q}"
    return f"whatsapp://send?phone={number}", f"https://wa.me/{number}"


def compose_whatsapp(lead, body, now=None):
    """The first message as it will open in WhatsApp: the fixed intro, Momo's
    middle, the fixed closing. Returns (text, error)."""
    from . import outreach
    now = _now(now)
    parts = outreach.whatsapp_parts(lead, store.findings_of(lead), hour=now.hour)
    if not parts:
        return None, "Per questo studio non c'è un problema verificato da scrivere"
    middle = parts["body"] if body is None else str(body)
    middle = middle.replace("\r\n", "\n").strip()
    if len(middle) < 10:
        return None, "Il messaggio è vuoto: scrivi almeno una frase"
    if len(middle) > 1500:
        return None, "Il messaggio è troppo lungo (massimo 1500 caratteri)"
    text = "\n\n".join((parts["intro"], middle, parts["closing"]))
    missing = outreach.missing_clauses(text)
    if missing:
        return None, "Mancano le frasi obbligatorie: chi sei, dove hai trovato il numero, come smettere"
    return text, None


def start_handoff(lead_id, body, now=None):
    """Validate an "Apri WhatsApp" (or "Chiama") and hold it open until Momo
    says what happened. Returns (status, payload) with the link to open.
    Nothing is recorded as sent here."""
    now = _now(now)
    body = body if isinstance(body, dict) else {}
    channel, kind = body.get("channel"), body.get("kind") or "first"
    if channel not in ("whatsapp", "call") or kind not in ("first", "follow_up", "reply"):
        return 400, {"error": "richiesta non valida"}
    with _lock:
        lead = store.get(lead_id)
        if not lead:
            return 404, {"error": "studio non trovato"}
        if lead.get("do_not_contact_at"):
            return 409, {"error": "Questo studio è segnato Non contattare"}
        _expire_handoffs(now)
        pend = _open_handoff()
        if pend and pend["lead_id"] != lead_id:
            other = store.get(pend["lead_id"]) or {"name": "lo studio precedente"}
            prep = "ad" if other["name"][:1] in "aA" else "a"
            return 409, {"error": f"Prima di aprirne un altro: hai scritto {prep} {other['name']}?",
                         "pending": pending_view(now)}
        s = settings()
        text = None
        if channel == "whatsapp":
            if not lead.get("whatsapp"):
                return 409, {"error": "Nessun cellulare per WhatsApp"}
            if lead.get("phone_invalid_at"):
                return 409, {"error": "Numero segnato come errato: correggilo nei contatti"}
            if kind != "reply" and paused("whatsapp", s, now):
                return 409, {"error": "WhatsApp è in pausa"}
            if kind == "first":
                if lead["state"] != "NEW" or "whatsapp" not in store.channels_open(lead_id):
                    return 409, {"error": "Questo studio non è in coda per il primo messaggio"}
                text, error = compose_whatsapp(lead, body.get("body"), now)
                if error:
                    return 400, {"error": error}
            elif lead["state"] == "NEW":
                return 409, {"error": "Prima serve il primo messaggio"}
            if kind != "reply":
                sent, cap = count_whatsapp(now.date()), s["cap_whatsapp"]
                if sent + _reserved_whatsapp(now, except_lead=lead_id) >= cap:
                    return 429, {"error": f"Limite WhatsApp di oggi raggiunto: {sent}/{cap}"}
        else:
            if not _number(lead):
                return 409, {"error": "Nessun numero da chiamare"}
            if lead.get("phone_invalid_at"):
                return 409, {"error": "Numero segnato come errato: correggilo nei contatti"}
            if kind != "reply" and paused("call", s, now):
                return 409, {"error": "Le chiamate sono in pausa"}
        with store.connect() as conn:
            if pend and pend["lead_id"] == lead_id:
                key = pend["key"]
                conn.execute("UPDATE handoffs SET channel = ?, kind = ?, message = ?, created_at = ? WHERE key = ?",
                             (channel, kind, text, _iso(now), key))
            else:
                key = secrets.token_urlsafe(12)
                conn.execute("INSERT INTO handoffs (key, lead_id, channel, kind, created_at, status, message)"
                             " VALUES (?,?,?,?,?,'open',?)", (key, lead_id, channel, kind, _iso(now), text))
        link, web = _handoff_links(lead, channel, text)
        return 200, {"key": key, "channel": channel, "kind": kind, "lead_id": lead_id, "name": lead["name"],
                     "link": link, "web_link": web}


def _follow_up_was_due(lead, today):
    due = _date(lead.get("follow_up_at"))
    if due and due <= today:
        return due
    if not lead.get("follow_up_at") and not lead.get("follow_up_off_at"):
        legacy = legacy_due(lead)
        if legacy and legacy <= today:
            return legacy
    return None


def _set_default_follow_up(lead_id, days, now, conn):
    if days is None:
        conn.execute("UPDATE leads SET follow_up_at = NULL, follow_up_off_at = ? WHERE id = ?", (_iso(now), lead_id))
        return None
    day = business_day(now.date() + datetime.timedelta(days=days))
    conn.execute("UPDATE leads SET follow_up_at = ?, follow_up_off_at = NULL WHERE id = ?", (day.isoformat(), lead_id))
    _log(conn, lead_id, "follow_up_set", f"{day.isoformat()} (automatico)", now)
    return day


def default_follow_up_days(action, follow_ups=0):
    """The follow-up a send leaves behind, from the waits the queue already
    uses: WHATSAPP_WAIT_DAYS after a first WhatsApp, EMAIL_WAIT_DAYS after an
    email, FOLLOW_UP_DAYS after a conversation or a follow-up - and nothing
    after MAX_FOLLOW_UPS follow-ups."""
    if action == "first_whatsapp":
        return store.WHATSAPP_WAIT_DAYS
    if action == "first_email":
        return store.EMAIL_WAIT_DAYS
    if action in ("contacted", "reply_handled"):
        return store.FOLLOW_UP_DAYS
    if action == "follow_up":
        return store.FOLLOW_UP_DAYS if follow_ups < MAX_FOLLOW_UPS else None
    if action in ("call_later", "no_answer"):
        return 1
    return None


def after_email_sent(lead_id, now=None):
    """Called by the existing email send once it succeeded: close a due
    follow-up and leave the default next one."""
    now = _now(now)
    lead = store.get(lead_id)
    if not lead:
        return
    with store.connect() as conn:
        due = _follow_up_was_due(lead, now.date())
        if due and lead["state"] != "NEW":
            _log(conn, lead_id, "follow_up_done", json.dumps({"due": due.isoformat(), "on": now.date().isoformat()}), now)
        conn.execute("UPDATE leads SET snoozed_until = NULL, skipped_at = NULL WHERE id = ?", (lead_id,))
        _set_default_follow_up(lead_id, default_follow_up_days("first_email"), now, conn)


def resolve_handoff(key, body, now=None):
    """Momo's answer to "Hai inviato il messaggio?" (or how the call went).
    Idempotent: a second "Inviato" for the same handoff records nothing."""
    now = _now(now)
    body = body if isinstance(body, dict) else {}
    result = body.get("result")
    with _lock:
        with store.connect() as conn:
            row = conn.execute("SELECT * FROM handoffs WHERE key = ?", (str(key),)).fetchone()
        if not row:
            return 404, {"error": "richiesta non trovata"}
        h = dict(row)
        if h["status"] != "open":
            return 200, {"ok": True, "already": h["status"]}
        lead = store.get(h["lead_id"])
        if not lead or lead.get("do_not_contact_at"):
            with store.connect() as conn:
                conn.execute("UPDATE handoffs SET status = 'cancelled', resolved_at = ? WHERE key = ?", (_iso(now), key))
            return 409, {"error": "Questo studio è segnato Non contattare"}
        if h["channel"] == "whatsapp":
            if result not in ("sent", "not_sent", "later"):
                return 400, {"error": "risposta non valida"}
            label = _resolve_whatsapp(lead, h, result, now)
            status = result
        else:
            outcome = body.get("outcome")
            if result != "call" or outcome not in ("ok", "hot", "later", "noanswer", "no", "none"):
                return 400, {"error": "esito non valido"}
            label = _resolve_call(lead, h, outcome, now)
            status = "call:" + outcome
        with store.connect() as conn:
            conn.execute("UPDATE handoffs SET status = ?, resolved_at = ? WHERE key = ? AND status = 'open'",
                         (status, _iso(now), key))
        after = store.get(h["lead_id"]) or {}
        return 200, {"ok": True, "label": label, "lead_id": h["lead_id"], "name": lead["name"],
                     "follow_up_at": after.get("follow_up_at"), "snoozed_until": after.get("snoozed_until")}


def _resolve_whatsapp(lead, h, result, now):
    lead_id, today = lead["id"], now.date()
    if result == "not_sent":
        _update(lead_id, now, event=("not_sent:whatsapp", "aperto dall'app, non inviato"))
        return "Non inviato"
    if result == "later":
        until = later_today(now)
        _update(lead_id, now, event=("snooze", _iso(until)), snoozed_until=_iso(until))
        return "Più tardi"
    if h["kind"] == "first":
        store.set_state(lead_id, "WHATSAPP_SENT", note="whatsapp: inviato dall'app")
        with store.connect() as conn:
            conn.execute("UPDATE leads SET snoozed_until = NULL, skipped_at = NULL WHERE id = ?", (lead_id,))
            _set_default_follow_up(lead_id, default_follow_up_days("first_whatsapp"), now, conn)
        return "Inviato"
    if h["kind"] == "reply":
        with store.connect() as conn:
            conn.execute("UPDATE leads SET reply_todo_at = NULL, snoozed_until = NULL, skipped_at = NULL"
                         " WHERE id = ?", (lead_id,))
            _log(conn, lead_id, "reply_handled", "whatsapp", now)
            _set_default_follow_up(lead_id, default_follow_up_days("reply_handled"), now, conn)
        return "Risposto"
    # follow-up
    with store.connect() as conn:
        due = _follow_up_was_due(lead, today)
        _log(conn, lead_id, "send:whatsapp", "follow-up", now)
        if due:
            _log(conn, lead_id, "follow_up_done", json.dumps({"due": due.isoformat(), "on": today.isoformat()}), now)
        conn.execute("UPDATE leads SET follow_ups = follow_ups + 1, snoozed_until = NULL, skipped_at = NULL"
                     " WHERE id = ?", (lead_id,))
        _set_default_follow_up(lead_id, default_follow_up_days("follow_up", (lead.get("follow_ups") or 0) + 1), now, conn)
    return "Inviato"


def _resolve_call(lead, h, outcome, now):
    from . import callmode
    lead_id, today = lead["id"], now.date()
    if outcome == "none":
        return "Non chiamato"
    due = _follow_up_was_due(lead, today) if lead["state"] != "NEW" else None
    label = callmode.apply(lead_id, outcome, "call")
    after = store.get(lead_id)
    with store.connect() as conn:
        if outcome in ("ok", "hot", "later", "no") and due:
            _log(conn, lead_id, "follow_up_done", json.dumps({"due": due.isoformat(), "on": today.isoformat()}), now)
        conn.execute("UPDATE leads SET snoozed_until = NULL, skipped_at = NULL WHERE id = ?", (lead_id,))
        if outcome in ("ok", "hot", "later") and after.get("reply_todo_at"):
            conn.execute("UPDATE leads SET reply_todo_at = NULL WHERE id = ?", (lead_id,))
            _log(conn, lead_id, "reply_handled", "call", now)
        if outcome == "no" or after["state"] == "DEAD":
            conn.execute("UPDATE leads SET follow_up_at = NULL, reply_todo_at = NULL, follow_up_off_at = ?"
                         " WHERE id = ?", (_iso(now), lead_id))
        elif outcome in ("ok", "hot"):
            _set_default_follow_up(lead_id, default_follow_up_days("contacted"), now, conn)
        elif outcome == "later":
            _set_default_follow_up(lead_id, default_follow_up_days("call_later"), now, conn)
        elif outcome == "noanswer" and lead["state"] != "NEW":
            _set_default_follow_up(lead_id, default_follow_up_days("no_answer"), now, conn)
    return label


# ── one-tap actions ────────────────────────────────────────────────────────

def later_today(now=None):
    """Two hours from now, never past 19:00. Too late for that: tomorrow 9:00."""
    now = _now(now).replace(microsecond=0)
    until = now + datetime.timedelta(hours=LATER_HOURS)
    latest = now.replace(hour=LATER_LATEST_HOUR, minute=0, second=0)
    if until > latest:
        until = latest
    if until <= now + datetime.timedelta(minutes=15):
        until = (now + datetime.timedelta(days=1)).replace(hour=9, minute=0, second=0)
    return until


def _lead_or_404(lead_id, allow_dnc=False):
    lead = store.get(lead_id)
    if not lead:
        return None, (404, {"error": "studio non trovato"})
    if not allow_dnc and lead.get("do_not_contact_at"):
        return None, (409, {"error": "Questo studio è segnato Non contattare"})
    return lead, None


def skip(lead_id, now=None):
    """To the end of today's queue; status and counters untouched."""
    now = _now(now)
    lead, err = _lead_or_404(lead_id)
    if err:
        return err
    _update(lead_id, now, event=("skip", None), skipped_at=_iso(now))
    return 200, {"ok": True}


def snooze(lead_id, body, now=None):
    now = _now(now)
    body = body if isinstance(body, dict) else {}
    lead, err = _lead_or_404(lead_id)
    if err:
        return err
    if body.get("preset", "later") == "later" and not body.get("until"):
        until = later_today(now)
    else:
        until = _dt(body.get("until"))
        if not until or until <= now or until > now + datetime.timedelta(days=30):
            return 400, {"error": "orario non valido"}
    _update(lead_id, now, event=("snooze", _iso(until)), snoozed_until=_iso(until))
    return 200, {"ok": True, "until": _iso(until)}


def set_follow_up(lead_id, body, now=None):
    """Set, move or remove the follow-up date."""
    now = _now(now)
    body = body if isinstance(body, dict) else {}
    lead, err = _lead_or_404(lead_id)
    if err:
        return err
    if lead["state"] == "DEAD":
        return 409, {"error": "Studio chiuso: niente follow-up"}
    if lead["state"] == "NEW":
        # Not contacted yet, so nothing to follow up: "Più tardi" moves it.
        return 409, {"error": "Prima serve il primo contatto"}
    today = now.date()
    if body.get("remove"):
        _update(lead_id, now, event=("follow_up_off", None), follow_up_at=None, follow_up_off_at=_iso(now))
        return 200, {"ok": True, "follow_up_at": None}
    preset = body.get("preset")
    if preset in ("today", "tomorrow", "3days"):
        day = today + datetime.timedelta(days={"today": 0, "tomorrow": 1, "3days": 3}[preset])
    else:
        day = _date(body.get("date")) if isinstance(body.get("date"), str) and len(body["date"]) == 10 else None
        if not day or day < today or day > today + datetime.timedelta(days=365):
            return 400, {"error": "data non valida"}
    _update(lead_id, now, event=("follow_up_set", day.isoformat()),
            follow_up_at=day.isoformat(), follow_up_off_at=None)
    return 200, {"ok": True, "follow_up_at": day.isoformat()}


def do_not_contact(lead_id, reason=None, now=None):
    """Permanent, on every channel. Written at once; undo_do_not_contact()
    can take it back for UNDO_SECONDS, never after."""
    now = _now(now)
    with _lock:
        lead = store.get(lead_id)
        if not lead:
            return 404, {"error": "studio non trovato"}
        if lead.get("do_not_contact_at"):
            return 200, {"ok": True, "already": True}
        prev = {k: lead.get(k) for k in ("state", "state_changed_at", "follow_up_at", "follow_up_off_at",
                                         "reply_todo_at", "snoozed_until")}
        reason = (str(reason).strip()[:200] if reason else "") or "segnato dall'app"
        with store.connect() as conn:
            conn.execute("UPDATE leads SET do_not_contact_at = ?, do_not_contact_reason = ?, follow_up_at = NULL,"
                         " reply_todo_at = NULL, snoozed_until = NULL WHERE id = ?", (_iso(now), reason, lead_id))
            _log(conn, lead_id, "dnc", json.dumps({"reason": reason, "prev": prev}), now)
            conn.execute("UPDATE handoffs SET status = 'cancelled', resolved_at = ? WHERE lead_id = ?"
                         " AND status = 'open'", (_iso(now), lead_id))
        if lead["state"] != "DEAD":
            store.set_state(lead_id, "DEAD", note="non contattare")
    return 200, {"ok": True, "undo_seconds": 5}


def undo_do_not_contact(lead_id, now=None):
    now = _now(now)
    with _lock:
        lead = store.get(lead_id)
        if not lead:
            return 404, {"error": "studio non trovato"}
        at = _dt(lead.get("do_not_contact_at"))
        if not at:
            return 409, {"error": "Niente da annullare"}
        if (now - at).total_seconds() > UNDO_SECONDS:
            return 409, {"error": "Troppo tardi: resta Non contattare"}
        with store.connect() as conn:
            row = conn.execute("SELECT detail FROM events WHERE lead_id = ? AND kind = 'dnc' ORDER BY id DESC LIMIT 1",
                               (lead_id,)).fetchone()
            try:
                prev = json.loads(row["detail"])["prev"] if row else {}
            except (ValueError, KeyError, TypeError):
                prev = {}
            conn.execute("UPDATE leads SET do_not_contact_at = NULL, do_not_contact_reason = NULL, state = ?,"
                         " state_changed_at = ?, follow_up_at = ?, follow_up_off_at = ?, reply_todo_at = ?,"
                         " snoozed_until = ? WHERE id = ?",
                         (prev.get("state") or lead["state"], prev.get("state_changed_at") or lead["state_changed_at"],
                          prev.get("follow_up_at"), prev.get("follow_up_off_at"), prev.get("reply_todo_at"),
                          prev.get("snoozed_until"), lead_id))
            _log(conn, lead_id, "dnc_undo", None, now)
    return 200, {"ok": True}


def log_reply(lead_id, body, now=None):
    """A reply that came in, logged by hand, and the next action it sets:

        positive        -> Interessato, "Rispondere oggi"
        question        -> still active, "Rispondere oggi"
        not_interested  -> closed, follow-ups cancelled; opt_out adds Non contattare
        wrong_number    -> phone/WhatsApp invalid; a non-PEC email stays usable
    """
    now = _now(now)
    body = body if isinstance(body, dict) else {}
    kind = body.get("type")
    if kind not in REPLY_TYPES:
        return 400, {"error": "tipo di risposta non valido"}
    via = body.get("channel") if body.get("channel") in CHANNELS else "whatsapp"
    lead, err = _lead_or_404(lead_id)
    if err:
        return err
    stamp = _iso(now)
    note = f"risposta {REPLY_TYPES[kind].lower()} ({via})"
    with store.connect() as conn:
        conn.execute("UPDATE leads SET reply_type = ?, reply_at = ?, snoozed_until = NULL, skipped_at = NULL"
                     " WHERE id = ?", (kind, stamp, lead_id))
        _log(conn, lead_id, f"reply:{kind}", via, now)
        conn.execute("UPDATE handoffs SET status = 'cancelled', resolved_at = ? WHERE lead_id = ? AND status = 'open'",
                     (stamp, lead_id))
    if kind == "positive":
        if lead["state"] != "INTERESTED":
            store.set_state(lead_id, "INTERESTED", note=note)
        _update(lead_id, now, reply_todo_at=stamp, follow_up_at=None)
    elif kind == "question":
        if lead["state"] in store.OPEN_STATES:
            store.set_state(lead_id, "CONTACTED", note=note)
        _update(lead_id, now, reply_todo_at=stamp, follow_up_at=None)
    elif kind == "not_interested":
        if lead["state"] != "DEAD":
            store.set_state(lead_id, "DEAD", note=note)
        _update(lead_id, now, reply_todo_at=None, follow_up_at=None, follow_up_off_at=stamp)
        if body.get("opt_out"):
            do_not_contact(lead_id, "ha chiesto di non essere ricontattato", now)
    elif kind == "wrong_number":
        fresh = store.get(lead_id)
        if fresh["state"] == "NEW":
            # Never written to: the queue routes it to email by itself.
            _update(lead_id, now, phone_invalid_at=stamp, reply_todo_at=None)
        elif store.emailable(fresh) and not already_emailed(lead_id):
            _update(lead_id, now, phone_invalid_at=stamp, reply_todo_at=None,
                    follow_up_at=now.date().isoformat(), follow_up_off_at=None)
        else:
            _update(lead_id, now, phone_invalid_at=stamp, reply_todo_at=None,
                    follow_up_at=None, follow_up_off_at=stamp)
    return 200, {"ok": True, "lead": lead_detail(lead_id, now)}


def reply_done(lead_id, body=None, now=None):
    """Momo answered a reply outside the app's handoff (from his phone, say)."""
    now = _now(now)
    body = body if isinstance(body, dict) else {}
    lead, err = _lead_or_404(lead_id)
    if err:
        return err
    if not lead.get("reply_todo_at"):
        return 200, {"ok": True, "already": True}
    via = body.get("channel") if body.get("channel") in CHANNELS else "whatsapp"
    with store.connect() as conn:
        conn.execute("UPDATE leads SET reply_todo_at = NULL, snoozed_until = NULL, skipped_at = NULL WHERE id = ?",
                     (lead_id,))
        _log(conn, lead_id, "reply_handled", via, now)
        _set_default_follow_up(lead_id, default_follow_up_days("reply_handled"), now, conn)
    return 200, {"ok": True}


EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,120}\.[a-z]{2,24}$", re.I)


def edit_contact(lead_id, body, now=None):
    """Phone, mobile, email, website, PEC flag. The old value stays in the
    history; a changed website is rescanned before anyone writes about it."""
    now = _now(now)
    body = body if isinstance(body, dict) else {}
    lead, err = _lead_or_404(lead_id, allow_dnc=True)
    if err:
        return err
    from .commands import mobile_number
    changes, events, errors = {}, [], {}

    def text(key, limit):
        v = body.get(key)
        return None if v is None else str(v).strip()[:limit]

    phone = text("phone", 40)
    if phone is not None:
        digits = "".join(c for c in phone if c.isdigit())
        if phone and (not re.fullmatch(r"[+\d\s()./-]+", phone) or not 6 <= len(digits) <= 15):
            errors["phone"] = "Telefono non valido"
        elif (phone or None) != lead.get("phone"):
            changes["phone"] = phone or None
            events.append(("edit:phone", f"{lead.get('phone') or '—'} → {phone or '—'}"))
    mobile = text("whatsapp", 40)
    if mobile is not None:
        normalized = mobile_number(mobile) if mobile else None
        if mobile and not normalized:
            errors["whatsapp"] = "Serve un cellulare italiano (3xx...)"
        elif normalized != lead.get("whatsapp"):
            changes["whatsapp"] = normalized
            events.append(("edit:whatsapp", f"{lead.get('whatsapp') or '—'} → {normalized or '—'}"))
    email = text("email", 190)
    if email is not None:
        if email and not EMAIL_RE.match(email):
            errors["email"] = "Email non valida"
        elif (email or None) != lead.get("email"):
            changes["email"] = email or None
            events.append(("edit:email", f"{lead.get('email') or '—'} → {email or '—'}"))
    website = text("website", 200)
    if website is not None:
        url = website if (not website or "://" in website) else "https://" + website
        host = urllib.parse.urlparse(url).hostname if url else None
        if website and (not host or "." not in host or " " in website):
            errors["website"] = "Sito non valido"
        elif (url or None) != lead.get("website"):
            changes["website"] = url or None
            changes["scanned_at"] = None      # a claim about the new site needs a new scan
            events.append(("edit:website", f"{lead.get('website') or '—'} → {url or '—'}"))
    if "email_pec" in body:
        if not isinstance(body["email_pec"], bool):
            errors["email_pec"] = "valore non valido"
        elif int(body["email_pec"]) != int(lead.get("email_is_pec") or 0):
            changes["email_is_pec"] = int(body["email_pec"])
            events.append(("edit:email_pec", "PEC" if body["email_pec"] else "non PEC"))
    if errors:
        return 400, {"error": next(iter(errors.values())), "fields": errors}
    if "phone" in changes or "whatsapp" in changes:
        changes["phone_invalid_at"] = None
    if changes:
        with store.connect() as conn:
            cols = ", ".join(f"{k} = ?" for k in changes)
            conn.execute(f"UPDATE leads SET {cols} WHERE id = ?", (*changes.values(), lead_id))
            for kind, detail in events:
                _log(conn, lead_id, kind, detail, now)
    return 200, {"ok": True, "lead": lead_detail(lead_id, now)}


def add_note(lead_id, text, now=None):
    text = str(text or "").strip()[:1000]
    if not text:
        return 400, {"error": "nota vuota"}
    if not store.get(lead_id):
        return 404, {"error": "studio non trovato"}
    store.add_note(lead_id, text)
    return 200, {"ok": True, "lead": lead_detail(lead_id, now)}


# ── the queue ──────────────────────────────────────────────────────────────

LEGACY_WAIT = {"WHATSAPP_SENT": "WHATSAPP_WAIT_DAYS", "EMAIL_SENT": "EMAIL_WAIT_DAYS",
               "CONTACTED": "FOLLOW_UP_DAYS", "CALL_DUE": None}


def legacy_due(lead):
    """When the old wait-based cascade makes this lead due, for leads that
    have no follow-up date of their own (everything contacted before v2)."""
    state = lead["state"]
    if state not in LEGACY_WAIT:
        return None
    if state == "CONTACTED" and (lead.get("follow_ups") or 0) >= 1:
        return None
    changed = _dt(lead.get("state_changed_at"))
    if not changed:
        return None
    wait = getattr(store, LEGACY_WAIT[state]) if LEGACY_WAIT[state] else 0
    return (changed + datetime.timedelta(days=wait)).date()


def _context(now):
    buckets = store.due_leads()
    bucket_of = {}
    for bucket, channel in store.BUCKET_CHANNEL.items():
        for lead in buckets[bucket]:
            bucket_of.setdefault(lead["id"], channel)
    today = now.date()
    return {"now": now, "today": today, "buckets": buckets, "bucket_of": bucket_of, "settings": settings(),
            "counts": {"whatsapp": count_whatsapp(today), "email": count_email(today), "call": count_calls(today)}}


def next_action(lead, ctx):
    """What this lead is waiting for, as {"kind", "label", "date", ...}.
    Kinds: dnc, closed, reply, follow, new, none."""
    today = ctx["today"]
    if lead.get("do_not_contact_at"):
        return {"kind": "dnc", "label": "Non contattare"}
    if lead["state"] == "DEAD":
        return {"kind": "closed", "label": "Chiuso"}
    if lead.get("reply_todo_at"):
        return {"kind": "reply", "label": "Rispondere", "date": str(lead["reply_todo_at"])[:10], "due": True}
    due = _date(lead.get("follow_up_at"))
    if due:
        return {"kind": "follow", "label": "Follow-up", "date": due.isoformat(),
                "due": due <= today, "overdue": due < today}
    if lead.get("follow_up_off_at"):
        return {"kind": "none", "label": "Nessun follow-up"}
    channel = ctx["bucket_of"].get(lead["id"])
    if lead["state"] == "NEW":
        if channel:
            return {"kind": "new", "label": "Primo contatto", "channel": channel}
        return {"kind": "none", "label": "Niente da scrivere"}
    legacy = legacy_due(lead)
    if legacy and channel:
        return {"kind": "follow", "label": "Follow-up", "date": legacy.isoformat(), "due": True,
                "overdue": legacy < today, "legacy": channel}
    if legacy and legacy > today and lead["state"] != "CALL_DUE":
        return {"kind": "follow", "label": "Follow-up", "date": legacy.isoformat(), "due": False, "overdue": False}
    return {"kind": "none", "label": "Nessun follow-up"}


def _channels(lead, ctx, kind, reserved):
    """Which channel buttons work for this lead right now, and why not."""
    s, now, counts = ctx["settings"], ctx["now"], ctx["counts"]
    bucket = ctx["bucket_of"].get(lead["id"])
    wa = {"ok": False, "why": None, "number": lead.get("whatsapp")}
    if not lead.get("whatsapp"):
        wa["why"] = "Nessun cellulare"
    elif lead.get("phone_invalid_at"):
        wa["why"] = "Numero errato"
    elif kind != "reply" and paused("whatsapp", s, now):
        wa["why"] = "WhatsApp in pausa"
    elif kind == "new" and bucket != "whatsapp":
        wa["why"] = "Non in coda per WhatsApp"
    elif kind == "new" and not lead_message_ok(lead):
        wa["why"] = "Nessun problema verificato da scrivere"
    elif kind != "reply" and counts["whatsapp"] + reserved >= s["cap_whatsapp"]:
        wa["why"] = f"Limite {counts['whatsapp']}/{s['cap_whatsapp']}"
    else:
        wa["ok"] = True
    em = {"ok": False, "why": None, "address": lead.get("email")}
    if not lead.get("email"):
        em["why"] = "Nessuna email"
    elif store.email_is_pec(lead):
        em["why"] = "Indirizzo PEC: niente email"
    elif already_emailed(lead["id"]):
        em["why"] = "Email già inviata"
    elif kind != "reply" and paused("email", s, now):
        em["why"] = "Email in pausa"
    elif bucket != "email":
        em["why"] = "Non in coda per l'email"
    elif counts["email"] >= s["cap_email"]:
        em["why"] = f"Limite {counts['email']}/{s['cap_email']}"
    else:
        em["ok"] = True
    call = {"ok": False, "why": None, "number": _number(lead)}
    if not call["number"]:
        call["why"] = "Nessun numero"
    elif lead.get("phone_invalid_at"):
        call["why"] = "Numero errato"
    elif kind != "reply" and paused("call", s, now):
        call["why"] = "Chiamate in pausa"
    else:
        call["ok"] = True
    return {"whatsapp": wa, "email": em, "call": call}


def lead_message_ok(lead):
    from . import outreach
    return bool(outreach.whatsapp_parts(lead, store.findings_of(lead)))


def _default_channel(kind, lead, channels, ctx):
    bucket = ctx["bucket_of"].get(lead["id"])
    if kind == "new":
        return bucket if bucket in CHANNELS else "call"
    order = ["whatsapp", "call", "email"]
    if kind == "follow" and bucket in ("email", "call"):
        order = [bucket] + [c for c in order if c != bucket]
    for ch in order:
        if channels[ch]["ok"]:
            return ch
    return order[0]


def _events(lead_id, limit=200):
    with store.connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM events WHERE lead_id = ? ORDER BY id DESC LIMIT ?",
                                              (lead_id, limit))]


CONTACT_KINDS = {"state:WHATSAPP_SENT": "WhatsApp", "send:whatsapp": "WhatsApp", "state:EMAIL_SENT": "Email",
                 "attempt": "Chiamata senza risposta", "reply_handled": "Risposta"}


def _last_contact(events):
    """The last time Momo reached out, on any channel. Replies are shown on
    their own, so they are not a "contact" here."""
    for e in events:
        kind = e["kind"]
        if kind in CONTACT_KINDS:
            return {"at": e["at"], "label": CONTACT_KINDS[kind]}
        if kind.startswith("state:") and (e["detail"] or "").startswith("chiamata"):
            return {"at": e["at"], "label": "Chiamata"}
    return None


NOTE_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}): ?(.*)$")


def parse_notes(notes):
    """The notes column is "timestamp: text" lines, where a text may itself
    run over several lines (a sent email is kept whole). Newest first."""
    out = []
    for line in (notes or "").splitlines():
        m = NOTE_LINE.match(line)
        if m:
            out.append({"at": m.group(1), "text": m.group(2)})
        elif out:
            out[-1]["text"] += "\n" + line
        elif line.strip():
            out.append({"at": None, "text": line})
    for n in out:
        n["text"] = n["text"][:2000]
    return list(reversed(out))


def _shot(lead_id):
    shots = os.environ.get("SCAN_SHOTS_DIR", "data/shots")
    path = os.path.join(shots, f"lead-{int(lead_id)}.png")
    try:
        return {"at": _iso(datetime.datetime.fromtimestamp(os.path.getmtime(path)))}
    except OSError:
        return None


def card(lead, ctx, kind, reserved=None, full=False):
    """Everything a queue card or the lead detail shows. Plain values only:
    the page renders every string as text."""
    from . import outreach
    now = ctx["now"]
    if reserved is None:
        reserved = _reserved_whatsapp(now, except_lead=lead["id"])
    channels = _channels(lead, ctx, kind, reserved)
    events = _events(lead["id"])
    notes = parse_notes(lead.get("notes"))
    findings = store.findings_of(lead)
    view = {
        "id": lead["id"], "name": lead["name"], "category": lead.get("category"), "city": lead.get("city"),
        "state": lead["state"], "status_label": STATUS_LABEL.get(lead["state"], lead["state"]),
        "phone": lead.get("phone"), "whatsapp": lead.get("whatsapp"), "email": lead.get("email"),
        "website": lead.get("website"), "source": _source_label(lead),
        "phone_invalid": bool(lead.get("phone_invalid_at")), "email_pec": store.email_is_pec(lead),
        "email_pec_flag": bool(lead.get("email_is_pec")),
        "problem": _problem(lead), "kind": kind, "channels": channels,
        "channel": _default_channel(kind, lead, channels, ctx),
        "next": next_action(lead, ctx),
        "follow_up_at": lead.get("follow_up_at"), "snoozed_until": lead.get("snoozed_until"),
        "reply": {"type": lead.get("reply_type"), "label": REPLY_TYPES.get(lead.get("reply_type") or ""),
                  "at": lead.get("reply_at"), "todo": bool(lead.get("reply_todo_at"))},
        "last_contact": _last_contact(events),
        "last_note": notes[0] if notes else None,
        "attempts": lead.get("attempts") or 0,
        "shot": _shot(lead["id"]),
        "dnc": {"at": lead["do_not_contact_at"], "reason": lead.get("do_not_contact_reason")}
               if lead.get("do_not_contact_at") else None,
    }
    bucket = ctx["bucket_of"].get(lead["id"])
    if lead["state"] == "NEW" and bucket == "whatsapp":
        view["message"] = outreach.whatsapp_parts(lead, findings, hour=now.hour)
    if bucket == "email" and store.emailable(lead) and not already_emailed(lead["id"]):
        body = outreach.email_message(lead, findings, hour=now.hour)
        if body:
            view["email_draft"] = {"subject": outreach.subject_for(lead, findings), "body": body,
                                   "footer": outreach.email_footer().strip()}
    view["script"] = outreach.call_script(lead, findings)
    if full:
        view["notes"] = notes
        view["history"] = [history_item(e) for e in events[:120]]
    return view


def today_view(now=None):
    """Oggi: replies, overdue follow-ups, follow-ups today, then new leads.
    Only the first item carries its full card."""
    now = _now(now)
    ctx = _context(now)
    s, counts, today = ctx["settings"], ctx["counts"], ctx["today"]
    _expire_handoffs(now)
    reserved = _reserved_whatsapp(now)
    replies, overdue, due_today, snoozed = [], [], [], 0
    all_leads = store.list_leads(limit=store.LEADS_LIST_CAP)
    by_id = {l["id"]: l for l in all_leads}

    def is_snoozed(lead):
        until = _dt(lead.get("snoozed_until"))
        return bool(until and until > now)

    for lead in all_leads:
        if lead.get("do_not_contact_at") or lead["state"] == "DEAD":
            continue
        na = next_action(lead, ctx)
        if na["kind"] not in ("reply", "follow") or not na.get("due"):
            continue
        if is_snoozed(lead):
            snoozed += 1
            continue
        item = {"kind": "reply" if na["kind"] == "reply" else ("follow_overdue" if na.get("overdue") else "follow_today"),
                "lead": lead, "due": na.get("date")}
        (replies if na["kind"] == "reply" else overdue if na.get("overdue") else due_today).append(item)
    overdue.sort(key=lambda i: i["due"] or "")
    replies.sort(key=lambda i: by_id[i["lead"]["id"]].get("reply_todo_at") or "")

    # New leads, in the order the old queue serves them, within the caps.
    new = []
    off_cat, off_city = set(s["off_categories"]), set(s["off_cities"])
    wa_left = s["cap_whatsapp"] - counts["whatsapp"] - reserved
    em_left = s["cap_email"] - counts["email"]
    from . import outreach
    for bucket, channel in (("to_whatsapp", "whatsapp"), ("to_email", "email"), ("to_call", "call")):
        if paused(channel, s, now):
            continue
        for lead in ctx["buckets"][bucket]:
            if lead["state"] != "NEW" or (lead.get("category") or "") in off_cat or (lead.get("city") or "") in off_city:
                continue
            if is_snoozed(lead):
                snoozed += 1
                continue
            if channel == "whatsapp":
                if wa_left <= 0 or not outreach.whatsapp_message(lead, store.findings_of(lead)):
                    continue
                wa_left -= 1
            elif channel == "email":
                if em_left <= 0 or already_emailed(lead["id"]) or \
                        not outreach.email_message(lead, store.findings_of(lead)):
                    continue
                em_left -= 1
            new.append({"kind": "new", "lead": lead, "channel": channel})

    items = replies + overdue + due_today + new
    # "Salta" sends a lead to the back of today's queue, in the order skipped.
    fresh = [i for i in items if (i["lead"].get("skipped_at") or "")[:10] != today.isoformat()]
    later = sorted([i for i in items if (i["lead"].get("skipped_at") or "")[:10] == today.isoformat()],
                   key=lambda i: i["lead"]["skipped_at"])
    items = fresh + later

    def compact(i):
        lead = i["lead"]
        p = _problem(lead)
        return {"kind": i["kind"], "id": lead["id"], "name": lead["name"], "category": lead.get("category"),
                "city": lead.get("city"), "due": i.get("due"), "channel": i.get("channel"),
                "problem": p["label"] if p else None, "skipped": i in later}
    first = None
    if items:
        head = items[0]
        kind = "new" if head["kind"] == "new" else ("reply" if head["kind"] == "reply" else "follow")
        first = dict(compact(head), card=card(head["lead"], ctx, kind, _reserved_whatsapp(now, head["lead"]["id"])))

    # The laptop agenda: follow-ups coming up in the next week.
    agenda = []
    for lead in all_leads:
        if lead.get("do_not_contact_at") or lead["state"] == "DEAD":
            continue
        due = _date(lead.get("follow_up_at"))
        if due and today < due <= today + datetime.timedelta(days=7):
            agenda.append({"id": lead["id"], "name": lead["name"], "date": due.isoformat()})
    agenda.sort(key=lambda a: (a["date"], a["name"]))

    pause_view = {k: paused(k, s, now) for k in CHANNELS}
    pause_view["all"] = paused("all", s, now)
    return {
        "date": today.isoformat(), "now": _iso(now),
        "counts": {"whatsapp": counts["whatsapp"], "email": counts["email"], "call": counts["call"],
                   "total": counts["whatsapp"] + counts["email"] + counts["call"]},
        "caps": {"whatsapp": s["cap_whatsapp"], "email": s["cap_email"]}, "goal": s["goal"],
        "paused": pause_view,
        "sections": {"replies": len(replies), "overdue": len(overdue), "today": len(due_today),
                     "new": len(new), "snoozed": snoozed},
        "first": first,
        "queue": [compact(i) for i in items[1:60]],
        "remaining": max(0, len(items) - 1),
        "pending": pending_view(now),
        "agenda": agenda[:20],
    }


def lead_detail(lead_id, now=None):
    now = _now(now)
    lead = store.get(lead_id)
    if not lead:
        return None
    ctx = _context(now)
    na = next_action(lead, ctx)
    kind = {"reply": "reply", "follow": "follow", "new": "new"}.get(na["kind"], "follow")
    if lead["state"] == "NEW" and kind != "new":
        kind = "new"
    return card(lead, ctx, kind, full=True)


# ── Contatti ───────────────────────────────────────────────────────────────

NEXT_ORDER = {"reply": 0, "follow_overdue": 1, "follow_today": 2, "new": 3, "follow_future": 4,
              "none": 5, "closed": 6, "dnc": 7}


def _next_bucket(na):
    if na["kind"] == "follow":
        return "follow_overdue" if na.get("overdue") else "follow_today" if na.get("due") else "follow_future"
    return na["kind"]


def leads_view(params, now=None):
    """Search and filters for Contatti. One due_leads() per request, however
    many rows: channels_open() per row would recompute it for each."""
    now = _now(now)
    params = params or {}
    ctx = _context(now)
    q = (params.get("q") or "").strip().lower()[:80]
    status = params.get("status") or ""
    category = params.get("category") or ""
    city = params.get("city") or ""
    problem = params.get("problem") or ""
    nxt = params.get("next") or ""
    rows, facets = [], {"categories": {}, "cities": {}, "problems": {}}
    for lead in store.list_leads(limit=store.LEADS_LIST_CAP):
        p = _problem(lead)
        facets["categories"][lead.get("category") or ""] = facets["categories"].get(lead.get("category") or "", 0) + 1
        facets["cities"][lead.get("city") or ""] = facets["cities"].get(lead.get("city") or "", 0) + 1
        if p:
            facets["problems"][p["code"]] = facets["problems"].get(p["code"], 0) + 1
        na = next_action(lead, ctx)
        bucket = _next_bucket(na)
        if q and q not in (lead["name"] or "").lower() and q not in (lead.get("category") or "").lower() \
                and q not in (lead.get("city") or "").lower() and q not in (lead.get("phone") or "").lower() \
                and q not in (lead.get("email") or "").lower():
            continue
        if status == "dnc":
            if not lead.get("do_not_contact_at"):
                continue
        elif status == "todo":
            if bucket not in ("reply", "follow_overdue", "follow_today", "new"):
                continue
        elif status:
            if lead["state"] != status or lead.get("do_not_contact_at"):
                continue
        if category and (lead.get("category") or "") != category:
            continue
        if city and (lead.get("city") or "") != city:
            continue
        if problem and (not p or p["code"] != problem):
            continue
        if nxt:
            wanted = {"reply": ("reply",), "overdue": ("follow_overdue",), "today": ("follow_today",),
                      "future": ("follow_future",), "new": ("new",), "none": ("none", "closed", "dnc")}.get(nxt, ())
            if bucket not in wanted:
                continue
        rows.append({"id": lead["id"], "name": lead["name"], "category": lead.get("category"),
                     "city": lead.get("city"), "state": lead["state"],
                     "status_label": "Non contattare" if lead.get("do_not_contact_at")
                     else STATUS_LABEL.get(lead["state"], lead["state"]),
                     "problem": p["label"] if p else None, "problem_code": p["code"] if p else None,
                     "next": na, "order": NEXT_ORDER.get(bucket, 9),
                     "snoozed_until": lead.get("snoozed_until") if (_dt(lead.get("snoozed_until")) or now) > now else None})
    rows.sort(key=lambda r: (r["order"], r["next"].get("date") or "9999", (r["name"] or "").lower()))
    total = len(rows)

    def facet(d, labels=None):
        return [{"value": k, "label": (labels or {}).get(k, k), "count": v}
                for k, v in sorted(d.items(), key=lambda kv: (-kv[1], kv[0])) if k]
    return {"total": total, "rows": rows[:300],
            "facets": {"categories": facet(facets["categories"]), "cities": facet(facets["cities"])[:80],
                       "problems": facet(facets["problems"], PROBLEM_SHORT),
                       "statuses": [{"value": k, "label": v} for k, v in STATUS_LABEL.items()]}}


# ── history ────────────────────────────────────────────────────────────────

FIELD_LABEL = {"phone": "Telefono", "whatsapp": "Cellulare", "email": "Email", "website": "Sito",
               "email_pec": "PEC"}


def history_item(e):
    kind, detail = e["kind"], e.get("detail") or ""
    label = kind
    if kind == "created":
        label, detail = "Aggiunto all'elenco", ""
    elif kind == "scanned":
        n = detail.split(" ")[0]
        label, detail = "Sito controllato", ("nessun problema" if n == "0" else f"{n} problemi trovati" if n != "1" else "1 problema trovato")
    elif kind.startswith("state:"):
        label = "Stato: " + STATUS_LABEL.get(kind[6:], kind[6:]).lower()
    elif kind == "note":
        label = "Nota"
    elif kind == "attempt":
        label, detail = "Chiamata senza risposta", ""
    elif kind == "follow_up":
        label = "Ricontattato"
    elif kind == "send:whatsapp":
        label, detail = "WhatsApp inviato", detail
    elif kind == "not_sent:whatsapp":
        label, detail = "WhatsApp aperto, non inviato", ""
    elif kind.startswith("reply:"):
        label, detail = "Risposta: " + REPLY_TYPES.get(kind[6:], kind[6:]).lower(), detail
    elif kind == "reply_handled":
        label = "Risposta gestita"
    elif kind == "follow_up_set":
        label = "Follow-up fissato"
    elif kind == "follow_up_off":
        label, detail = "Follow-up tolto", ""
    elif kind == "follow_up_done":
        try:
            d = json.loads(detail)
            late = (_date(d["on"]) - _date(d["due"])).days
            detail = "in tempo" if late <= 0 else f"in ritardo di {late} giorn{'o' if late == 1 else 'i'}"
        except (ValueError, KeyError, TypeError):
            detail = ""
        label = "Follow-up fatto"
    elif kind == "snooze":
        label = "Rimandato"
    elif kind == "skip":
        label, detail = "Saltato", ""
    elif kind == "dnc":
        try:
            detail = json.loads(detail).get("reason") or ""
        except (ValueError, AttributeError):
            pass
        label = "Non contattare"
    elif kind == "dnc_undo":
        label, detail = "Non contattare annullato", ""
    elif kind.startswith("edit:"):
        label = FIELD_LABEL.get(kind[5:], kind[5:]) + " modificato"
    elif kind == "website_found":
        label = "Sito trovato"
    elif kind == "site_search":
        label = "Verifica del sito"
    return {"at": e["at"], "kind": kind, "label": label, "detail": detail[:400]}


# ── Risultati ──────────────────────────────────────────────────────────────

def _reply_kind(kind, detail):
    """A reply, from a v2 reply event or from what the old app recorded."""
    if kind.startswith("reply:"):
        return kind[6:]
    d = (detail or "").lower()
    if not d.startswith(("whatsapp:", "email:")):
        return None
    if kind == "state:INTERESTED":
        return "positive"
    if kind == "state:DEAD" and "non interessat" in d:
        return "not_interested"
    if kind == "state:CONTACTED":
        return "other"
    return None


def _contact_channel(kind, detail):
    if kind == "state:WHATSAPP_SENT" or kind == "send:whatsapp":
        return "whatsapp"
    if kind == "state:EMAIL_SENT":
        return "email"
    if kind == "attempt" or (kind.startswith("state:") and (detail or "").startswith("chiamata")):
        return "call"
    return None


def _segment(key, label, n, replies):
    return {"key": key, "label": label, "n": n, "replies": replies,
            "rate": round(replies / n, 3) if n else None, "small": n < SMALL_N}


def results(days=30, now=None):
    now = _now(now)
    days = days if days in (7, 30, 90) else 30
    today = now.date()
    start = today - datetime.timedelta(days=days - 1)
    cohort_end = today - datetime.timedelta(days=MATURE_DAYS)
    s = settings()
    with store.connect() as conn:
        events = [dict(r) for r in conn.execute(
            "SELECT lead_id, at, kind, detail FROM events WHERE kind IN"
            " ('state:WHATSAPP_SENT','send:whatsapp','state:EMAIL_SENT','attempt','follow_up_done')"
            " OR kind LIKE 'reply:%' OR kind LIKE 'state:%' ORDER BY at, id")]
        leads = {r["id"]: dict(r) for r in conn.execute("SELECT id, findings FROM leads")}

    # Per day: distinct practices per channel.
    per_day = {}
    for e in events:
        ch = _contact_channel(e["kind"], e["detail"])
        day = _date(e["at"])
        if not ch or not day or day < start or day > today:
            continue
        per_day.setdefault(day, {"whatsapp": set(), "email": set(), "call": set()})[ch].add(e["lead_id"])
    series = []
    for i in range(days):
        day = start + datetime.timedelta(days=i)
        d = per_day.get(day, {"whatsapp": set(), "email": set(), "call": set()})
        row = {"date": day.isoformat(), "whatsapp": len(d["whatsapp"]), "email": len(d["email"]),
               "call": len(d["call"])}
        row["total"] = row["whatsapp"] + row["email"] + row["call"]
        series.append(row)
    goal = s["goal"]
    on_goal = [r for r in series if goal and r["total"] >= goal]
    streak = 0
    for r in reversed(series):
        if r["date"] == today.isoformat() and not (goal and r["total"] >= goal):
            continue           # today is not over yet: it does not break the streak
        if goal and r["total"] >= goal:
            streak += 1
        else:
            break

    # Reply attribution: each reply goes to the last contact before it.
    first_contact = {}          # (lead, channel) -> date
    replied = set()             # (lead, channel)
    last_channel = {}
    quality = {k: 0 for k in list(REPLY_TYPES) + ["other"]}
    follow = {"on_time": 0, "late": 0}
    for e in events:
        kind, lead_id, day = e["kind"], e["lead_id"], _date(e["at"])
        ch = _contact_channel(kind, e["detail"])
        if ch:
            first_contact.setdefault((lead_id, ch), day)
            last_channel[lead_id] = ch
            if ch == "call" and kind.startswith("state:"):
                replied.add((lead_id, "call"))          # a call that reached someone
            continue
        rk = _reply_kind(kind, e["detail"])
        if rk:
            if lead_id in last_channel:
                replied.add((lead_id, last_channel[lead_id]))
            if day and start <= day <= today:
                quality[rk] = quality.get(rk, 0) + 1
            continue
        if kind == "follow_up_done" and day and start <= day <= today:
            try:
                d = json.loads(e["detail"])
                late = (_date(d["on"]) - _date(d["due"])).days
            except (ValueError, KeyError, TypeError):
                late = 0
            follow["late" if late > 0 else "on_time"] += 1

    def cohort(channel):
        return [lead for (lead, ch), day in first_contact.items()
                if ch == channel and day and start <= day <= cohort_end]
    labels = {"whatsapp": "WhatsApp", "email": "Email", "call": "Chiamate"}
    by_channel = []
    for ch in CHANNELS:
        members = cohort(ch)
        by_channel.append(_segment(ch, labels[ch], len(members), sum((l, ch) in replied for l in members)))
    written = {}
    for ch in ("whatsapp", "email"):
        for lead_id in cohort(ch):
            lead = leads.get(lead_id)
            p = _problem(lead) if lead else None
            code = p["code"] if p else "none"
            bucket = written.setdefault(code, {"n": 0, "replies": 0})
            bucket["n"] += 1
            bucket["replies"] += (lead_id, ch) in replied
    by_problem = [_segment(code, PROBLEM_SHORT.get(code, "Nessun problema" if code == "none" else code),
                           v["n"], v["replies"]) for code, v in written.items()]
    by_problem.sort(key=lambda seg: (-seg["n"], seg["label"]))
    q_total = sum(quality.values())
    quality_items = [{"key": k, "label": REPLY_TYPES.get(k, "Senza tipo (vecchia app)"), "count": v,
                      "pct": round(v / q_total, 3) if q_total else None}
                     for k, v in quality.items() if k != "other" or v]
    queue = today_view(now)["sections"]
    totals = {ch: sum(r[ch] for r in series) for ch in CHANNELS}
    totals["contacts"] = sum(r["total"] for r in series)
    totals["messages"] = totals["whatsapp"] + totals["email"]
    totals["replies"] = q_total
    return {"days": days, "from": start.isoformat(), "to": today.isoformat(), "goal": goal,
            "caps": {"whatsapp": s["cap_whatsapp"], "email": s["cap_email"]},
            "series": series, "totals": totals,
            "streak": {"current": streak, "days_on_goal": len(on_goal), "days": days},
            "mature_days": MATURE_DAYS, "cohort_to": cohort_end.isoformat(),
            "by_channel": by_channel, "by_problem": by_problem,
            "quality": {"n": q_total, "small": q_total < SMALL_N, "items": quality_items},
            "follow_up": {"due_now": queue["overdue"] + queue["today"], "overdue_now": queue["overdue"],
                          "done_on_time": follow["on_time"], "done_late": follow["late"]}}
