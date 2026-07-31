"""Answer the question: what is the earliest session in which I can graduate?

A graduation session is reachable only if all four of these hold:

1. its application deadline is still in the future (one month before the day);
2. every outstanding exam has a published sitting early enough to be *recorded*
   by the records deadline (one week before the day);
3. the report can be finished and uploaded by that same deadline;
4. the remaining credits actually add up to 180.

Rules and dates come from the *Final examination regulations* published on
bai.unipv.it, not from assumptions baked into this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable

from .models import (
    ENROLLED,
    PASSED,
    Career,
    Exam,
    ExamSitting,
    GraduationSession,
    Requirement,
    index_by_course,
    match_course_key,
)


@dataclass
class PlannerOptions:
    """Assumptions the answer depends on, all explicit and overridable."""

    # Days between sitting an exam and the mark appearing as recorded in Esse3.
    # The regulations require exams to be *recorded* by the deadline, not merely
    # sat, and verbalizzazione is rarely instant.
    recording_lag_days: int = 7
    # Minimum notice needed before sitting an exam you have not prepared.
    exam_prep_days: int = 0
    # Minimum time needed to produce the final report, counted to the upload
    # deadline. Zero means the report is already effectively done.
    thesis_days_needed: int = 0
    # Mark assumed for exams not yet passed, when projecting the final mark.
    assumed_mark: int = 26
    # Credits the student expects to earn per academic year. 60 is the nominal
    # full-time load for this degree; the planner also reports the pace
    # actually observed so far.
    pace_cfu_per_year: float = 60.0
    # Set when the student is still within the third year from enrolment.
    in_corso: bool | None = None
    total_cfu_required: int = 180


@dataclass
class ExamPlan:
    """When an outstanding exam would have to be sat for a given session."""

    name: str
    cfu: float
    sitting: ExamSitting | None
    recorded_by: date | None
    feasible: bool
    reason: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cfu": self.cfu,
            "sitting_date": self.sitting.date.isoformat() if self.sitting else None,
            "sitting_session": self.sitting.session if self.sitting else None,
            "sitting_location": self.sitting.location if self.sitting else None,
            "recorded_by": self.recorded_by.isoformat() if self.recorded_by else None,
            "feasible": self.feasible,
            "reason": self.reason,
        }


@dataclass
class SessionAssessment:
    """Verdict for one graduation session."""

    session: GraduationSession
    feasible: bool
    blockers: list[str] = field(default_factory=list)
    exam_plans: list[ExamPlan] = field(default_factory=list)
    projected_mark: dict[str, Any] = field(default_factory=dict)
    forecast: dict[str, Any] = field(default_factory=dict)
    # False when the exam calendar does not reach this session yet.
    sittings_known: bool = True

    def to_json(self) -> dict[str, Any]:
        return {
            **self.session.to_json(),
            "feasible": self.feasible,
            "blockers": self.blockers,
            "exams_to_sit": [p.to_json() for p in self.exam_plans],
            "projected_mark": self.projected_mark,
            "sittings_known": self.sittings_known,
            "forecast": self.forecast,
        }


def outstanding_requirements(career: Career, thesis_cfu: float = 3.0) -> list[Requirement]:
    """Everything in the student's plan that is not yet passed."""
    requirements: list[Requirement] = []
    for exam in career.exams:
        if exam.status == PASSED:
            continue
        kind = "thesis" if _is_thesis(exam) else "exam"
        note = "already booked" if exam.status == ENROLLED else ""
        requirements.append(
            Requirement(name=exam.name, cfu=exam.cfu, kind=kind, code=exam.code, note=note)
        )

    if not any(r.kind == "thesis" for r in requirements):
        if not any(_is_thesis(e) and e.status == PASSED for e in career.exams):
            requirements.append(
                Requirement(name="Final exam (report)", cfu=thesis_cfu, kind="thesis", code="509535")
            )
    return requirements


def _is_thesis(exam: Exam) -> bool:
    if exam.code == "509535":
        return True
    name = exam.name.lower()
    return "final exam" in name or "prova finale" in name


