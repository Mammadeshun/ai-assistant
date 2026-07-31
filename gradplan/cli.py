"""Command line entry point.

    python -m gradplan fetch-public          # rules + calendars (no login)
    python -m gradplan fetch-esse3 --auth interactive
    python -m gradplan fetch-kiro  --auth storage
    python -m gradplan build-career          # archive -> data/career.json
    python -m gradplan plan                  # the answer
    python -m gradplan plan --remaining "Statistical modelling,Brain modelling"

Every fetch archives raw responses under ``data/raw/``; every parse reads from
there, so parsing can be re-run offline as often as needed.
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from datetime import date, timedelta

from . import career as career_mod
from . import config, report
from .archive import RawArchive
from .models import NOT_TAKEN, PASSED, Career, Exam
from .planner import (
    PlannerOptions,
    assess,
    completion_forecast,
    earliest_feasible,
    extrapolate_sessions,
    outstanding_requirements,
)
from .sources import bai, esse3, kiro
from .sources.browser import AUTH_AUTO, AUTH_ENV, AUTH_INTERACTIVE, AUTH_STORAGE, session
from .sources.http_session import http_session


def _add_auth(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--auth",
        choices=[AUTH_AUTO, AUTH_INTERACTIVE, AUTH_STORAGE, AUTH_ENV],
        default=AUTH_AUTO,
        help=(
            "auto (default): reuse the saved session, else use "
            "UNIPV_USERNAME / UNIPV_PASSWORD if set, else open a browser for "
            "you to sign in; interactive: always sign in by hand (handles 2FA); "
            "storage: only reuse the saved session; "
            "env: only use the environment variables"
        ),
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=config.REQUEST_DELAY_SECONDS,
        help="seconds to wait between requests (default: %(default)s)",
    )
    parser.add_argument(
        "--transport",
        choices=["browser", "http"],
        default="browser",
        help=(
            "browser (default): drive Chromium via Playwright; "
            "http: follow the SSO form chain with a plain cookie jar, for "
            "environments where a headless browser has no network egress. "
            "http requires UNIPV_USERNAME / UNIPV_PASSWORD"
        ),
    )


def _add_planner_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--today", help="override today's date (YYYY-MM-DD)")
    parser.add_argument(
        "--recording-lag-days",
        type=int,
        default=7,
        help=(
            "days assumed between sitting an exam and it being recorded in "
            "Esse3; the regulations require exams to be recorded, not merely "
            "sat, by the deadline (default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--thesis-days-needed",
        type=int,
        default=0,
        help="days still needed to finish the final report (default: %(default)s)",
    )
    parser.add_argument(
        "--assumed-mark",
        type=int,
        default=26,
        help="mark assumed for exams not yet passed, for the projection (default: %(default)s)",
    )
    parser.add_argument(
        "--in-corso",
        action="store_true",
        help="graduating within the third year from enrolment (+2 points)",
    )
    parser.add_argument(
        "--pace",
        type=float,
        default=60.0,
        help=(
            "CFU you expect to earn per academic year; 60 is the nominal "
            "full-time load for this degree (default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--remaining",
        help=(
            "comma-separated names of exams still to pass; use this to get an "
            "answer without scraping Esse3"
        ),
    )
    parser.add_argument("--json", dest="json_out", help="also write the assessment to this path")


def _hypothetical_career(names: str) -> Career:
    """Build a stand-in career from a list of outstanding exam names.

    CFU are taken from the reference study plan where the name matches.
    """
    plan_path = config.REFERENCE_DIR / "study_plan_2025_26.json"
    cfu_by_name: dict[str, float] = {}
    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        for activities in plan.get("years", {}).values():
            for activity in activities:
                cfu_by_name[activity["name"].lower()] = float(activity["cfu"])
        for track in plan.get("tracks", {}).values():
            for course in track.get("courses", []):
                cfu_by_name[course["name"].lower()] = float(course["cfu"])
        for lab in plan.get("laboratories", []):
            cfu_by_name[lab["name"].lower()] = float(lab["cfu"])

    exams: list[Exam] = []
    outstanding_cfu = 0.0
    for raw in [n.strip() for n in names.split(",") if n.strip()]:
        cfu = cfu_by_name.get(raw.lower(), 6.0)
        outstanding_cfu += cfu
        exams.append(Exam(name=raw, cfu=cfu, status=NOT_TAKEN, source="hypothetical"))

    # One synthetic passed block standing in for everything already done, so the
    # CFU total reaches 180. It carries no mark, so it never skews the average.
    already = config.TOTAL_CFU_REQUIRED - outstanding_cfu - config.FINAL_EXAM_CFU
    if already > 0:
        exams.insert(
            0,
            Exam(
                name="(exams already passed)",
                cfu=already,
                status=PASSED,
                pass_fail=True,
                source="hypothetical",
            ),
        )
    return Career(exams=exams, student={"mode": "hypothetical"})


def cmd_fetch_public(args: argparse.Namespace) -> int:
    config.ensure_dirs()
    result = bai.fetch_all(RawArchive(), delay=args.delay)
    print(f"  archived: {', '.join(result['fetched']) or 'nothing'}")
    for miss in result["missing"]:
        print(f"  missing:  {miss}")
    return 0


@contextmanager
def _transport(args: argparse.Namespace, archive: RawArchive):
    """Yield either a Playwright session or the HTTP one, per --transport."""
    if args.transport == "http":
        handle = http_session(archive, delay=args.delay)
        try:
            yield handle
        finally:
            handle.close()
    else:
        with session(
            archive, auth_mode=args.auth, headless=False, delay=args.delay
        ) as handle:
            yield handle


def _run_fetch(args: argparse.Namespace, module) -> int:
    config.ensure_dirs()
    archive = RawArchive()
    with _transport(args, archive) as handle:
        result = module.fetch_all(handle)
    print(f"  archived: {', '.join(result['fetched']) or 'nothing'}")
    for failure in result["failed"]:
        print(f"  failed:   {failure}")
    return 0 if result["fetched"] else 1


def cmd_fetch_esse3(args: argparse.Namespace) -> int:
    return _run_fetch(args, esse3)


def cmd_fetch_kiro(args: argparse.Namespace) -> int:
    return _run_fetch(args, kiro)


def cmd_build_career(args: argparse.Namespace) -> int:
    archive = RawArchive()
    built, diagnostics = career_mod.build(archive, write=False)
    if not built.exams:
        # Writing an empty career.json would let `plan` run on nothing and
        # report a confidently wrong answer.
        print("  no activities parsed - career.json left untouched", file=sys.stderr)
        for note in diagnostics:
            print(f"  note: {note}", file=sys.stderr)
        return 1

    career_mod.build(archive, write=True)
    print(f"  wrote {config.CAREER_JSON} ({len(built.exams)} activities)")
    for note in diagnostics:
        print(f"  note: {note}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    today = date.fromisoformat(args.today) if args.today else date.today()
    archive = RawArchive()

    if args.remaining:
        student_career = _hypothetical_career(args.remaining)
    elif config.CAREER_JSON.exists():
        student_career = career_mod.load()
    else:
        print(
            "  No data/career.json yet. Either run fetch-esse3 + build-career, "
            "or pass --remaining to explore a scenario.",
            file=sys.stderr,
        )
        return 2

    sessions = bai.load_graduation_sessions(archive)
    if not sessions:
        print("  No graduation calendar archived. Run fetch-public first.", file=sys.stderr)
        return 2
    sittings = bai.load_exam_sittings(archive)

    options = PlannerOptions(
        recording_lag_days=args.recording_lag_days,
        thesis_days_needed=args.thesis_days_needed,
        assumed_mark=args.assumed_mark,
        in_corso=args.in_corso,
        pace_cfu_per_year=args.pace,
    )

    # If the credits left cannot be earned before the calendar runs out, extend
    # it by repeating the published pattern so the answer is still a date.
    forecast = completion_forecast(
        student_career, outstanding_requirements(student_career), today, options
    )
    horizon = date.fromisoformat(forecast["earliest_completion"])
    sessions = extrapolate_sessions(sessions, until=horizon + timedelta(days=400))
    assessments = assess(student_career, sessions, sittings, today=today, options=options)
    print(report.render(student_career, assessments, today, sittings))

    winner = earliest_feasible(assessments)
    payload = {
        "generated_at": today.isoformat(),
        "options": options.__dict__,
        "earliest_feasible": winner.to_json() if winner else None,
        "sessions": [a.to_json() for a in assessments],
    }
    config.ensure_dirs()
    out_path = args.json_out or config.PLAN_JSON
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    print(f"\n  written: {out_path}")
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    from . import schedule as sched

    today = date.fromisoformat(args.today) if args.today else date.today()
    if not config.CAREER_JSON.exists():
        print("  No data/career.json. Run fetch-esse3 + build-career first.", file=sys.stderr)
        return 2
    student_career = career_mod.load()

    assume = [n.strip() for n in (args.assume_passed or "").split(",") if n.strip()]
    activities, unprofiled = sched.profile_outstanding(
        student_career, assume_passed=assume
    )
    sessions, coursework = sched.build_schedule(
        activities, today, session_budget=args.session_budget
    )
    summary = sched.summarise(sessions, coursework, unprofiled)

    completion = summary["completion"]
    print(report.BAR)
    print("FASTEST ROUTE THROUGH THE REMAINING EXAMS")
    print(report.BAR)
    if assume:
        print(f"  Assuming already passed: {', '.join(assume)}")
    print(
        f"  {len(activities)} activities left"
        f"  ({sum(a.cfu for a in activities):g} CFU),"
        f" effort budget {args.session_budget} points per session"
    )
    print()
    for session in sessions:
        print(
            f"  {session.name.upper():7s} {session.start:%b %Y}"
            f"   {session.points} pts, {session.cfu:g} CFU"
        )
        for activity in session.activities:
            flag = "papers" if activity.past_papers else "no papers"
            print(
                f"      e{activity.points} {activity.cfu:>2g} CFU  "
                f"{activity.name[:44]:44s} {activity.mode[:34]:34s} {flag}"
            )
    if coursework:
        print()
        print("  In parallel (no exam slot - coursework or project):")
        for activity in coursework:
            print(
                f"      e{activity.points} {activity.cfu:>2g} CFU  "
                f"{activity.name[:44]:44s} {activity.mode[:40]}"
            )
    if unprofiled:
        print()
        print(f"  No assessment profile ({len(unprofiled)}), assumed medium written:")
        for name in unprofiled:
            print(f"      - {name}")

    print()
    print(f"  Last exam session ends   {completion}")

    sessions_gr = bai.load_graduation_sessions(archive := RawArchive())
    sittings = bai.load_exam_sittings(archive)
    if sessions_gr and completion:
        done = date.fromisoformat(completion)
        extended = extrapolate_sessions(sessions_gr, until=done + timedelta(days=400))
        reachable = [s for s in extended if s.records_deadline >= done and s.application_deadline >= today]
        if reachable:
            target = min(reachable, key=lambda s: s.date)
            tag = " (projected)" if target.projected else ""
            print(f"  Earliest graduation      {target.date:%d %b %Y}{tag}")
            print(f"      apply by             {target.application_deadline:%d %b %Y}")
            print(f"      all exams recorded   {target.records_deadline:%d %b %Y}")
            summary["earliest_graduation"] = target.to_json()

    out = args.json_out or (config.DATA_DIR / "schedule.json")
    config.ensure_dirs()
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
    print(f"\n  written: {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gradplan",
        description="Earliest possible graduation session for the interateneo BSc in AI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    public = subparsers.add_parser("fetch-public", help="download rules and calendars (no login)")
    public.add_argument("--delay", type=float, default=config.REQUEST_DELAY_SECONDS)
    public.set_defaults(func=cmd_fetch_public)

    esse3_parser = subparsers.add_parser("fetch-esse3", help="scrape Esse3 career and libretto")
    _add_auth(esse3_parser)
    esse3_parser.set_defaults(func=cmd_fetch_esse3)

    kiro_parser = subparsers.add_parser("fetch-kiro", help="scrape Kiro (Moodle) enrolments")
    _add_auth(kiro_parser)
    kiro_parser.set_defaults(func=cmd_fetch_kiro)

    build = subparsers.add_parser("build-career", help="parse the archive into data/career.json")
    build.set_defaults(func=cmd_build_career)

    plan = subparsers.add_parser("plan", help="compute the earliest graduation session")
    _add_planner_options(plan)
    plan.set_defaults(func=cmd_plan)

    sched_p = subparsers.add_parser(
        "schedule", help="pack the remaining exams into sessions"
    )
    sched_p.add_argument("--today", help="override today's date (YYYY-MM-DD)")
    sched_p.add_argument(
        "--session-budget",
        type=int,
        default=8,
        help=(
            "effort points per exam session; low exam = 1, medium = 2, high = 3 "
            "(default: %(default)s)"
        ),
    )
    sched_p.add_argument(
        "--assume-passed",
        help="comma-separated exams to treat as already passed",
    )
    sched_p.add_argument("--json", dest="json_out", help="write the schedule here")
    sched_p.set_defaults(func=cmd_schedule)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
