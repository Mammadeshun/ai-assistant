"""Human-readable rendering of the graduation assessment."""

from __future__ import annotations

from datetime import date
from typing import Iterable

from .models import Career
from .planner import SessionAssessment, earliest_feasible

BAR = "─" * 72


def _fmt_date(value: date) -> str:
    return value.strftime("%d %b %Y")


def career_summary(career: Career) -> str:
    lines = [BAR, "CAREER", BAR]
    average = career.weighted_average()
    base = career.base_graduation_score()
    lines.append(f"  Exams passed        {len(career.passed)}")
    lines.append(f"  CFU earned          {career.cfu_earned:g} / 180")
    if average is not None:
        lines.append(f"  Weighted average    {average:.2f} / 30")
        lines.append(f"  Base degree score   {base} / 110  (average x 11/3)")
    else:
        lines.append("  Weighted average    n/a (no graded exams recorded)")
    outstanding = [e for e in career.exams if e.status != "passed"]
    if outstanding:
        lines.append(f"  Still outstanding   {len(outstanding)}")
        for exam in outstanding:
            flag = " (booked)" if exam.status == "enrolled" else ""
            lines.append(f"      - {exam.name} [{exam.cfu:g} CFU]{flag}")
    return "\n".join(lines)


def answer(assessments: Iterable[SessionAssessment], today: date) -> str:
    assessments = list(assessments)
    winner = earliest_feasible(assessments)
    lines = [BAR, "EARLIEST POSSIBLE GRADUATION", BAR]

    if winner is None:
        lines.append("  No published graduation session is reachable.")
        upcoming = [a for a in assessments if a.session.date > today]
        if upcoming:
            nearest = upcoming[0]
            lines.append(f"  Nearest session {_fmt_date(nearest.session.date)} is blocked by:")
            for blocker in nearest.blockers:
                lines.append(f"      - {blocker}")
        lines.append("")
        lines.append("  Note: the calendar only runs to the last published session.")
        return "\n".join(lines)

    session = winner.session
    days = (session.date - today).days
    lines.append(f"  >>> {_fmt_date(session.date)}  at {session.location}   ({days} days away)")
    lines.append("")
    lines.append(f"  Apply by                     {_fmt_date(session.application_deadline)}")
    lines.append("  Report uploaded and every")
    lines.append(f"  exam recorded by             {_fmt_date(session.records_deadline)}")

    to_sit = [p for p in winner.exam_plans if p.sitting]
    if to_sit:
        lines.append("")
        lines.append("  Exams still to sit:")
        for plan in sorted(to_sit, key=lambda p: p.sitting.date):
            lines.append(
                f"      {_fmt_date(plan.sitting.date)}  {plan.name} "
                f"[{plan.cfu:g} CFU, {plan.sitting.session} session, {plan.sitting.location}]"
            )

    mark = winner.projected_mark
    if mark.get("available"):
        low, high = mark["final_range"]
        lines.append("")
        lines.append(
            f"  Projected degree mark        {low}-{high} / 110"
            f"  (base {mark['base_score']}"
            + (f" + {mark['in_corso_bonus']} in corso" if mark["in_corso_bonus"] else "")
            + ", board adds 0-7)"
        )
        if mark["cum_laude_possible"]:
            lines.append("  Cum laude is arithmetically reachable with a high board increment.")
    return "\n".join(lines)


def session_table(assessments: Iterable[SessionAssessment], today: date) -> str:
    lines = [BAR, "ALL PUBLISHED SESSIONS", BAR]
    for assessment in assessments:
        session = assessment.session
        if session.date <= today:
            state = "past"
        elif assessment.feasible:
            state = "REACHABLE"
        else:
            state = "blocked"
        lines.append(
            f"  {_fmt_date(session.date)}  {session.location:<16s} "
            f"apply by {_fmt_date(session.application_deadline)}  "
            f"records by {_fmt_date(session.records_deadline)}   {state}"
        )
        if not assessment.feasible and session.date > today:
            for blocker in assessment.blockers:
                lines.append(f"        - {blocker}")
    return "\n".join(lines)


def coverage(sittings: Iterable) -> str:
    """State what the exam calendar actually covers.

    A course can look unreachable simply because its session's sheet was not
    published yet, so the span of archived sittings has to be visible.
    """
    sittings = list(sittings)
    lines = [BAR, "EXAM CALENDAR COVERAGE", BAR]
    if not sittings:
        lines.append("  No exam sittings archived - run fetch-public.")
        return "\n".join(lines)

    sessions = sorted({s.session for s in sittings})
    first = min(s.date for s in sittings)
    last = max(s.date for s in sittings)
    lines.append(f"  Sessions archived   {', '.join(sessions)}")
    lines.append(f"  Sittings            {len(sittings)} covering {_fmt_date(first)} - {_fmt_date(last)}")
    for name in ("winter", "summer", "autumn"):
        if name not in sessions:
            lines.append(
                f"  Missing             {name} session sheet is not published; "
                f"exams held only in {name} will show as having no sitting"
            )
    return "\n".join(lines)


def render(
    career: Career,
    assessments: Iterable[SessionAssessment],
    today: date,
    sittings: Iterable = (),
) -> str:
    assessments = list(assessments)
    return "\n\n".join(
        [
            career_summary(career),
            answer(assessments, today),
            session_table(assessments, today),
            coverage(sittings),
        ]
    )
