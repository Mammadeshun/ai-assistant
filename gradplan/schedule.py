"""Pack the outstanding activities into exam sessions.

The credit-pace forecast in ``planner`` answers "roughly when". This answers
"in which session, and doing what" — which matters because the degree has no
prerequisites and no attendance obligation (Regolamento L-AI art. 10), so the
only real constraint is how much can be prepared per session.

Capacity is expressed as an *effort budget* per session rather than a count of
exams, because a 12 CFU written exam and a 6 CFU quiz are not interchangeable.
Activities assessed by coursework or project do not consume a session slot at
all: they are deadline-driven and run alongside exam preparation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable

from .config import REFERENCE_DIR
from .models import Career, PASSED, match_course_key, normalise_course_name

# The audit rates effort 1-5 against a written rubric (see gradplan.audit).
# Older profiles used low/medium/high; both are accepted.
EFFORT_POINTS = {"low": 1, "medium": 2, "high": 3}


def effort_points(value) -> int:
    if isinstance(value, (int, float)):
        return max(1, int(value))
    return EFFORT_POINTS.get(str(value), 2)

# Three sessions per academic year, as published for this degree:
# winter (Jan-Feb), summer (Jun-Jul), autumn (Aug-Sep).
SESSION_PATTERN = [
    ("winter", (1, 19), (2, 27)),
    ("summer", (6, 15), (7, 31)),
    ("autumn", (8, 31), (9, 25)),
]


@dataclass
class ProfiledActivity:
    name: str
    cfu: float
    code: str | None
    mode: str
    consumes_exam_slot: bool
    past_papers: bool
    effort: str
    notes: str = ""
    evidence: list[str] = field(default_factory=list)

    @property
    def points(self) -> int:
        return effort_points(self.effort)

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "code": self.code,
            "cfu": self.cfu,
            "mode": self.mode,
            "consumes_exam_slot": self.consumes_exam_slot,
            "past_papers": self.past_papers,
            "effort": self.effort,
            "effort_points": self.points,
            "notes": self.notes,
        }


@dataclass
class PlannedSession:
    name: str
    start: date
    end: date
    activities: list[ProfiledActivity] = field(default_factory=list)

    @property
    def points(self) -> int:
        return sum(a.points for a in self.activities)

    @property
    def cfu(self) -> float:
        return sum(a.cfu for a in self.activities)

    def to_json(self) -> dict[str, Any]:
        return {
            "session": self.name,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "effort_points": self.points,
            "cfu": self.cfu,
            "activities": [a.to_json() for a in self.activities],
        }


def load_profile(path=None) -> dict[str, dict[str, Any]]:
    """Assessment profile keyed by normalised course name."""
    path = path or REFERENCE_DIR / "assessment_profile.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    profile: dict[str, dict[str, Any]] = {}
    for entry in data.get("activities", []):
        findings = entry.get("findings", {})
        judgement = entry.get("judgement", {})
        fmt = str(findings.get("assessment_format", entry.get("mode", "")))
        # An activity needs an exam slot unless it is assessed purely by
        # submitted work, in which case it runs alongside exam preparation.
        coursework = bool(
            re.search(r"coursework|report \+ presentation", fmt, re.I)
            or re.fullmatch(r"project.*", fmt.strip(), re.I)
        )
        profile[normalise_course_name(entry["name"])] = {
            "mode": fmt or "UNVERIFIED",
            "consumes_exam_slot": entry.get("consumes_exam_slot", not coursework),
            "past_papers": bool(findings.get("past_paper_count", 0)),
            "effort": judgement.get("effort", entry.get("effort", 2)),
            "notes": judgement.get("why", entry.get("notes", "")),
            "evidence": [e.get("quote", "") for e in findings.get("evidence", [])],
            "tier": findings.get("evidence_tier", "?"),
        }
    return profile


def profile_outstanding(
    career: Career,
    profile: dict[str, dict[str, Any]] | None = None,
    assume_passed: Iterable[str] = (),
) -> tuple[list[ProfiledActivity], list[str]]:
    """Attach assessment info to everything not yet passed.

    ``assume_passed`` lets you explore "what if I clear these first" without
    editing the scraped career.
    """
    profile = profile if profile is not None else load_profile()
    assumed = {normalise_course_name(n) for n in assume_passed}
    activities: list[ProfiledActivity] = []
    unprofiled: list[str] = []

    for exam in career.exams:
        if exam.status == PASSED:
            continue
        key = normalise_course_name(exam.name)
        if key in assumed or match_course_key(exam.name, assumed):
            continue
        matched = match_course_key(exam.name, profile.keys())
        entry = profile.get(matched) if matched else None
        if entry is None:
            unprofiled.append(exam.name)
            entry = {
                "mode": "written",
                "consumes_exam_slot": True,
                "past_papers": False,
                "effort": "medium",
                "notes": "no assessment profile; assumed a medium written exam",
            }
        activities.append(
            ProfiledActivity(
                name=exam.name,
                cfu=exam.cfu,
                code=exam.code,
                mode=entry["mode"],
                consumes_exam_slot=entry.get("consumes_exam_slot", True),
                past_papers=entry.get("past_papers", False),
                effort=entry.get("effort", "medium"),
                notes=entry.get("notes", ""),
                evidence=entry.get("evidence", []),
            )
        )
    return activities, unprofiled


MIN_USABLE_DAYS = 14


def upcoming_sessions(today: date, count: int = 12) -> list[PlannedSession]:
    """The next usable exam sessions, in order.

    A session already under way counts only if enough of it is left to sit
    something; one that ends tomorrow is not a planning option.
    """
    sessions: list[PlannedSession] = []
    year = today.year
    while len(sessions) < count:
        for name, (start_month, start_day), (end_month, end_day) in SESSION_PATTERN:
            start = date(year, start_month, start_day)
            end = date(year, end_month, end_day)
            remaining = (end - max(today, start)).days
            if end > today and remaining >= MIN_USABLE_DAYS:
                sessions.append(PlannedSession(name=name, start=start, end=end))
        year += 1
    return sorted(sessions, key=lambda s: s.start)[:count]


def build_schedule(
    activities: Iterable[ProfiledActivity],
    today: date,
    session_budget: int = 8,
) -> tuple[list[PlannedSession], list[ProfiledActivity]]:
    """Greedily fill sessions up to the effort budget.

    Hardest first: a 12 CFU written exam is the thing most likely to need a
    second attempt, so it should land as early as possible, leaving later
    sessions as slack.
    """
    exams = sorted(
        (a for a in activities if a.consumes_exam_slot),
        key=lambda a: (-a.points, -a.cfu, a.name),
    )
    coursework = [a for a in activities if not a.consumes_exam_slot]

    sessions = upcoming_sessions(today, count=max(4, len(exams)))
    for activity in exams:
        for session in sessions:
            if session.points + activity.points <= session_budget:
                session.activities.append(activity)
                break
        else:  # pragma: no cover - only if budget < a single activity's points
            sessions[-1].activities.append(activity)

    used = [s for s in sessions if s.activities]
    return used, coursework


def completion_date(
    sessions: Iterable[PlannedSession], coursework: Iterable[ProfiledActivity]
) -> date | None:
    """When the last credit could be earned."""
    used = [s for s in sessions if s.activities]
    if not used and not list(coursework):
        return None
    return max((s.end for s in used), default=None)


def summarise(
    sessions: Iterable[PlannedSession],
    coursework: Iterable[ProfiledActivity],
    unprofiled: Iterable[str],
) -> dict[str, Any]:
    sessions = list(sessions)
    coursework = list(coursework)
    return {
        "sessions": [s.to_json() for s in sessions],
        "coursework_in_parallel": [a.to_json() for a in coursework],
        "unprofiled": list(unprofiled),
        "exams_scheduled": sum(len(s.activities) for s in sessions),
        "sessions_needed": len(sessions),
        "completion": (
            completion_date(sessions, coursework).isoformat()
            if completion_date(sessions, coursework)
            else None
        ),
    }
