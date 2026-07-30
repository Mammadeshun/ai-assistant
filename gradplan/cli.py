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
from datetime import date

from . import career as career_mod
from . import config, report
from .archive import RawArchive
from .models import NOT_TAKEN, PASSED, Career, Exam
from .planner import PlannerOptions, assess, earliest_feasible
from .sources import bai, esse3, kiro
from .sources.browser import AUTH_ENV, AUTH_INTERACTIVE, AUTH_STORAGE, session


def _add_auth(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--auth",
        choices=[AUTH_INTERACTIVE, AUTH_STORAGE, AUTH_ENV],
        default=AUTH_STORAGE,
        help=(
            "interactive: sign in by hand in a visible browser (handles 2FA); "
            "storage: reuse the saved session; "
            "env: fill the form from UNIPV_USERNAME / UNIPV_PASSWORD"
        ),
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=config.REQUEST_DELAY_SECONDS,
        help="seconds to wait between requests (default: %(default)s)",
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


def cmd_fetch_esse3(args: argparse.Namespace) -> int:
    config.ensure_dirs()
    archive = RawArchive()
    with session(archive, auth_mode=args.auth, headless=False, delay=args.delay) as handle:
        result = esse3.fetch_all(handle)
    print(f"  archived: {', '.join(result['fetched']) or 'nothing'}")
    for failure in result["failed"]:
        print(f"  failed:   {failure}")
    return 0 if result["fetched"] else 1


def cmd_fetch_kiro(args: argparse.Namespace) -> int:
    config.ensure_dirs()
    archive = RawArchive()
    with session(archive, auth_mode=args.auth, headless=False, delay=args.delay) as handle:
        result = kiro.fetch_all(handle)
    print(f"  archived: {', '.join(result['fetched']) or 'nothing'}")
    for failure in result["failed"]:
        print(f"  failed:   {failure}")
    return 0 if result["fetched"] else 1


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
    )
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

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