def plan_exam(
    requirement: Requirement,
    session: GraduationSession,
    sittings_by_course: dict[str, list[ExamSitting]],
    today: date,
    options: PlannerOptions,
) -> ExamPlan:
    """Find the sitting that gets this exam recorded in time, if one exists."""
    deadline = session.records_deadline - timedelta(days=options.recording_lag_days)
    earliest = today + timedelta(days=options.exam_prep_days)

    key = match_course_key(requirement.name, sittings_by_course.keys())
    candidates = sittings_by_course.get(key, []) if key else []
    usable = [s for s in candidates if earliest <= s.date <= deadline]

    if usable:
        chosen = min(usable, key=lambda s: s.date)
        return ExamPlan(
            name=requirement.name,
            cfu=requirement.cfu,
            sitting=chosen,
            recorded_by=chosen.date + timedelta(days=options.recording_lag_days),
            feasible=True,
        )

    if not candidates:
        return ExamPlan(
            name=requirement.name,
            cfu=requirement.cfu,
            sitting=None,
            recorded_by=None,
            feasible=False,
            reason="no sitting for this course in the published exam calendars",
        )

    future = [s for s in candidates if s.date >= earliest]
    if not future:
        return ExamPlan(
            name=requirement.name,
            cfu=requirement.cfu,
            sitting=None,
            recorded_by=None,
            feasible=False,
            reason="every published sitting for this course is already in the past",
        )
    nxt = min(future, key=lambda s: s.date)
    return ExamPlan(
        name=requirement.name,
        cfu=requirement.cfu,
        sitting=nxt,
        recorded_by=nxt.date + timedelta(days=options.recording_lag_days),
        feasible=False,
        reason=(
            f"next sitting is {nxt.date.isoformat()}, too late to be recorded by "
            f"{session.records_deadline.isoformat()}"
        ),
    )


def project_mark(
    career: Career,
    requirements: Iterable[Requirement],
    options: PlannerOptions,
) -> dict[str, Any]:
    """Project the degree mark under the regulations' formula.

    base = weighted average x 11/3, rounded; final = base + board increment
    (0-7) + 2 if the degree is taken in corso; cum laude from 112.
    """
    graded = [(e.mark, e.cfu) for e in career.exams if e.counts_for_average]
    for requirement in requirements:
        if requirement.kind == "exam" and requirement.cfu:
            graded.append((options.assumed_mark, requirement.cfu))

    total_cfu = sum(cfu for _, cfu in graded)
    if not total_cfu:
        return {"available": False, "reason": "no graded exams recorded yet"}

    average = sum(mark * cfu for mark, cfu in graded) / total_cfu
    base = round(average * 11 / 3)
    bonus = 2 if options.in_corso else 0
    low = min(base + bonus, 110)
    high = min(base + bonus + 7, 110)
    return {
        "available": True,
        "weighted_average": round(average, 3),
        "base_score": base,
        "in_corso_bonus": bonus,
        "final_range": [low, high],
        "cum_laude_possible": base + bonus + 7 >= 112,
        "assumed_mark_for_remaining": options.assumed_mark,
        "note": (
            "Board increment is 0-7 points and is not predictable; "
            "cum laude requires base + increment >= 112 and a unanimous board."
        ),
    }


def observed_pace(career: Career, today: date) -> dict[str, Any]:
    """CFU per year actually earned so far, from the first recorded exam."""
    dates = [e.date for e in career.exams if e.status == PASSED and e.date]
    if not dates:
        return {"available": False}
    first = min(dates)
    years = max((today - first).days / 365.25, 0.5)
    return {
        "available": True,
        "since": first.isoformat(),
        "years": round(years, 2),
        "cfu_per_year": round(career.cfu_earned / years, 1),
    }


def completion_forecast(
    career: Career,
    requirements: Iterable[Requirement],
    today: date,
    options: PlannerOptions,
) -> dict[str, Any]:
    """Earliest date the outstanding credits could realistically be earned.

    Deadline arithmetic alone would happily schedule twenty exams into one
    session. This bounds the answer by how fast credits can actually be
    accumulated.
    """
    outstanding_cfu = sum(r.cfu for r in requirements if r.kind != "thesis")
    if outstanding_cfu <= 0:
        return {"cfu_outstanding": 0.0, "earliest_completion": today.isoformat()}

    pace = max(options.pace_cfu_per_year, 1.0)
    days = (outstanding_cfu / pace) * 365.25
    earliest = today + timedelta(days=round(days))
    return {
        "cfu_outstanding": outstanding_cfu,
        "pace_cfu_per_year": pace,
        "years_needed": round(outstanding_cfu / pace, 2),
        "earliest_completion": earliest.isoformat(),
        "observed_pace": observed_pace(career, today),
    }


