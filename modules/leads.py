"""The lead store: one SQLite file, one state machine, no ORM.

States, and what moves a lead between them:

    NEW            scanned, drafted, waiting for you to send the first message
    WHATSAPP_SENT  you tapped the wa.me link          (/sent <id>)
    EMAIL_SENT     you approved the email             (/email <id>)
    CALL_DUE       no reply in time; it wants a phone call
    CONTACTED      you spoke to them                  (/contacted <id> [note])
    INTERESTED     worth chasing                      (/interested <id>)
    DEAD           stop spending attention on it      (/dead <id>)

Nothing here sends anything. Messages are drafted and queued; the send is a
deliberate act in Telegram, which keeps the whole thing on the right side of
Italy's rules on unsolicited commercial messaging (art. 130 Codice Privacy),
and matches the rule that nothing a cheap model wrote reaches a business
without a human reading it first.
"""

import os
import json
import sqlite3
import datetime
import contextlib

DB_PATH = os.environ.get("LEADS_DB", "data/leads.db")

STATES = ("NEW", "WHATSAPP_SENT", "EMAIL_SENT", "CALL_DUE",
          "CONTACTED", "INTERESTED", "DEAD")
OPEN_STATES = ("NEW", "WHATSAPP_SENT", "EMAIL_SENT", "CALL_DUE")
# CONTACTED belongs here too: the pipeline is done with it, but you still owe
# it one follow-up. Leaving it out made the follow-up branch unreachable.
ACTIONABLE_STATES = OPEN_STATES + ("CONTACTED",)

