#!/usr/bin/env python3
"""Day-by-day study calendar for the September 2026 session.

The first version of this scheduler was earliest-deadline-first over one
contiguous block per course. EDF is optimal for *feasibility* - if EDF cannot
fit the plan, no ordering can - and it is actively harmful for *retention*,
because it schedules every course as early as its deadline allows and then
never returns to it. Information Retrieval was studied 1-5 August and examined
on 31 August: twenty-six days cold, with four more exams in the five days
around it.

Capacity is 359 h against 331 h of work, so there is no room to simply move
blocks later. The fix is interleaving. Each day is split into two lanes:

  learning  new material, earliest-deadline-first as before
  review    spaced retrieval on courses whose block has already closed

Roughly the last 75 minutes of a study day goes to review. That moves about a
fifth of every course's budget out of first-pass learning, which is the point:
spaced retrieval beats massed re-reading, and the total stays at 331 h.

Review touches follow an expanding interval after a block closes (+2, +5, +10,
+18 days), always with a consolidation touch inside the 48 hours before the
exam, and a repair pass guarantees no course is ever more than MAX_GAP days
without contact. That guarantee is asserted at build time.
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

# The review lane: the tail of each day, not extra time on top of it.
REVIEW_LANE_FREE = 1.25
REVIEW_LANE_EXAM = 1.0

# Share of a course's budget reserved for spaced review rather than first pass.
REVIEW_SHARE = 0.20

# No course may go longer than this without contact before its exam.
MAX_GAP = 5

# Expanding interval after a learning block closes.
INTERVALS = (2, 5, 10, 18, 28, 40)

MIN_TOUCH = 0.5
TOTAL_HOURS_EXPECTED = 331

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

EXAM_DAYS = {course[2] for course in PLAN}
NAME = {c[0]: c[1] for c in PLAN}
EXAM = {c[0]: c[2] for c in PLAN}
CFU = {c[0]: c[4] for c in PLAN}
HOURS = {c[0]: c[3] for c in PLAN}
DUE = {c[0]: (c[6] or c[2] - dt.timedelta(days=1)) for c in PLAN}


def days() -> list[dt.date]:
    return [START + dt.timedelta(days=i) for i in range((END - START).days + 1)]


def q(hours: float) -> float:
    """Quarter-hour granularity; nobody schedules seven-minute study blocks."""
    return round(hours * 4) / 4


# --------------------------------------------------------------------------- #
# lanes
# --------------------------------------------------------------------------- #

def lane_capacity(day: dt.date) -> tuple[float, float]:
    """(learning hours, review hours) available on a day."""
    if day in EXAM_DAYS:
        return EXAM_DAY_HOURS - REVIEW_LANE_EXAM, REVIEW_LANE_EXAM
    return FREE_DAY_HOURS - REVIEW_LANE_FREE, REVIEW_LANE_FREE


def day_capacity(day: dt.date) -> float:
    return EXAM_DAY_HOURS if day in EXAM_DAYS else FREE_DAY_HOURS


def schedule_learning(
    learn_hours: dict[str, float],
    review_used: dict[dt.date, float] | None = None,
) -> tuple[dict[dt.date, list[tuple[str, float]]], dict[str, dt.date]]:
    """Earliest-deadline-first over the learning lane.

    Kept from the original scheduler because feasibility still matters: this is
    the part that proves the plan fits at all. What changed is that it no longer
    owns the whole day.
    """
    review_used = review_used or {}
    remaining = dict(learn_hours)
    plan: dict[dt.date, list[tuple[str, float]]] = {}
    block_end: dict[str, dt.date] = {}

    for day in days():
        # The review lane is genuinely reserved, not merely a ceiling. Letting
        # learning eat whatever review does not use fills every day to the brim,
        # and then a gap has nowhere to be repaired into. The slack this leaves
        # is given back at the end by topping up review touches.
        capacity = day_capacity(day) - review_used.get(day, 0.0)
        slots: list[tuple[str, float]] = []
        for code in sorted(remaining, key=lambda c: (DUE[c], -remaining[c])):
            if capacity <= 0.01:
                break
            if remaining[code] <= 0.01 or DUE[code] < day:
                continue
            take = min(capacity, remaining[code])
            slots.append((code, q(take)))
            remaining[code] -= take
            capacity -= take
            block_end[code] = day
        plan[day] = slots

    unplaced = {NAME[c]: round(h, 2) for c, h in remaining.items() if h > 0.01}
    if unplaced:
        raise AssertionError(f"learning lane could not fit: {unplaced}")
    return plan, block_end


# --------------------------------------------------------------------------- #
# review
# --------------------------------------------------------------------------- #

def touch_days(code: str, closed: dt.date) -> list[dt.date]:
    """Expanding-interval touches, plus consolidation inside the last 48 hours."""
    exam = EXAM[code]
    wanted: list[dt.date] = []
    for gap in INTERVALS:
        when = closed + dt.timedelta(days=gap)
        if closed < when < exam:
            wanted.append(when)

    # Mandatory consolidation: the day before, or two days before if that day is
    # itself an exam and already crowded.
    for back in (1, 2):
        when = exam - dt.timedelta(days=back)
        if when > closed and when >= START:
            if when not in wanted:
                wanted.append(when)
            break

    return sorted(set(wanted))


def repair_gaps(code: str, closed: dt.date, touches: list[dt.date]) -> list[dt.date]:
    """Insert touches until no gap before the exam exceeds MAX_GAP days."""
    exam = EXAM[code]
    out = sorted(set(touches))
    cursor = closed
    result: list[dt.date] = []
    queue = list(out)
    while cursor < exam:
        nxt = queue[0] if queue else None
        if nxt is None or (nxt - cursor).days > MAX_GAP:
            candidate = cursor + dt.timedelta(days=MAX_GAP)
            if candidate >= exam:
                break
            result.append(candidate)
            cursor = candidate
            continue
        result.append(nxt)
        cursor = nxt
        queue.pop(0)
    return sorted(set(result))


def schedule_review(
    block_end: dict[str, dt.date], budget: dict[str, float]
) -> dict[dt.date, list[tuple[str, float]]]:
    """Place review touches in the review lane, respecting daily capacity."""
    wanted: dict[str, list[dt.date]] = {}
    for code, closed in block_end.items():
        planned = touch_days(code, closed)
        wanted[code] = repair_gaps(code, closed, planned)
    per_touch = {
        code: max(MIN_TOUCH, q(budget[code] / max(len(dates), 1)))
        for code, dates in wanted.items()
    }

    free = {day: lane_capacity(day)[1] for day in days()}
    plan: dict[dt.date, list[tuple[str, float]]] = {day: [] for day in days()}

    # Nearest exam first, then largest CFU. Measured recall is not available at
    # build time - it only exists once the app has been used - so the client can
    # re-order this later; the build cannot.
    requests: list[tuple[dt.date, str]] = [
        (day, code) for code, dates in wanted.items() for day in dates
    ]
    requests.sort(key=lambda r: (r[0], EXAM[r[1]], -CFU[r[1]]))

    for day, code in requests:
        need = per_touch[code]
        # Prefer the intended day, then walk backwards - never far forwards,
        # because a later touch could break the gap guarantee it was inserted to
        # satisfy. A touch may be split across days if one cannot hold it.
        for offset in (0, -1, 1, -2, -3):
            if need < MIN_TOUCH:
                break
            target = day + dt.timedelta(days=offset)
            if target < START or target >= EXAM[code] or target > END:
                continue
            available = free.get(target, 0)
            if available < MIN_TOUCH:
                continue
            take = q(min(need, available))
            if take < MIN_TOUCH:
                continue
            plan[target].append((code, take))
            free[target] -= take
            need -= take
        # If it still does not fit, drop it rather than overrunning the day. The
        # repair pass works on the merged schedule and can pay for a touch out
        # of a learning slot, which keeps both the day and the total intact.
    return plan


# --------------------------------------------------------------------------- #
# reporting and assertions
# --------------------------------------------------------------------------- #

def contact_days(schedule: dict[str, list], code: str) -> list[dt.date]:
    out = []
    for iso, slots in schedule.items():
        if any(s[0] == code for s in slots):
            out.append(dt.date.fromisoformat(iso))
    return sorted(out)


def days_cold(schedule: dict[str, list]) -> dict[str, tuple[int, int]]:
    """(days between last contact and the exam, worst gap before the exam)."""
    out: dict[str, tuple[int, int]] = {}
    for code in NAME:
        touches = [d for d in contact_days(schedule, code) if d < EXAM[code]]
        if not touches:
            out[code] = ((EXAM[code] - START).days, (EXAM[code] - START).days)
            continue
        last = (EXAM[code] - touches[-1]).days
        worst = last
        for a, b in zip(touches, touches[1:]):
            worst = max(worst, (b - a).days)
        out[code] = (last, worst)
    return out


def enforce_gaps(schedule: dict[str, list]) -> int:
    """Close any residual gap on the merged schedule.

    The per-course pass plans touches from where a block was expected to close,
    but EDF interleaves and placement nudges a touch by a day when a lane is
    full, so a six-day hole can survive both. This works on the final schedule,
    where the truth is, and it *moves* time rather than adding it: the touch is
    paid for out of the same course's largest learning slot, so the per-course
    total and the 331 h ceiling are untouched.
    """
    def spare(day: dt.date) -> float:
        return day_capacity(day) - sum(s[1] for s in schedule[day.isoformat()])

    def first_hole(code: str) -> dt.date | None:
        touches = [d for d in contact_days(schedule, code) if d < EXAM[code]]
        if not touches:
            return None
        for a, b in zip(touches + [EXAM[code]], touches[1:] + [EXAM[code]]):
            if (b - a).days > MAX_GAP:
                candidate = a + dt.timedelta(days=MAX_GAP)
                return candidate if candidate < EXAM[code] else None
        return None

    repairs = 0
    for _ in range(200):
        pending = [(c, first_hole(c)) for c in NAME]
        pending = [(c, h) for c, h in pending if h is not None]
        if not pending:
            break
        # Nearest exam first: its holes are the ones that cost marks soonest.
        code, latest = min(pending, key=lambda r: (EXAM[r[0]], -CFU[r[0]]))
        if True:
            # Any day from the hole back to just after the previous touch closes
            # it; prefer the latest with room, so the interval stays as long as
            # the rule allows.
            window = [
                latest - dt.timedelta(days=k)
                for k in range(MAX_GAP)
                if START <= latest - dt.timedelta(days=k) < EXAM[code]
            ]
            if not window:
                break
            donors = sorted(
                (
                    (iso, i, s)
                    for iso, slots in schedule.items()
                    for i, s in enumerate(slots)
                    if s[0] == code and s[2] == "learn" and s[1] > MIN_TOUCH
                ),
                key=lambda r: -r[2][1],
            )
            if not donors:
                break
            donor_iso, donor_index, donor_slot = donors[0]
            donor_day = dt.date.fromisoformat(donor_iso)

            target = next((d for d in window if spare(d) >= MIN_TOUCH), None)
            if target is None and False:
                # Every candidate day is full. Swap instead of overrunning: this
                # course gives up half an hour of learning on the donor day and
                # takes it as review on the target day, while some other course
                # moves half an hour of learning the other way. Both budgets and
                # both day totals come out unchanged. Moving another course's
                # learning earlier can never break its own deadline.
                # Prefer displacing a course that is already present on the donor
                # day. Moving half an hour of some course onto a day where it has
                # nothing else strands it there, and a stranded slot is a new
                # contact followed by a long gap - which is the very defect this
                # function exists to remove.
                swap = None
                for cand_iso, cand_index, cand_slot in donors:
                    cand_day = dt.date.fromisoformat(cand_iso)
                    present = {s[0] for s in schedule[cand_iso]}
                    for d in window:
                        if d <= cand_day:
                            continue
                        for i, s in enumerate(schedule[d.isoformat()]):
                            # Strict: the displaced half hour must land where
                            # that course already works, or it becomes a stray
                            # early contact followed by a long gap.
                            if s[0] == code or s[2] != "learn" or s[1] <= MIN_TOUCH:
                                continue
                            if s[0] not in present or DUE[s[0]] < cand_day:
                                continue
                            swap = (d, i, s)
                            break
                        if swap:
                            break
                    if swap:
                        donor_iso, donor_index, donor_slot = cand_iso, cand_index, cand_slot
                        break
                if swap is None:
                    break
                target, other_index, other_slot = swap
                schedule[target.isoformat()][other_index] = [
                    other_slot[0], q(other_slot[1] - MIN_TOUCH), "learn"
                ]
                schedule[donor_iso].append([other_slot[0], MIN_TOUCH, "learn"])

            if target is None:
                # Every day in the window is already at capacity. Half an hour of
                # retrieval matters more than a day finishing exactly on 7 h, so
                # the emptiest day runs 30 minutes long and the overrun is
                # reported; stacking two repairs on one day is not allowed.
                # Prefer a non-exam day with room; failing that the emptiest day
                # in the window runs 30 minutes long. A day already overrun is
                # never chosen twice.
                ranked = sorted(window, key=lambda d: (d in EXAM_DAYS, -spare(d)))
                target = next((d for d in ranked if spare(d) > -0.01), None)
                if target is None:
                    break
            schedule[donor_iso][donor_index] = [code, q(donor_slot[1] - MIN_TOUCH), "learn"]
            schedule[target.isoformat()].append([code, MIN_TOUCH, "review"])
            repairs += 1
    return repairs


def enforce_consolidation(schedule: dict[str, list]) -> int:
    """Guarantee contact inside the 48 hours before every exam.

    The gap rule alone permits a last touch five days out, which is not the same
    thing as walking in warm. This is the one slot that is never negotiable.
    """
    forced = 0
    for code in NAME:
        exam = EXAM[code]
        wanted = [exam - dt.timedelta(days=1), exam - dt.timedelta(days=2)]
        if any(d in contact_days(schedule, code) for d in wanted):
            continue
        donor = max(
            (
                (iso, i, s)
                for iso, slots in schedule.items()
                for i, s in enumerate(slots)
                if s[0] == code and s[2] == "learn" and s[1] > MIN_TOUCH
            ),
            key=lambda r: r[2][1],
            default=None,
        )
        if donor is None:
            continue
        iso, index, slot = donor

        def room(day: dt.date) -> float:
            return day_capacity(day) - sum(s[1] for s in schedule[day.isoformat()])

        # Prefer a non-exam day: an exam day is already only four hours long and
        # you are sitting a paper on it. This slot is non-negotiable, so it may
        # take the same 30-minute overrun the gap repair uses.
        ranked = sorted(
            (d for d in wanted if d >= START),
            key=lambda d: (d in EXAM_DAYS, -room(d)),
        )
        target = next((d for d in ranked if room(d) > -0.01), None)
        if target is None:
            continue
        schedule[iso][index] = [code, q(slot[1] - MIN_TOUCH), "learn"]
        schedule[target.isoformat()].append([code, MIN_TOUCH, "review"])
        forced += 1
    return forced


def top_up(schedule: dict[str, list]) -> float:
    """Spend each course's unscheduled hours on the touches it already has.

    Reserving the review lane leaves the plan short of the 331 h budget. Rather
    than invent new sessions, lengthen the review already scheduled: more time
    on retrieval is the point of the exercise, and adding minutes to an existing
    contact day cannot break the gap rule.
    """
    added = 0.0
    for code in NAME:
        booked = sum(s[1] for slots in schedule.values() for s in slots if s[0] == code)
        short = q(HOURS[code] - booked)
        if short <= 0:
            continue
        # Latest first: extra retrieval is worth most close to the exam.
        slots = sorted(
            (
                (iso, i)
                for iso, day_slots in schedule.items()
                for i, s in enumerate(day_slots)
                if s[0] == code
            ),
            key=lambda r: r[0],
            reverse=True,
        )
        for iso, index in slots:
            if short <= 0:
                break
            day = dt.date.fromisoformat(iso)
            spare = day_capacity(day) - sum(s[1] for s in schedule[iso])
            take = q(min(short, spare))
            if take <= 0:
                continue
            schedule[iso][index][1] = q(schedule[iso][index][1] + take)
            short = q(short - take)
            added += take

        if short <= 0:
            continue
        # Still short: open new review days between this course's first contact
        # and its exam. An extra contact day can only help the gap rule.
        contacts = contact_days(schedule, code)
        if not contacts:
            continue
        window = [
            d for d in days()
            if contacts[0] <= d < EXAM[code]
        ]
        for day in sorted(window, reverse=True):
            if short <= 0:
                break
            iso = day.isoformat()
            spare = day_capacity(day) - sum(s[1] for s in schedule[iso])
            take = q(min(short, spare))
            if take < MIN_TOUCH:
                continue
            schedule[iso].append([code, take, "review"])
            short = q(short - take)
            added += take
    return added


def verify(schedule: dict[str, list], total: float) -> None:
    assert abs(total - TOTAL_HOURS_EXPECTED) < 0.6, (
        f"total hours drifted to {total}, expected {TOTAL_HOURS_EXPECTED}"
    )
    for code, name, exam, _h, _c, _camp, _due in PLAN:
        book_by = BOOK_BY.get(code)
        assert book_by is not None and book_by < exam, (
            f"{name}: booking deadline {book_by} is not before the exam {exam}"
        )
    cold = days_cold(schedule)
    bad = {NAME[c]: v for c, v in cold.items() if v[1] > MAX_GAP}
    assert not bad, f"courses exceeding the {MAX_GAP}-day contact rule: {bad}"
    late = {NAME[c]: v[0] for c, v in cold.items() if v[0] > 2}
    assert not late, f"courses with no contact in the 48 h before the exam: {late}"
    for iso, slots in schedule.items():
        day = dt.date.fromisoformat(iso)
        hours = sum(s[1] for s in slots)
        assert hours <= day_capacity(day) + 0.51, (
            f"{iso} carries {hours} h against a capacity of {day_capacity(day)} h"
        )
    for code in NAME:
        booked = sum(
            s[1] for slots in schedule.values() for s in slots if s[0] == code
        )
        assert abs(booked - HOURS[code]) < 0.26, (
            f"{NAME[code]}: {booked} h scheduled against a budget of {HOURS[code]} h"
        )


BOOK_BY = {
    "509496": dt.date(2026, 8, 26), "509521": dt.date(2026, 8, 27),
    "509519": dt.date(2026, 8, 28), "509494": dt.date(2026, 8, 29),
    "509495": dt.date(2026, 8, 30), "509485": dt.date(2026, 9, 3),
    "509477": dt.date(2026, 9, 4), "509481": dt.date(2026, 9, 6),
    "509486": dt.date(2026, 9, 10), "509492": dt.date(2026, 9, 17),
    "509488": dt.date(2026, 9, 19),
}


def _pipeline() -> tuple[dict[str, list], float]:
    """Build a merged schedule from whatever PLAN currently holds."""
    learn_hours = {c[0]: q(c[3] * (1 - REVIEW_SHARE)) for c in PLAN}
    review_budget = {c[0]: q(c[3] * REVIEW_SHARE) for c in PLAN}
    review_used: dict[dt.date, float] = {}
    learning: dict[dt.date, list] = {}
    review: dict[dt.date, list] = {}

    for _ in range(6):
        learning, block_end = schedule_learning(learn_hours, review_used)
        review = schedule_review(block_end, review_budget)
        placed = {code: 0.0 for code in NAME}
        review_used = {}
        for day, slots in review.items():
            for code, hours in slots:
                placed[code] += hours
                review_used[day] = review_used.get(day, 0.0) + hours
        adjusted = {code: q(HOURS[code] - placed[code]) for code in NAME}
        if adjusted == learn_hours:
            break
        learn_hours = adjusted
    learning, block_end = schedule_learning(learn_hours, review_used)

    merged: dict[str, list] = {}
    for day in days():
        slots = [[c, h, "learn"] for c, h in learning[day]]
        slots += [[c, h, "review"] for c, h in review.get(day, [])]
        merged[day.isoformat()] = slots

    enforce_consolidation(merged)
    enforce_gaps(merged)
    top_up(merged)

    for iso, slots in merged.items():
        combined: dict[tuple[str, str], float] = {}
        for code, hours, kind in slots:
            combined[(code, kind)] = q(combined.get((code, kind), 0.0) + hours)
        merged[iso] = [[code, hours, kind] for (code, kind), hours in combined.items()]

    total = sum(s[1] for slots in merged.values() for s in slots)
    return merged, total


def plan_for(subset: list) -> dict:
    """Schedule an alternative set of courses, for the drop simulator.

    The module keeps its tables as globals because every helper reads them; the
    honest way to schedule a different set is to rebind them for the duration
    and put them back. Not elegant, but it means the simulator runs the real
    scheduler rather than a second implementation that could drift from it.
    """
    global PLAN, EXAM_DAYS, NAME, EXAM, CFU, HOURS, DUE
    saved = (PLAN, EXAM_DAYS, NAME, EXAM, CFU, HOURS, DUE)
    try:
        PLAN = subset
        EXAM_DAYS = {c[2] for c in subset}
        NAME = {c[0]: c[1] for c in subset}
        EXAM = {c[0]: c[2] for c in subset}
        CFU = {c[0]: c[4] for c in subset}
        HOURS = {c[0]: c[3] for c in subset}
        DUE = {c[0]: (c[6] or c[2] - dt.timedelta(days=1)) for c in subset}

        merged, total = _pipeline()
        cold = days_cold(merged)
        overrun = [
            iso for iso, slots in merged.items()
            if sum(s[1] for s in slots) > day_capacity(dt.date.fromisoformat(iso)) + 0.01
        ]
        peak = max(
            (sum(s[1] for s in slots) for slots in merged.values()), default=0.0
        )
        capacity = sum(day_capacity(d) for d in days())
        return {
            "total": round(total, 2),
            # Slack is the number that decides whether a bad week is survivable.
            "slack": round(capacity - total, 2),
            "worst_gap": max((v[1] for v in cold.values()), default=0),
            "overrun_days": len(overrun),
            "peak_day": round(peak, 2),
        }
    finally:
        PLAN, EXAM_DAYS, NAME, EXAM, CFU, HOURS, DUE = saved


def main() -> int:
    # Compare against the original single-pass schedule, not against whatever
    # this script wrote last time, or the table flatters itself.
    baseline = Path("reference/calendar_baseline.json")
    current = Path("data/audit/calendar.json")
    if not baseline.exists() and current.exists():
        payload = json.loads(current.read_text())
        if not any(
            len(s) > 2 and s[2] == "review"
            for slots in payload["days"].values()
            for s in slots
        ):
            baseline.write_text(json.dumps(payload, indent=1))
    before = json.loads(baseline.read_text())["days"] if baseline.exists() else {}

    merged, total = _pipeline()

    return merged, total


def plan_for(subset: list) -> dict:
    """Schedule an alternative set of courses, for the drop simulator.

    The module keeps its tables as globals because every helper reads them; the
    honest way to schedule a different set is to rebind them for the duration
    and put them back. Not elegant, but it means the simulator runs the real
    scheduler rather than a second implementation that could drift from it.
    """
    global PLAN, EXAM_DAYS, NAME, EXAM, CFU, HOURS, DUE
    saved = (PLAN, EXAM_DAYS, NAME, EXAM, CFU, HOURS, DUE)
    try:
        PLAN = subset
        EXAM_DAYS = {c[2] for c in subset}
        NAME = {c[0]: c[1] for c in subset}
        EXAM = {c[0]: c[2] for c in subset}
        CFU = {c[0]: c[4] for c in subset}
        HOURS = {c[0]: c[3] for c in subset}
        DUE = {c[0]: (c[6] or c[2] - dt.timedelta(days=1)) for c in subset}

        merged, total = _pipeline()
        cold = days_cold(merged)
        overrun = [
            iso for iso, slots in merged.items()
            if sum(s[1] for s in slots) > day_capacity(dt.date.fromisoformat(iso)) + 0.01
        ]
        peak = max(
            (sum(s[1] for s in slots) for slots in merged.values()), default=0.0
        )
        capacity = sum(day_capacity(d) for d in days())
        return {
            "total": round(total, 2),
            # Slack is the number that decides whether a bad week is survivable.
            "slack": round(capacity - total, 2),
            "worst_gap": max((v[1] for v in cold.values()), default=0),
            "overrun_days": len(overrun),
            "peak_day": round(peak, 2),
        }
    finally:
        PLAN, EXAM_DAYS, NAME, EXAM, CFU, HOURS, DUE = saved


def main() -> int:
    # Compare against the original single-pass schedule, not against whatever
    # this script wrote last time, or the table flatters itself.
    baseline = Path("reference/calendar_baseline.json")
    current = Path("data/audit/calendar.json")
    if not baseline.exists() and current.exists():
        payload = json.loads(current.read_text())
        if not any(
            len(s) > 2 and s[2] == "review"
            for slots in payload["days"].values()
            for s in slots
        ):
            baseline.write_text(json.dumps(payload, indent=1))
    before = json.loads(baseline.read_text())["days"] if baseline.exists() else {}

    # The review lane truncates a touch when the day is full, so the share
    # actually placed is never exactly REVIEW_SHARE. Iterate: whatever review
    # cannot take, learning absorbs, and the per-course total stays exact.
    learn_hours = {c[0]: q(c[3] * (1 - REVIEW_SHARE)) for c in PLAN}
    review_budget = {c[0]: q(c[3] * REVIEW_SHARE) for c in PLAN}
    learning: dict[dt.date, list[tuple[str, float]]] = {}
    review: dict[dt.date, list[tuple[str, float]]] = {}

    # Two passes: a provisional learning pass fixes where each block closes, the
    # review skeleton is built from that, and the final learning pass fills the
    # space the skeleton leaves. Learning absorbs whatever review does not use,
    # so the per-course totals stay exact.
    review_used: dict[dt.date, float] = {}
    for _ in range(6):
        learning, block_end = schedule_learning(learn_hours, review_used)
        review = schedule_review(block_end, review_budget)
        placed = {code: 0.0 for code in NAME}
        review_used = {}
        for day, slots in review.items():
            for code, hours in slots:
                placed[code] += hours
                review_used[day] = review_used.get(day, 0.0) + hours
        adjusted = {code: q(HOURS[code] - placed[code]) for code in NAME}
        if adjusted == learn_hours:
            break
        learn_hours = adjusted
    learning, block_end = schedule_learning(learn_hours, review_used)

    merged: dict[str, list] = {}
    total = 0.0
    for day in days():
        slots = [(c, h, "learn") for c, h in learning[day]]
        slots += [(c, h, "review") for c, h in review.get(day, [])]
        merged[day.isoformat()] = [[c, h, kind] for c, h, kind in slots]
        total += sum(h for _c, h, _k in slots)

    # Consolidation first: it is the one slot that cannot move, so it must claim
    # its day before the gap repairs fill the crunch week around it.
    forced = enforce_consolidation(merged)
    repairs = enforce_gaps(merged) + forced
    added = top_up(merged)

    # Repairs can leave a course with two separate slots of the same kind on one
    # day, which reads as two sessions when it is one.
    for iso, slots in merged.items():
        combined: dict[tuple[str, str], float] = {}
        for code, hours, kind in slots:
            combined[(code, kind)] = q(combined.get((code, kind), 0.0) + hours)
        merged[iso] = [[code, hours, kind] for (code, kind), hours in combined.items()]

    total = sum(s[1] for slots in merged.values() for s in slots)
    verify(merged, total)
    if repairs or added:
        print(f"gap repair: {repairs} touch(es) inserted; {added:.2f} h topped up onto review\n")

    after = days_cold(merged)
    before_cold = days_cold(before) if before else {}

    print(f"{'course':<32} {'before':>18} {'after':>18}")
    print(f"{'':<32} {'cold  worst':>18} {'cold  worst':>18}")
    for code, name, *_ in PLAN:
        b = before_cold.get(code)
        a = after[code]
        btxt = f"{b[0]:>4}  {b[1]:>5}" if b else "     -      -"
        print(f"{name[:32]:<32} {btxt:>18} {a[0]:>10}  {a[1]:>5}")
    worst_before = max((v[1] for v in before_cold.values()), default=0)
    print(f"\nworst gap before: {worst_before} days   after: {max(v[1] for v in after.values())} days")
    print(f"total hours: {total:.2f} (learning {sum(h for d in learning.values() for _c,h in d):.2f}, "
          f"review {sum(h for d in review.values() for _c,h in d):.2f})")

    Path("data/audit/calendar.json").write_text(
        json.dumps(
            {
                "generated": dt.date.today().isoformat(),
                "total_hours": round(total, 2),
                "total_cfu": sum(c[4] for c in PLAN),
                "exam_day_hours": EXAM_DAY_HOURS,
                "free_day_hours": FREE_DAY_HOURS,
                "review_lane_free": REVIEW_LANE_FREE,
                "review_share": REVIEW_SHARE,
                "max_gap_days": MAX_GAP,
                "days_cold": {c: {"last": v[0], "worst": v[1]} for c, v in after.items()},
                "days": merged,
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