def extrapolate_sessions(
    sessions: Iterable[GraduationSession],
    until: date,
    application_lead_days: int = 30,
    records_lead_days: int = 7,
) -> list[GraduationSession]:
    """Extend the calendar past its last published session.

    The graduation calendar repeats annually, so future years are generated by
    shifting the published pattern. These are flagged ``projected`` — they are
    an expectation, not an announcement.
    """
    published = sorted(sessions, key=lambda s: s.date)
    if not published:
        return []
    out = list(published)
    last = published[-1].date
    if until <= last:
        return out

    year_offset = 1
    while True:
        added_any = False
        for base in published:
            try:
                candidate = base.date.replace(year=base.date.year + year_offset)
            except ValueError:  # 29 Feb
                candidate = base.date.replace(year=base.date.year + year_offset, day=28)
            if candidate <= last:
                continue
            out.append(
                GraduationSession(
                    date=candidate,
                    location=base.location,
                    application_deadline=candidate - timedelta(days=application_lead_days),
                    records_deadline=candidate - timedelta(days=records_lead_days),
                    academic_year="projected",
                    projected=True,
                )
            )
            added_any = True
            if candidate >= until:
                return sorted(out, key=lambda s: s.date)
        if not added_any:
            return sorted(out, key=lambda s: s.date)
        year_offset += 1
        if year_offset > 10:
            return sorted(out, key=lambda s: s.date)


def assess(
    career: Career,
    sessions: Iterable[GraduationSession],
    sittings: Iterable[ExamSitting],
    today: date | None = None,
    options: PlannerOptions | None = None,
) -> list[SessionAssessment]:
    """Evaluate every published graduation session, in date order."""
    today = today or date.today()
    options = options or PlannerOptions()
    sittings_by_course = index_by_course(sittings)
    requirements = outstanding_requirements(career)
    exam_reqs = [r for r in requirements if r.kind == "exam"]
    has_thesis_left = any(r.kind == "thesis" for r in requirements)

    cfu_earned = career.cfu_earned
    cfu_planned = cfu_earned + sum(r.cfu for r in requirements)

    forecast = completion_forecast(career, requirements, today, options)
    earliest_completion = date.fromisoformat(forecast["earliest_completion"])
    # Sittings are only published a couple of sessions ahead; past that
    # horizon their absence says nothing about feasibility.
    sitting_horizon = max((s.date for s in sittings), default=None)

    assessments: list[SessionAssessment] = []
    for session in sorted(sessions, key=lambda s: s.date):
        blockers: list[str] = []

        if session.date <= today:
            blockers.append(f"the session was held on {session.date.isoformat()}")
        elif session.application_deadline < today:
            blockers.append(
                f"application closed on {session.application_deadline.isoformat()}"
            )

        beyond_calendar = (
            sitting_horizon is None or session.records_deadline > sitting_horizon
        )
        if beyond_calendar:
            # Cannot verify individual exams; the credit forecast below is the
            # binding constraint instead.
            plans = []
        else:
            plans = [
                plan_exam(req, session, sittings_by_course, today, options)
                for req in exam_reqs
            ]
            blocked = [p for p in plans if not p.feasible]
            if blocked:
                blockers.append(
                    f"{len(blocked)} exam(s) cannot be recorded by "
                    f"{session.records_deadline.isoformat()}"
                )

        if exam_reqs and session.records_deadline < earliest_completion:
            blockers.append(
                f"{forecast['cfu_outstanding']:g} CFU still to earn; at "
                f"{forecast['pace_cfu_per_year']:g} CFU/year the earliest they "
                f"can all be recorded is {forecast['earliest_completion']}"
            )

        if has_thesis_left and options.thesis_days_needed:
            available = (session.records_deadline - today).days
            if available < options.thesis_days_needed:
                blockers.append(
                    f"only {available} days to finish the report, "
                    f"{options.thesis_days_needed} assumed necessary"
                )

        if cfu_planned < options.total_cfu_required:
            blockers.append(
                f"study plan accounts for {cfu_planned:g} CFU, "
                f"{options.total_cfu_required} required"
            )

        assessments.append(
            SessionAssessment(
                session=session,
                feasible=not blockers,
                blockers=blockers,
                exam_plans=plans,
                projected_mark=project_mark(career, exam_reqs, options),
                forecast=forecast,
                sittings_known=not beyond_calendar,
            )
        )
    return assessments


def earliest_feasible(assessments: Iterable[SessionAssessment]) -> SessionAssessment | None:
    for assessment in sorted(assessments, key=lambda a: a.session.date):
        if assessment.feasible:
            return assessment
    return None
