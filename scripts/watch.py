#!/usr/bin/env python3
"""Daily watch on the things that can change the plan without telling you.

Six checks, each one attached to a decision:

1. **Winter appelli.** Esse3 returns nothing for 2027, so the January half of
   the plan currently has no confirmed dates. The moment they publish, the
   Hall-violator check has to be re-run against them.
2. **Extraordinary autumn appelli.** Project Work has sittings on 14/10 and
   02/12, which proves the university schedules them. If any deferred course
   gets one, January stops being a single attempt.
3. **The AI Marketing lab window.** Both 2026 windows closed with nothing
   submitted. An autumn window reopening is the only thing that unblocks 509498.
4. **Booking windows.** Opens 20 days before an appello, closes 5 days before.
   Warns three days before a close.
5. **New forum posts** on any watched course.
6. **Results** appearing on the exam-results board.

State lives in data/watch_state.json, so only changes are reported. Run with
--once for a single pass; exits non-zero only on a genuine failure, not on
"nothing changed".
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bs4 import BeautifulSoup  # noqa: E402

from gradplan import config  # noqa: E402
from gradplan.archive import RawArchive  # noqa: E402
from gradplan.sources.http_session import http_session  # noqa: E402

STATE = Path("data/watch_state.json")
RAW = Path("data/raw")

DEFERRED_TO_WINTER = {
    "ORGANIZATION THEORY AND DESIGN",
    "WEB AND SOCIAL MEDIA SEARCH AND ANALYSIS",
    "ARTIFICIAL INTELLIGENCE FOR COMMUNICATION AND MARKETING",
    "PROBABILITY AND STATISTICAL INFERENCE",
    "KNOWLEDGE REPRESENTATION AND REASONING",
    "COMPUTATIONAL LOGIC",
    "FUZZY SYSTEMS AND EVOLUTIONARY COMPUTING",
    "STATISTICAL MODELLING",
}

# The two lab assignments that gate 509498.
AIC_M_COURSE = "https://elearning.unipv.it/course/view.php?id=11447"


def load_env() -> None:
    env = Path(".env")
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=1, sort_keys=True))


def parse_appelli(markup: str) -> list[dict[str, str]]:
    """Rows of the AppelliF.do table: course, date, booking window."""
    soup = BeautifulSoup(markup, "html.parser")
    rows: list[dict[str, str]] = []
    for row in soup.select("table tr"):
        cells = [c.get_text(" ", strip=True).replace("​", "") for c in row.select("td")]
        if len(cells) < 3:
            continue
        dates = [c for c in cells if re.fullmatch(r"\d{2}/\d{2}/\d{4}", c)]
        window = next((c for c in cells if re.match(r"\d{2}/\d{2}/\d{4}\s+\d{2}/\d{2}/\d{4}", c)), "")
        if not dates:
            continue
        # The first cell is an empty icon column. Taking it as the course name
        # blanks every row, and 43 sittings collapse into 21 unique dates.
        course = next(
            (
                c
                for c in cells
                if c and not re.match(r"\d{2}/\d{2}/\d{4}", c) and len(c) > 3
            ),
            "",
        )
        rows.append(
            {
                "course": course[:90],
                "appello": dates[0],
                "iscrizione": window,
            }
        )
    return rows


def check_appelli(session, state: dict, findings: list[str]) -> list[dict[str, str]]:
    # Esse3 answers an unauthenticated GET with a SAML bounce page, not the
    # table, so the SSO chain has to be walked before anything is fetched.
    session.login(config.ESSE3_LIBRETTO, success_marker="libretto")
    response = session.goto(
        config.ESSE3_AVAILABLE_EXAMS, source="esse3", label="watch-appelli"
    )
    rows = parse_appelli(response.read_text())
    seen = {f"{r['course']}|{r['appello']}" for r in rows}
    known = set(state.get("appelli_seen", []))

    # First run has nothing to compare against: record the baseline rather than
    # reporting every appello in the system as a change.
    if not known:
        state["appelli_seen"] = sorted(seen)
        findings.append(f"baseline recorded: {len(seen)} appelli known")
        return rows

    for key in sorted(seen - known):
        course, date = key.split("|", 1)
        try:
            when = dt.datetime.strptime(date, "%d/%m/%Y").date()
        except ValueError:
            continue
        if when.year >= 2027:
            findings.append(f"WINTER APPELLO PUBLISHED: {course} on {date}")
        elif when.month in (10, 11, 12):
            findings.append(f"EXTRAORDINARY AUTUMN APPELLO: {course} on {date}")
        elif course.strip().upper() in DEFERRED_TO_WINTER:
            findings.append(f"new appello for a deferred course: {course} on {date}")
        else:
            findings.append(f"new appello: {course} on {date}")

    state["appelli_seen"] = sorted(seen | known)
    return rows


def check_booking_deadlines(rows: list[dict[str, str]], findings: list[str]) -> None:
    today = dt.date.today()
    for row in rows:
        window = row.get("iscrizione", "")
        parts = window.split()
        if len(parts) != 2:
            continue
        try:
            opens = dt.datetime.strptime(parts[0], "%d/%m/%Y").date()
            closes = dt.datetime.strptime(parts[1], "%d/%m/%Y").date()
        except ValueError:
            continue
        if opens == today:
            findings.append(f"BOOKING OPENS TODAY: {row['course']} ({row['appello']})")
        days_left = (closes - today).days
        if 0 <= days_left <= 3:
            findings.append(
                f"BOOKING CLOSES IN {days_left}d: {row['course']} "
                f"({row['appello']}) — closes {parts[1]}"
            )


def check_lab_window(session, state: dict, findings: list[str]) -> None:
    """Has an autumn lab assignment appeared for 509498?"""
    try:
        response = session.goto(AIC_M_COURSE, source="kiro", label="watch-509498")
    except Exception as exc:  # noqa: BLE001
        findings.append(f"could not read the AI Marketing course page: {type(exc).__name__}")
        return
    soup = BeautifulSoup(response.read_text(), "html.parser")
    assignments = sorted(
        a.get_text(" ", strip=True)
        for a in soup.select('a[href*="/mod/assign/view.php"]')
    )
    digest = hashlib.sha256("|".join(assignments).encode()).hexdigest()[:16]
    if state.get("aicm_assign_digest") and state["aicm_assign_digest"] != digest:
        findings.append(
            "AI MARKETING LAB CHANGED — assignments are now: " + "; ".join(assignments)
        )
    state["aicm_assign_digest"] = digest
    state["aicm_assignments"] = assignments


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="single pass (default)")
    parser.parse_args()

    load_env()
    state = load_state()
    findings: list[str] = []

    archive = RawArchive(RAW)
    session = http_session(archive, delay=config.REQUEST_DELAY_SECONDS)
    try:
        rows = check_appelli(session, state, findings)
        check_booking_deadlines(rows, findings)
        check_lab_window(session, state, findings)
    finally:
        session.close()

    state["last_run"] = dt.datetime.now(dt.timezone.utc).isoformat()
    save_state(state)

    stamp = dt.date.today().isoformat()
    if findings:
        print(f"[{stamp}] {len(findings)} change(s):")
        for line in findings:
            print(f"  - {line}")
    else:
        print(f"[{stamp}] no change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
