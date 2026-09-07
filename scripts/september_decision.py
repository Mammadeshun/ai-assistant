#!/usr/bin/env python3
"""What can actually be sat in the September 2026 window, and at what cost.

Two separate questions, deliberately kept apart:

  1. How many sittings can be physically attended? A pure scheduling question -
     one exam per day, courses that share a date compete. Bipartite matching.
  2. How many can be prepared for? An arithmetic question - hours available
     against hours needed, taken from data/audit/hours_final.json.

The first number is always the larger one, and reporting it alone would be
dishonest. The plan is the second.

Inputs are live: Esse3's AppelliF.do for the open sittings and
BachecaPrenotazioni.do for what is already booked, both refetched today.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TODAY = dt.date(2026, 9, 7)
LAST_DAY = dt.date(2026, 9, 25)

# Hours the student can actually put in per day. The August plan was built at
# 7h on a free day; that is the honest rate to keep using.
DAILY_HOURS = 7.0
# A day spent sitting an exam is not a day spent preparing.
EXAM_DAY_HOURS = 2.0

HOURS = json.loads(Path("data/audit/hours_final.json").read_text())
# Two courses were never costed: no papers were ever found for either, so the
# hours model has nothing to work from. Priced at the mean of same-CFU courses
# and marked, rather than silently omitted.
ESTIMATED = {
    "509494": {"name": "Brain Modelling", "cfu": 6, "hours": 28,
               "basis": "ESTIMATE - project 30% + written 70%, project mark carries"},
    "504703": {"name": "Computer Vision", "cfu": 6, "hours": 28,
               "basis": "ESTIMATE - no papers located"},
}
HOURS = {**HOURS, **ESTIMATED}

# course code -> [(exam date, booking closes or None when already booked)]
SITTINGS: dict[str, list[tuple[str, str | None]]] = {
    "509496": [("2026-09-15", "2026-09-10")],
    "509486": [("2026-09-15", "2026-09-10")],
    "509519": [("2026-09-16", "2026-09-11")],
    "509487": [("2026-09-17", "2026-09-12")],
    "504464": [("2026-09-17", "2026-09-14")],
    "509498": [("2026-09-18", "2026-09-13")],
    "509478": [("2026-09-21", "2026-09-16")],
    "509521": [("2026-09-21", "2026-09-16")],
    "504703": [("2026-09-22", "2026-09-17")],
    "509492": [("2026-09-22", "2026-09-17")],
    "509483": [("2026-09-23", "2026-09-18")],
    "509495": [("2026-09-24", "2026-09-19")],
    "509493": [("2026-09-24", "2026-09-19")],
    "510638": [("2026-09-24", "2026-09-19")],
    "509494": [("2026-09-25", "2026-09-20")],
    "509481": [("2026-09-25", "2026-09-20")],
    "509485": [("2026-09-25", "2026-09-20")],
    "510109": [("2026-09-25", "2026-09-20")],
    # Booked already and not cancellable ("iscrizione chiusa"), each with a
    # second sitting later in the month.
    "509477": [("2026-09-09", None), ("2026-09-25", "2026-09-20")],
    "509488": [("2026-09-10", None), ("2026-09-24", "2026-09-19")],
}
LOCKED_IN = {"2026-09-09": "509477", "2026-09-10": "509488"}


def name(code: str) -> str:
    return HOURS[code]["name"]


def budget(exam_days: set[str], rate: float = DAILY_HOURS) -> float:
    """Study hours between tomorrow and the last exam."""
    total = 0.0
    day = TODAY + dt.timedelta(days=1)
    while day <= LAST_DAY:
        total += EXAM_DAY_HOURS if day.isoformat() in exam_days else rate
        day += dt.timedelta(days=1)
    return total


def best_set(cap: float | None) -> tuple[list[tuple[str, str]], float, int]:
    """Most CFU obtainable, one exam per day, within `cap` hours of prep.

    The two locked-in sittings are attended regardless - they cannot be
    cancelled - but they are not counted as achievable unless they are also
    prepared for, and their days are not available for anything else.
    """
    best: dict = {"cfu": -1}
    codes = sorted(SITTINGS, key=lambda c: -HOURS[c]["cfu"])

    def walk(i: int, used: frozenset[str], hours: float, picked: list[tuple[str, str]]) -> None:
        nonlocal best
        if i == len(codes):
            cfu = sum(HOURS[c]["cfu"] for c, _ in picked)
            if cfu > best["cfu"] or (cfu == best["cfu"] and hours < best["hours"]):
                best = {"cfu": cfu, "hours": hours, "picked": list(picked)}
            return
        code = codes[i]
        for date, _ in SITTINGS[code]:
            if date in used or LOCKED_IN.get(date) not in (None, code):
                continue
            cost = HOURS[code]["hours"]
            if cap is not None and hours + cost > cap:
                continue
            picked.append((code, date))
            walk(i + 1, used | {date}, hours + cost, picked)
            picked.pop()
        walk(i + 1, used, hours, picked)

    walk(0, frozenset(), 0.0, [])
    return best["picked"], best["hours"], best["cfu"]


def show(title: str, picked: list[tuple[str, str]], hours: float, cfu: int, cap: float) -> None:
    print(f"\n{title}")
    print(f"  {len(picked)} exams, {cfu} CFU, {hours:.0f}h of preparation "
          f"against {cap:.0f}h available")
    for code, date in sorted(picked, key=lambda p: p[1]):
        close = dict(SITTINGS[code])[date]
        when = "BOOKED (cannot cancel)" if close is None else f"book by {close[8:10]}/{close[5:7]}"
        print(f"    {date[8:10]}/{date[5:7]}  {name(code):<28} {HOURS[code]['cfu']:>2} CFU  "
              f"{HOURS[code]['hours']:>3}h  {when}")


def main() -> int:
    exam_days = {d for v in SITTINGS.values() for d, _ in v}
    print(f"September 2026 window: {TODAY + dt.timedelta(days=1)} to {LAST_DAY} "
          f"({(LAST_DAY - TODAY).days} days)")

    print("\nAlready booked and no longer cancellable:")
    for date, code in sorted(LOCKED_IN.items()):
        second = [d for d, _ in SITTINGS[code] if d != date]
        print(f"  {date[8:10]}/{date[5:7]}  {name(code):<28} "
              f"{HOURS[code]['hours']:>3}h needed; sits again {second[0][8:10]}/{second[0][5:7]}")

    # 1. Physical ceiling: ignore preparation entirely.
    picked, hours, cfu = best_set(None)
    cap = budget({d for _, d in picked})
    show("CEILING - every sitting that can be physically attended:", picked, hours, cfu, cap)
    print(f"  >> needs {hours:.0f}h across {(LAST_DAY - TODAY).days} days = "
          f"{hours / (LAST_DAY - TODAY).days:.1f} h/day, every day, starting tomorrow.")
    print(f"  >> deficit against a 7h/day rate: {hours - cap:.0f}h short.")

    # 2. What the hours actually buy.
    for rate, label in ((7.0, "sustainable (the rate the August plan assumed)"),
                        (10.0, "hard push")):
        # The budget depends on which days are exam days, which depends on the
        # plan, which depends on the budget. Two passes settle it.
        cap = budget({"2026-09-09", "2026-09-10"}, rate)
        picked, hours, cfu = best_set(cap)
        cap2 = budget({d for _, d in picked} | {"2026-09-09", "2026-09-10"}, rate)
        picked, hours, cfu = best_set(cap2)
        show(f"PLAN at {rate:.0f}h/day - {label}:", picked, hours, cfu, cap2)
        deferred = sorted(set(SITTINGS) - {c for c, _ in picked},
                          key=lambda c: -HOURS[c]["cfu"])
        print(f"    deferred to Jan/Feb 2027 ({len(deferred)} exams, "
              f"{sum(HOURS[c]['cfu'] for c in deferred)} CFU, "
              f"{sum(HOURS[c]['hours'] for c in deferred)}h):")
        for code in deferred:
            print(f"      {name(code):<28} {HOURS[code]['cfu']:>2} CFU  {HOURS[code]['hours']:>3}h")

    print("""
CAVEATS THAT CHANGE THESE NUMBERS
  509498 AI Comm & Marketing  The sitting on 18/09 is open and bookable, but
      the compulsory lab project gates the written exam and both 2026
      submission windows closed with nothing submitted. 16h is the cheapest
      6 CFU on the board and it may not be claimable at all. Confirm with the
      lecturer before spending the booking.
  509477 / 509488 on 09/09 and 10/09  Booked, uncancellable, and unprepared -
      but both sit again on 25/09 and 24/09. Sitting them costs two days and
      nothing else: no penalty attaches to a failed or withdrawn attempt, and
      seeing the real paper is worth more than the day. Go, read it, leave.
  Same-day sittings are treated as mutually exclusive. If two exams on one date
      run at different hours both could be sat; Esse3's list does not publish
      times. Worth one email before writing off 24/09 and 25/09, which carry
      four and five sittings respectively.
  509494 Brain Modelling and 504703 Computer Vision are ESTIMATES - no past
      papers were ever located for either, so the hours model has no input.""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
