#!/usr/bin/env python3
"""Turn the scoring into a plan: what to sit, and what to do each day.

    python plan.py [--hours-per-day 7]

Two constraints decide the exam set, and they are enforced separately because
they fail differently:

  physical   one sitting per day. Courses that share a date compete, and no
             amount of preparation resolves that.
  budget     hours available before the last chosen exam, against hours needed.
             Exceeding it does not produce a worse mark, it produces failed
             exams and wasted sittings.

The calendar is built backwards from each exam date so the drilling lands
against the exam it is for, and it deliberately spends less than the day's
capacity: one lost day a week is absorbed up front, because a plan with no
slack is a plan that is wrong by Wednesday.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA, ANALYSIS = ROOT / "data", ROOT / "analysis"

LOST_DAY_PER_WEEK = 1        # absorbed up front, not discovered later
DRILL_WINDOW_DAYS = 2        # last 48h before a paper: past papers only
MIN_WEEKLY_HOURS = 30


def parse_date(text: str) -> dt.date:
    day, month, year = text.split("/")
    return dt.date(int(year), int(month), int(day))


def cost_of(row: dict) -> float:
    """Hours to budget for a course. See the note in walk() on unmeasured ones."""
    return row["hours_low"] if row.get("measured", True) else row["hours_high"]


def feasible(picked: list[dict], today: dt.date, hours_per_day: float) -> bool:
    """Can every exam's preparation actually happen before that exam sits?

    A single total budget is the wrong constraint and was quietly producing
    impossible plans. The autumn sittings cluster into ten days, so "216 hours
    are available before the last exam" says nothing about whether the 42 hours
    for an exam seven days away can be found. Preparation for an exam has to
    fit before that exam, not before the last one.

    This is the earliest-deadline-first feasibility test: walk the exams in
    date order and require the running total of hours to fit in the days
    available up to each one.
    """
    running = 0.0
    for row in sorted(picked, key=lambda r: parse_date(r["sitting"]["exam_date"])):
        running += cost_of(row)
        days = (parse_date(row["sitting"]["exam_date"]) - today).days
        if days <= 0 or running > days * hours_per_day:
            return False
    return True


def choose(rows: list[dict], budget_hours: float, today: dt.date | None = None,
           hours_per_day: float = 7.0) -> tuple[list[dict], list[dict]]:
    """Most CFU that fits both constraints. Exhaustive: the candidate set is
    small enough that there is no reason to approximate."""
    today = today or dt.date.today()
    candidates = [r for r in rows if r.get("sitting")]
    best: dict = {"cfu": -1, "picked": []}

    def walk(index: int, used: set[str], hours: float, picked: list[dict]) -> None:
        nonlocal best
        if index == len(candidates):
            if not feasible(picked, today, hours_per_day):
                return
            cfu = sum(r["cfu"] for r in picked)
            expected = sum(r["cfu"] * r["p_pass"] for r in picked)
            if (cfu, expected) > (best["cfu"], best.get("expected", 0)):
                best = {"cfu": cfu, "expected": expected, "hours": hours,
                        "picked": list(picked)}
            return
        row = candidates[index]
        date = row["sitting"]["exam_date"]
        # For a course nothing could be measured about, hours_low is the floor
        # the model emits with no evidence, not an estimate. Budgeting at that
        # floor makes the unknown courses look like the cheapest on the board
        # and pulls them into the plan ahead of courses that were actually
        # counted - Computer Vision, Ethics and Web and Social took 24 of 66
        # CFU that way. Cost them at the top of their range instead, so an
        # unknown has to be worth committing to, not merely cheap to assume.
        cost = cost_of(row)
        if date not in used and hours + cost <= budget_hours:
            picked.append(row)
            walk(index + 1, used | {date}, hours + cost, picked)
            picked.pop()
        walk(index + 1, used, hours, picked)

    walk(0, set(), 0.0, [])
    chosen = sorted(best["picked"], key=lambda r: parse_date(r["sitting"]["exam_date"]))
    dropped = [r for r in rows if r not in chosen]
    return chosen, dropped


def build_calendar(chosen: list[dict], start: dt.date, hours_per_day: float) -> list[dict]:
    """Backwards from each exam, so drilling lands where it is needed."""
    if not chosen:
        return []
    last = max(parse_date(r["sitting"]["exam_date"]) for r in chosen)
    exam_days = {parse_date(r["sitting"]["exam_date"]): r for r in chosen}

    days: list[dict] = []
    day = start
    while day <= last:
        days.append({"date": day, "blocks": [], "exam": exam_days.get(day),
                     "capacity": 0.0 if day in exam_days else hours_per_day})
        day += dt.timedelta(days=1)
    # One lost day a week, taken from the least-pressured days: absorbing it up
    # front is honest, discovering it later is not.
    free = [d for d in days if not d["exam"]]
    for index in range(LOST_DAY_PER_WEEK * (len(days) // 7 + 1)):
        position = int((index + 0.5) * len(free) / max(1, LOST_DAY_PER_WEEK * (len(days)//7 + 1)))
        if position < len(free):
            free[position]["capacity"] = 0.0
            free[position]["buffer"] = True

    for row in sorted(chosen, key=lambda r: parse_date(r["sitting"]["exam_date"])):
        exam_day = parse_date(row["sitting"]["exam_date"])
        remaining = float(row["hours_low"])
        drill = remaining * 0.4
        # Fill backwards: the two days before the exam take drilling only.
        for entry in sorted([d for d in days if d["date"] < exam_day],
                            key=lambda d: d["date"], reverse=True):
            if remaining <= 0:
                break
            spare = entry["capacity"] - sum(b["hours"] for b in entry["blocks"])
            if spare <= 0.25:
                continue
            in_drill_window = (exam_day - entry["date"]).days <= DRILL_WINDOW_DAYS
            take = min(spare, remaining, 4.0)
            kind = "past papers" if (in_drill_window or drill > 0) else "content"
            if kind == "past papers":
                drill -= take
            entry["blocks"].append({"course": row["name"], "code": row["code"],
                                    "hours": round(take, 2), "kind": kind,
                                    "for_exam": row["sitting"]["exam_date"]})
            remaining -= take
        row["unplaced_hours"] = round(max(0.0, remaining), 1)
    return days


def write_plan(chosen: list[dict], dropped: list[dict], days: list[dict],
               hours_per_day: float, budget: float, esse3: dict) -> None:
    today = dt.date.today()
    out = [
        "# PLAN", "",
        f"Built {today.isoformat()} from `data/scoring.json`, which is built from "
        f"files on disk. Nothing here is a guess; where something could not be "
        f"measured it says so.", "",
        f"**{esse3['cfu_passed']} CFU passed, {esse3['cfu_remaining']} remaining of "
        f"{esse3['cfu_required']}.** Budget to the last chosen exam: "
        f"**{budget:.0f}h** at {hours_per_day:g}h a day with one lost day a week "
        f"already absorbed.", "",
        "## The exam set", "",
    ]
    if not chosen:
        out += ["Nothing fits. Every open sitting costs more preparation than the "
                "days remaining can supply.", ""]
    total_cfu = sum(r["cfu"] for r in chosen)
    expected = sum(r["cfu"] * r["p_pass"] for r in chosen)
    total_hours = sum(r["hours_low"] for r in chosen)
    out += [
        f"**{len(chosen)} exams, {total_cfu} CFU, {total_hours}h of preparation.** "
        f"Expected yield {expected:.0f} CFU "
        f"({expected/max(total_cfu,1):.0%} of what is attempted).", "",
        "| Date | Exam | CFU | Hours | P(pass) | Book by | Why |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in chosen:
        sitting = row["sitting"]
        why = []
        if row["predictability"] and row["predictability"] >= 4:
            why.append(f"papers repeat (pred. {row['predictability']})")
        if row["papers"] >= 5:
            why.append(f"{row['papers']} papers to drill")
        if row["solutions"]:
            why.append(f"{row['solutions']} answer keys")
        if row["cost_per_pass"] <= 60:
            why.append(f"cheapest cost/pass ({row['cost_per_pass']})")
        out.append(
            f"| {sitting['exam_date']} | {row['name'][:34]} | {row['cfu']} "
            f"| {row['hours_low']}h | {row['p_pass']} | "
            f"{sitting['booking_closes'] or '—'} | {'; '.join(why[:3]) or 'fits the window'} |")
    out.append("")

    for row in chosen:
        out += [f"### {row['name']} — {row['sitting']['exam_date']}", ""]
        reasons = [
            f"- {row['cfu']} CFU for {row['hours_low']}–{row['hours_high']}h; "
            f"cost per pass {row['cost_per_pass']}, the ranking metric.",
            f"- Predictability {row['predictability'] or 'not measurable'}: "
            f"{row['predictability_basis']}.",
            f"- {row['papers']} past papers, {row['solutions']} with solutions, "
            f"{row['questions']} questions extracted to drill against.",
        ]
        if row["flags"]:
            reasons.append(f"- Risks: {'; '.join(row['flags'])}.")
        if row.get("unplaced_hours"):
            reasons.append(f"- **{row['unplaced_hours']}h could not be placed** in the "
                           "calendar before the exam. Treat this one as at risk.")
        out += reasons[:5] + [""]

    out += ["## Registration checklist", ""]
    booked = {b["code"]: b for b in esse3["bookings"]}
    out += ["| Book by | Exam | Date | Status |", "|---|---|---|---|"]
    for row in sorted(chosen, key=lambda r: r["sitting"]["booking_closes"] or "9"):
        sitting = row["sitting"]
        state = "already booked" if row["code"] in booked else "**NOT BOOKED**"
        out.append(f"| {sitting['booking_closes'] or '—'} | {row['name'][:34]} "
                   f"| {sitting['exam_date']} | {state} |")
    out += ["",
            "Sitting an exam you are not ready for is close to free: an Italian "
            "written exam can be withdrawn from (*ritiro*) on the day, and a "
            "refusal or a fail costs the sitting and nothing else — no penalty "
            "attaches to the transcript. Where a course has a second sitting "
            "later in the same session, the earlier one is a free look at the "
            "real paper. Book the marginal ones.", ""]

    already = [b for b in esse3["bookings"]
               if b["exam_date"] and parse_date(b["exam_date"]) >= today]
    if already:
        out += ["### Booked already and not cancellable", ""]
        for booking in already:
            out.append(f"- **{booking['exam_date']} {booking['name'][:44]}** — "
                       f"{booking['cancel_note'] or 'cannot be cancelled'}.")
        out.append("")

    out += ["## Day by day", "",
            "Built backwards from each exam date. The last 48h before a paper is "
            "past-paper drilling only. Blank days are the absorbed lost day.", "",
            "| Date | | Hours | Work |", "|---|---|---|---|"]
    for entry in days:
        label = entry["date"].strftime("%a %d %b")
        if entry["exam"]:
            row = entry["exam"]
            out.append(f"| {label} | **EXAM** | — | **{row['name'][:40]}** |")
            continue
        if not entry["blocks"]:
            out.append(f"| {label} | buffer | — | absorbed lost day / catch-up |")
            continue
        work = "; ".join(f"{b['course'][:26]} {b['hours']:g}h ({b['kind']})"
                         for b in entry["blocks"])
        total = sum(b["hours"] for b in entry["blocks"])
        out.append(f"| {label} | | {total:g}h | {work} |")
    out.append("")

    weeks = max(1, len(days) / 7)
    planned = sum(b["hours"] for d in days for b in d["blocks"])
    out += [f"Planned load: {planned:.0f}h over {len(days)} days "
            f"({planned/weeks:.0f}h a week"
            + ("" if planned/weeks >= MIN_WEEKLY_HOURS else
               f", below the {MIN_WEEKLY_HOURS}h target — the window is the "
               f"binding constraint, not willingness") + ").", ""]

    out += ["## Sequencing and go/no-go", "",
            "- When two exams are three days apart, the nearer one owns the "
            "48h before it outright; the further one gets the days before that. "
            "Splitting the final two days between both loses both.",
            "- If you fall behind, drop the exam with the **highest cost per "
            "pass** among those still ahead — not the one you like least. That "
            "is the one buying the fewest CFU per hour.",
            "- Sit anything already booked even if unprepared: withdrawal is "
            "free and seeing the real paper is worth the day."]
    for row in chosen:
        exam = parse_date(row["sitting"]["exam_date"])
        gate = exam - dt.timedelta(days=4)
        out.append(f"- **{gate.isoformat()}** — if you cannot work a "
                   f"{row['name'][:30]} past paper unaided by this date, drop it "
                   f"and move the hours to whatever is next in the ranking.")
    out.append("")

    out += ["## Rollover to January–February 2027", "",
            "Winter dates are not published yet — Esse3 lists nothing beyond "
            "2 December 2026, so these are deferred, not scheduled.", "",
            "| Exam | CFU | Hours | Why not now | Pre-build now |", "|---|---|---|---|---|"]
    for row in sorted(dropped, key=lambda r: -r["cfu"]):
        if not row.get("sitting"):
            reason = "no open sitting"
        elif any(c["sitting"]["exam_date"] == row["sitting"]["exam_date"] for c in chosen):
            reason = f"date clash on {row['sitting']['exam_date']}"
        else:
            reason = "outside the hours budget"
        prebuild = "—"
        if "project component" in row["flags"]:
            prebuild = "**start the project now** — it is calendar time, not study time"
        elif row["papers"] == 0:
            prebuild = "ask the lecturer for papers; there are none in the archive"
        out.append(f"| {row['name'][:32]} | {row['cfu']} | {row['hours_low']}h "
                   f"| {reason} | {prebuild} |")
    out.append("")

    out += ["## Files Phase 4 will generate", "",
            "| File | Est. pages |", "|---|---|"]
    pages = 0
    for row in chosen:
        essentials = min(30, max(15, 12 + row["questions"] // 12))
        practice = min(40, max(8, row["questions"] // 2))
        solutions = practice
        mock = 6
        pages += essentials + practice + solutions + mock * 2
        out += [f"| PASS-ESSENTIALS_{row['code']}.pdf | {essentials} |",
                f"| PRACTICE_{row['code']}.pdf | {practice} |",
                f"| SOLUTIONS_{row['code']}.pdf | {solutions} |",
                f"| MOCK-EXAM_{row['code']}.pdf + _SOLUTIONS.pdf | {mock*2} |"]
    out += [f"| STUDY-PLAN.pdf | {max(4, len(days)//8)} |", "",
            f"**{pages + max(4, len(days)//8)} pages total to print.**", "",
            "---", "", "**Stopping here for your approval before any of it is built.**"]
    (ANALYSIS / "PLAN.md").write_text("\n".join(out))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours-per-day", type=float, default=7.0)
    args = parser.parse_args()

    rows = json.loads((DATA / "scoring.json").read_text())
    esse3 = json.loads((DATA / "esse3.json").read_text())
    today = dt.date.today()
    horizon = max((parse_date(r["sitting"]["exam_date"]) for r in rows if r.get("sitting")),
                  default=today)
    span = (horizon - today).days
    budget = span * args.hours_per_day * (1 - LOST_DAY_PER_WEEK / 7)

    # The realistic rate: one lost day a week is already absorbed into it, so
    # feasibility is tested against what a normal week actually yields.
    effective_rate = args.hours_per_day * (1 - LOST_DAY_PER_WEEK / 7)
    chosen, dropped = choose(rows, budget, today, effective_rate)
    days = build_calendar(chosen, today + dt.timedelta(days=1), args.hours_per_day)
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    write_plan(chosen, dropped, days, args.hours_per_day, budget, esse3)

    print(f"budget {budget:.0f}h over {span} days at {args.hours_per_day:g}h/day")
    print(f"chosen: {len(chosen)} exams, {sum(r['cfu'] for r in chosen)} CFU, "
          f"{sum(r['hours_low'] for r in chosen)}h, expected yield "
          f"{sum(r['cfu']*r['p_pass'] for r in chosen):.0f} CFU")
    for row in chosen:
        print(f"  {row['sitting']['exam_date']} {row['name'][:36]:<38} "
              f"{row['cfu']:>2} CFU {row['hours_low']:>3}h  book by "
              f"{row['sitting']['booking_closes']}")
    print(f"deferred: {len(dropped)} exams, {sum(r['cfu'] for r in dropped)} CFU")
    print(f"wrote {ANALYSIS/'PLAN.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
