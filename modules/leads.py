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


def due_leads():
    """Leads whose timer has expired, grouped by what should happen next.

    Time only moves a lead forward here; sending stays manual, so this answers
    "what is waiting for me" rather than "what should the server fire off".
    """
    now = datetime.datetime.now()
    buckets = {"to_whatsapp": [], "to_email": [], "to_call": [], "to_follow_up": [],
               "no_angle": []}
    for lead in list_leads(state=ACTIONABLE_STATES, limit=500):
        state, changed = lead["state"], lead["state_changed_at"]

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
            if lead["whatsapp"]:
                buckets["to_whatsapp"].append(lead)
            elif lead["email"]:
                buckets["to_email"].append(lead)
            elif lead["phone"]:
                buckets["to_call"].append(lead)
            else:
                buckets["no_angle"].append(lead)
        elif state == "WHATSAPP_SENT" and age_days >= WHATSAPP_WAIT_DAYS:
            buckets["to_email"].append(lead)
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
    return buckets


def advance_overdue():
    """Move leads whose email went unanswered into CALL_DUE.

    due_leads() only reports; this is the transition that makes /leads
    CALL_DUE mean something and stops the digest recomputing it from dates
    every morning.
    """
    moved = []
    for lead in list_leads(state="EMAIL_SENT", limit=500):
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


def counts():
    with connect() as conn:
        rows = conn.execute("SELECT state, COUNT(*) n FROM leads GROUP BY state")
        return {r["state"]: r["n"] for r in rows}


if __name__ == "__main__":
    print("db:", DB_PATH)
    print("counts:", counts())