# Days to wait before a lead escalates to the next channel. Defaults match the
# plan; override per deployment without touching code.
WHATSAPP_WAIT_DAYS = int(os.environ.get("WHATSAPP_WAIT_DAYS", "2"))
EMAIL_WAIT_DAYS = int(os.environ.get("EMAIL_WAIT_DAYS", "3"))
FOLLOW_UP_DAYS = int(os.environ.get("FOLLOW_UP_DAYS", "4"))
# A claim in writing has to be current. Every scan in the database was taken
# once, days before the message would go out; in that time a domain had moved,
# a certificate had been renewed and a site had been rebuilt.
SCAN_MAX_AGE_HOURS = int(os.environ.get("SCAN_MAX_AGE_HOURS", "48"))
# Three unanswered calls on three different days, then stop.
MAX_ATTEMPTS = int(os.environ.get("MAX_CALL_ATTEMPTS", "3"))
# The row cap used wherever "every lead that might be due" is read. 500 was
# fine at 244 leads; a provincial OSM import can add several hundred more.
LEADS_LIST_CAP = int(os.environ.get("LEADS_LIST_CAP", "5000"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    category         TEXT,
    city             TEXT,
    website          TEXT,
    email            TEXT,
    phone            TEXT,
    whatsapp         TEXT,
    source           TEXT,
    state            TEXT NOT NULL DEFAULT 'NEW',
    created_at       TEXT NOT NULL,
    state_changed_at TEXT NOT NULL,
    next_action_at   TEXT,
    scanned_at       TEXT,
    findings         TEXT,
    draft            TEXT,
    follow_ups       INTEGER NOT NULL DEFAULT 0,
    notes            TEXT,
    UNIQUE (name, city)
);
CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL,
    at      TEXT NOT NULL,
    kind    TEXT NOT NULL,
    detail  TEXT,
    FOREIGN KEY (lead_id) REFERENCES leads (id)
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_state ON leads (state);
CREATE INDEX IF NOT EXISTS idx_events_lead ON events (lead_id);
"""


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


_schema_ready = False

# Columns added after the first deploy. CREATE TABLE IF NOT EXISTS never alters
# an existing table, so each addition is applied once, and "duplicate column"
# means it already was.
MIGRATIONS = (
    "ALTER TABLE leads ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE leads ADD COLUMN last_attempt_at TEXT",
)


def _migrate(conn):
    for statement in MIGRATIONS:
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e):
                raise


@contextlib.contextmanager
def connect():
    """Open the database, commit on success, and always close.

    sqlite3's own context manager commits but does NOT close, so the plain
    `with sqlite3.connect(...)` spelling leaks a file descriptor per call
    until the garbage collector happens to run - 93 of them after 400 calls
    in a process that is meant to stay up for months.

    timeout lets the 03:00 scan and a command typed in Telegram wait for each
    other instead of raising "database is locked".
    """
    global _schema_ready
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        if not _schema_ready:
            conn.executescript(SCHEMA)
            _migrate(conn)
            _schema_ready = True
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def add_lead(name, category=None, city=None, website=None, email=None,
             phone=None, whatsapp=None, source="manual"):
    """Insert a lead. Returns its id, or None when it already exists.

    Deduplicated on (name, city): re-importing the same list is normal and
    must not create twins or reset anyone's state.
    """
    # SQLite treats NULLs as distinct, so a missing city would let the same
    # business in twice however often the list is re-imported.
    name = (name or "").strip()
    city = (city or "").strip()
    with connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO leads (name, category, city, website, email, phone,"
                " whatsapp, source, created_at, state_changed_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (name, category, city, website, email, phone, whatsapp, source,
                 _now(), _now()))
        except sqlite3.IntegrityError:
            return None
        lead_id = cur.lastrowid
        conn.execute("INSERT INTO events (lead_id, at, kind, detail) VALUES (?,?,?,?)",
                     (lead_id, _now(), "created", source))
        return lead_id


def get(lead_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return dict(row) if row else None


def list_leads(state=None, limit=50):
    query = "SELECT * FROM leads"
    params = []
    if state:
        placeholders = ",".join("?" for _ in state) if isinstance(state, (list, tuple)) else "?"
        query += f" WHERE state IN ({placeholders})"
        params = list(state) if isinstance(state, (list, tuple)) else [state]
    query += " ORDER BY id LIMIT ?"
    params.append(limit)
    with connect() as conn:
        return [dict(r) for r in conn.execute(query, params)]


def set_state(lead_id, state, note=None, next_action_in_days=None):
    """Move a lead, recording why and when to look at it again."""
    if state not in STATES:
        raise ValueError(f"unknown state: {state}")
    next_at = None
    if next_action_in_days is not None:
        next_at = (datetime.datetime.now()
                   + datetime.timedelta(days=next_action_in_days)).isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute(
            "UPDATE leads SET state = ?, state_changed_at = ?, next_action_at = ?"
            " WHERE id = ?", (state, _now(), next_at, lead_id))
        conn.execute("INSERT INTO events (lead_id, at, kind, detail) VALUES (?,?,?,?)",
                     (lead_id, _now(), f"state:{state}", note))
    return get(lead_id)


def add_note(lead_id, text):
    with connect() as conn:
        row = conn.execute("SELECT notes FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if row is None:
            return None
        notes = (row["notes"] + "\n" if row["notes"] else "") + f"{_now()}: {text}"
        conn.execute("UPDATE leads SET notes = ? WHERE id = ?", (notes, lead_id))
        conn.execute("INSERT INTO events (lead_id, at, kind, detail) VALUES (?,?,?,?)",
                     (lead_id, _now(), "note", text))
    return get(lead_id)


def log_event(lead_id, kind, detail=None):
    """Record one event against a lead, for anything outside the built-in
    state machine - used by modules/site_search.py to log its decisions and
    to make its runs idempotent (see has_event)."""
    with connect() as conn:
        conn.execute("INSERT INTO events (lead_id, at, kind, detail) VALUES (?,?,?,?)",
                     (lead_id, _now(), kind, detail))


def has_event(lead_id, kind):
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM events WHERE lead_id = ? AND kind = ? LIMIT 1",
            (lead_id, kind)).fetchone()
        return row is not None


def set_website(lead_id, website):
    """Record a site found for a lead that had none, and clear scanned_at so
    scan_pending() picks it up on the next run - it only scans leads whose
    scanned_at is still NULL."""
    with connect() as conn:
        conn.execute("UPDATE leads SET website = ?, scanned_at = NULL WHERE id = ?",
                     (website, lead_id))
        conn.execute("INSERT INTO events (lead_id, at, kind, detail) VALUES (?,?,?,?)",
                     (lead_id, _now(), "website_found", website))
    return get(lead_id)


def save_scan(lead_id, findings, draft=None):
    """Store what the scanner found and the opener drafted from it."""
    with connect() as conn:
        conn.execute(
            "UPDATE leads SET findings = ?, draft = ?, scanned_at = ? WHERE id = ?",
            (json.dumps(findings, ensure_ascii=False), draft, _now(), lead_id))
        conn.execute("INSERT INTO events (lead_id, at, kind, detail) VALUES (?,?,?,?)",
                     (lead_id, _now(), "scanned", f"{len(findings)} finding(s)"))
    return get(lead_id)


def findings_of(lead):
    raw = lead.get("findings")
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


# Someone who builds sites for a living does not need one bought from you,
# and spots a templated opener instantly. Matched against name and category.
TRADE_EXCLUSIONS = ("gis", "web ", "webdesign", "web design", "informatic", "software",
                    "digital", "hosting", "seo", "agenzia di comunicazione", "sviluppat",
                    "programmat", "computer", "tecnolog", "startup", "consulenza it")


def _numbers(lead):
    """The last nine digits of every number on a lead - enough to match the
    same office written two different ways."""
    out = set()
    for field in ("phone", "whatsapp"):
        digits = "".join(c for c in (lead[field] or "") if c.isdigit())
        if len(digits) >= 9:
            out.add(digits[-9:])
    return out


def _domain(lead):
    """The registered-looking part of the site, so two entries for one
    practice match even when their phone numbers differ: Confident is in the
    list twice, on confident.dental, with two different landlines."""
    site = (lead["website"] or "").strip().lower()
    if not site:
        return None
    host = site.split("//")[-1].split("/")[0].removeprefix("www.")
    return host or None


def numbers_with_a_working_site():
    """Phone numbers belonging to a practice whose site checked out fine.

    The same practice is often listed twice - an old domain and the current
    one - and only the stale copy looks broken. The first message this system
    ever sent went to exactly that: a dead address from the map, while the
    real site, listed under the same number, was fine.
    """
    ok = set()
    with connect() as conn:
        for row in conn.execute("SELECT phone, whatsapp, findings, scanned_at FROM leads"):
            if row["scanned_at"] and not json.loads(row["findings"] or "[]"):
                ok |= _numbers(row)
    return ok


def _sendable_findings(lead):
    """Findings that may be asserted to a stranger today - judged by what the
    scanner is worth now, not by the number stored on the night of the scan."""
    from .scanner import SEVERITY, SENDABLE
    return [f for f in findings_of(lead) if SEVERITY.get(f["code"], 0) >= SENDABLE]


def _scan_is_fresh(lead):
    scanned = lead["scanned_at"]
    if not scanned:
        return False
    try:
        age = datetime.datetime.now() - datetime.datetime.fromisoformat(scanned)
    except (TypeError, ValueError):
        return False
    return age <= datetime.timedelta(hours=SCAN_MAX_AGE_HOURS)


def due_leads():
    """Leads whose timer has expired, grouped by what should happen next.

    Time only moves a lead forward here; sending stays manual, so this answers
    "what is waiting for me" rather than "what should the server fire off".
    """
    now = datetime.datetime.now()
    buckets = {"to_whatsapp": [], "to_email": [], "to_call": [], "to_follow_up": [],
               "no_angle": []}
    settled = numbers_with_a_working_site()
    seen_domains = set()
    # 500 used to be "more than we will ever have"; a provincial OSM import
    # alone can add several hundred, and a lead past this cap is simply never
    # queued, silently. LEADS_LIST_CAP is the same headroom scan_pending uses.
    for lead in list_leads(state=ACTIONABLE_STATES, limit=LEADS_LIST_CAP):
        state, changed = lead["state"], lead["state_changed_at"]

        # Nothing observed that is worth writing about. "No website in the map
        # data" is a guess, a blocked page is a refusal, a single slow reading
        # from Finland is not evidence - none of them go in a message. A
        # missing website is still a fair question to ask on the phone.
        if state == "NEW" and not _sendable_findings(lead):
            codes = {f["code"] for f in findings_of(lead)}
            if "no_website" in codes and lead["phone"]:
                buckets["to_call"].append(lead)
            else:
                buckets["no_angle"].append(lead)
            continue

        # Same number, another entry, working site: the problem we found is on
        # an address they have already left behind.
        if state == "NEW" and _numbers(lead) & settled:
            buckets["no_angle"].append(lead)
            continue
        # The same site listed twice is one practice, however many numbers it
        # publishes. Contacting both is contacting the same person twice.
        domain = _domain(lead)
        if state == "NEW" and domain:
            if domain in seen_domains:
                buckets["no_angle"].append(lead)
                continue
            seen_domains.add(domain)
        blob = f"{lead['name']} {lead.get('category') or ''}".lower()
        if state == "NEW" and any(t in blob for t in TRADE_EXCLUSIONS):
            buckets["no_angle"].append(lead)
            continue

        # Scanned and nothing wrong: there is no honest opener to write, so it
        # stays out of the send lists rather than producing an empty message.
        if state == "NEW" and lead["scanned_at"] and not findings_of(lead):
            buckets["no_angle"].append(lead)
            continue
        try:
            age_days = (now - datetime.datetime.fromisoformat(changed)).days
        except (TypeError, ValueError):
            age_days = 0

        # WhatsApp first where there is a number - highest read rate in Italy -
        # then email, then a call. Each step waits for the previous one to go
        # unanswered.
        if state == "NEW":
            # Route by the channels this lead actually has. Studi
            # professionali mostly publish a landline: of 77 contactable
            # dentists in Milan, 2 had a mobile. Queuing those for an email
            # address they do not have is how a digest fills up with work
            # that cannot be done.
            # In writing the claim must also be current; on the phone he can
            # look at the site while it rings.
            if not _scan_is_fresh(lead):
                buckets["to_call"].append(lead) if lead["phone"] else buckets["no_angle"].append(lead)
            elif lead["whatsapp"]:
                buckets["to_whatsapp"].append(lead)
            elif lead["email"]:
                buckets["to_email"].append(lead)
            elif lead["phone"]:
                buckets["to_call"].append(lead)
            else:
                buckets["no_angle"].append(lead)
        elif state == "WHATSAPP_SENT" and age_days >= WHATSAPP_WAIT_DAYS:
            # Straight to a call when there is no address: 10 of the 24
            # practices with a mobile publish no email, and queuing them for
            # one parked them in the email list for good.
            buckets["to_email" if lead["email"] else "to_call"].append(lead)
        elif state == "EMAIL_SENT" and age_days >= EMAIL_WAIT_DAYS:
            buckets["to_call"].append(lead)
        elif state == "CALL_DUE":
            buckets["to_call"].append(lead)
        elif state == "CONTACTED" and age_days >= FOLLOW_UP_DAYS and lead["follow_ups"] < 1:
            buckets["to_follow_up"].append(lead)
    # Strongest problem first. Ordered by id, the first calls of the day were
    # "could not find your site", the weakest angle in the list, while expired
    # certificates and dead sites - checkable in ten seconds on the owner's
    # own phone - sat halfway down.
    from .scanner import SEVERITY

    def strength(lead):
        # Looked up by code rather than read from the stored finding, so
        # retuning SEVERITY reorders existing leads without rescanning them.
        found = findings_of(lead)
        scores = [SEVERITY.get(f["code"], f.get("severity", 1)) for f in found]
        return (max(scores, default=0), len(found))
    for key in buckets:
        buckets[key].sort(key=strength, reverse=True)
    # "Non risponde" should move you on to the next practice, not hand the
    # same one back; it returns tomorrow.
    buckets["to_call"] = [l for l in buckets["to_call"] if not attempted_today(l)]
    return buckets


def attempted_today(lead):
    last = lead["last_attempt_at"] if "last_attempt_at" in lead.keys() else None
    return bool(last) and last[:10] == datetime.date.today().isoformat()


def record_attempt(lead_id, outcome):
    """A call that did not reach anyone. The lead leaves today's list and
    comes back tomorrow; after MAX_ATTEMPTS it is given up on.

    Only one attempt a day counts. Three taps in one sitting - a double tap,
    or a retry after a network error - used to archive a lead nobody had
    decided to give up on.
    """
    lead = get(lead_id)
    if lead and attempted_today(lead):
        return lead
    with connect() as conn:
        conn.execute("UPDATE leads SET attempts = attempts + 1, last_attempt_at = ?"
                     " WHERE id = ?", (_now(), lead_id))
        conn.execute("INSERT INTO events (lead_id, at, kind, detail) VALUES (?,?,?,?)",
                     (lead_id, _now(), "attempt", outcome))
    lead = get(lead_id)
    if lead and lead["attempts"] >= MAX_ATTEMPTS and lead["state"] in OPEN_STATES:
        set_state(lead_id, "DEAD", note=f"{lead['attempts']} tentativi senza risposta")
    return get(lead_id)


def attempted_today(lead):
    stamp = lead.get("last_attempt_at")
    return bool(stamp) and stamp[:10] == datetime.date.today().isoformat()


def advance_overdue():
    """Move leads whose email went unanswered into CALL_DUE.

    due_leads() only reports; this is the transition that makes /leads
    CALL_DUE mean something and stops the digest recomputing it from dates
    every morning.
    """
    moved = []
    for lead in list_leads(state="EMAIL_SENT", limit=LEADS_LIST_CAP):
        try:
            age = (datetime.datetime.now()
                   - datetime.datetime.fromisoformat(lead["state_changed_at"])).days
        except (TypeError, ValueError):
            continue
        if age >= EMAIL_WAIT_DAYS:
            set_state(lead["id"], "CALL_DUE", note=f"no reply in {age} days")
            moved.append(lead["id"])
    return moved


def mark_followed_up(lead_id):
    with connect() as conn:
        conn.execute("UPDATE leads SET follow_ups = follow_ups + 1 WHERE id = ?", (lead_id,))
        conn.execute("INSERT INTO events (lead_id, at, kind, detail) VALUES (?,?,?,?)",
                     (lead_id, _now(), "follow_up", None))
    return get(lead_id)


def get_setting(key, default=None):
    """Settings you can change from Telegram, without editing .env and
    restarting the service."""
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with connect() as conn:
        conn.execute("INSERT INTO settings (key, value) VALUES (?,?)"
                     " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     (key, value))
    return value


BUCKET_CHANNEL = {"to_whatsapp": "whatsapp", "to_email": "email",
                  "to_call": "call", "to_follow_up": "follow"}


def channels_open(lead_id):
    """Which channels the queue would offer this lead right now.

    One source of truth for "may this person be written to". The rules used to
    live only inside due_leads(), so the app's Lead screen and Telegram's
    /email walked straight past them: an audit found the app offering a first
    message to leads already contacted, to one marked "not interested", and to
    the lead whose false claim caused the first complaint.
    """
    buckets = due_leads()
    return {channel for bucket, channel in BUCKET_CHANNEL.items()
            if any(l["id"] == lead_id for l in buckets[bucket])}


def counts():
    with connect() as conn:
        rows = conn.execute("SELECT state, COUNT(*) n FROM leads GROUP BY state")
        return {r["state"]: r["n"] for r in rows}


if __name__ == "__main__":
    print("db:", DB_PATH)
    print("counts:", counts())
