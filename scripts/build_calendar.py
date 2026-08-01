#!/usr/bin/env python3
"""Day-by-day study calendar for the September 2026 session.

Scheduling is earliest-deadline-first, which is optimal for feasibility when
work is preemptible: if EDF cannot fit the plan, no ordering can. Exam days are
derated to 4 usable hours, because dividing total hours by total days quietly
assumes you revise a full day on the morning you sit Computer Programming in
Milan.

Deliverable-driven courses are pinned earlier than EDF would put them: a
project has a submission deadline before the exam, and cannot be crammed the
night before the way a written paper can.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

START = dt.date(2026, 8, 1)
END = dt.date(2026, 9, 25)

FREE_DAY_HOURS = 7.0
EXAM_DAY_HOURS = 4.0

# code, name, exam date, hours, CFU, campus, deliverable deadline (or None)
PLAN = [
    ("509496", "Information Retrieval & RecSys", dt.date(2026, 8, 31), 30, 6, "Pavia", dt.date(2026, 8, 24)),
    ("509521", "Laboratory of Machine Learning", dt.date(2026, 9, 1), 25, 3, "Pavia", dt.date(2026, 8, 28)),
    ("509519", "Ethics, Law and AI", dt.date(2026, 9, 2), 28, 12, "Pavia", None),
    ("509494", "Brain Modelling", dt.date(2026, 9, 3), 26, 6, "Pavia", dt.date(2026, 8, 27)),
    ("509495", "Data Mining", dt.date(2026, 9, 4), 19, 6, "Pavia", None),
    ("509485", "Cognitive Psychology", dt.date(2026, 9, 8), 27, 6, "Bicocca", None),
    ("509477", "Computer Programming", dt.date(2026, 9, 9), 44, 12, "Statale", None),
    ("509481", "Calculus", dt.date(2026, 9, 11), 44, 12, "Pavia", None),
    ("509486", "Machine Learning / ANN / DL", dt.date(2026, 9, 15), 28, 12, "Pavia", None),
    ("509492", "Theoretical & Quantum Physics", dt.date(2026, 9, 22), 30, 12, "Statale", None),
    ("509488", "Text Mining and NLP", dt.date(2026, 9, 24), 30, 6, "Pavia", None),
]


def days() -> list[dt.date]:
    span = (END - START).days + 1
    return [START + dt.timedelta(days=i) for i in range(span)]


def minimum_daily_hours() -> float:
    """The smallest free-day load under which every deadline is still met."""
    exam_days = {c[2] for c in PLAN}
    worst = 0.0
    for _, _, date, *_ in sorted(PLAN, key=lambda c: c[2]):
        needed = sum(c[3] for c in PLAN if c[2] <= date)
        before = [d for d in days() if d <= date]
        free = sum(1 for d in before if d not in exam_days)
        sat = sum(EXAM_DAY_HOURS for d in before if d in exam_days)
        if free:
            worst = max(worst, (needed - sat) / free)
    return worst


def schedule(free_hours: float) -> tuple[dict[str, list[tuple[str, float]]], list[str]]:
    """Earliest-deadline-first allocation, projects pinned to their deadline."""
    exam_days = {c[2]: c[1] for c in PLAN}
    remaining = {c[0]: float(c[3]) for c in PLAN}
    # A course must be finished by its deliverable deadline if it has one,
    # otherwise by the day before the exam.
    due = {c[0]: (c[6] or c[2] - dt.timedelta(days=1)) for c in PLAN}
    name = {c[0]: c[1] for c in PLAN}

    plan: dict[str, list[tuple[str, float]]] = {}
    warnings: list[str] = []

    for day in days():
        capacity = EXAM_DAY_HOURS if day in exam_days else free_hours
        slots: list[tuple[str, float]] = []
        # Earliest deadline first among courses still owing hours.
        for code in sorted(remaining, key=lambda c: (due[c], -remaining[c])):
            if capacity <= 0.01:
                break
            if remaining[code] <= 0.01 or due[code] < day:
                continue
            take = min(capacity, remaining[code])
            slots.append((code, round(take, 1)))
            remaining[code] -= take
            capacity -= take
        plan[day.isoformat()] = slots

    for code, left in remaining.items():
        if left > 0.01:
            warnings.append(f"{name[code]}: {left:.1f}h could not be placed before its deadline")
    return plan, warnings


def main() -> int:
    floor = minimum_daily_hours()
    plan, warnings = schedule(FREE_DAY_HOURS)

    exam_days = {c[2]: c for c in PLAN}
    name = {c[0]: c[1] for c in PLAN}

    lines = [
        "# Study calendar — 1 August to 25 September 2026",
        "",
        f"Eleven exams, {sum(c[4] for c in PLAN)} CFU, {sum(c[3] for c in PLAN)} hours.",
        "",
        f"**Minimum sustainable load: {floor:.1f} h on every non-exam day**, plus about "
        f"{EXAM_DAY_HOURS:.0f} h on exam days. Below that the plan misses a deadline. "
        f"The calendar below is built at {FREE_DAY_HOURS:.0f} h/day, which leaves "
        f"{FREE_DAY_HOURS * sum(1 for d in days() if d not in exam_days) + EXAM_DAY_HOURS * len(exam_days) - sum(c[3] for c in PLAN):.0f} h of slack "
        "across the whole eight weeks — roughly three lost days, no more.",
        "",
        "Dividing total hours by total days gives a lower, wrong number: it assumes "
        "a full day's revision on the morning you sit Computer Programming in Milan.",
        "",
        "| Date | Day | Hours | Work |",
        "|---|---|---|---|",
    ]
    for day in days():
        slots = plan[day.isoformat()]
        label = day.strftime("%a %d %b")
        if day in exam_days:
            course = exam_days[day]
            marker = f"**EXAM: {course[1]} ({course[5]})**"
            work = marker + ((" · then " + ", ".join(f"{name[c]} {h}h" for c, h in slots)) if slots else "")
        else:
            work = ", ".join(f"{name[c]} {h}h" for c, h in slots) or "—"
        total = sum(h for _, h in slots)
        lines.append(f"| {day.isoformat()} | {label} | {total:.0f} | {work} |")

    if warnings:
        lines += ["", "## Could not be placed", ""] + [f"- {w}" for w in warnings]

    Path("reference/CALENDAR.md").write_text("\n".join(lines) + "\n")
    Path("data/audit/calendar.json").write_text(
        json.dumps(
            {
                "minimum_free_day_hours": round(floor, 2),
                "built_at_free_day_hours": FREE_DAY_HOURS,
                "exam_day_hours": EXAM_DAY_HOURS,
                "total_hours": sum(c[3] for c in PLAN),
                "total_cfu": sum(c[4] for c in PLAN),
                "unplaced": warnings,
                "days": plan,
            },
            indent=1,
        )
    )
    print(f"minimum free-day load: {floor:.2f} h")
    print(f"built at {FREE_DAY_HOURS} h/day; unplaced: {warnings or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
