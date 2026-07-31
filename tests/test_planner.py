"""Planner tests: deadline arithmetic, feasibility and the mark projection."""

from __future__ import annotations

from datetime import date

import pytest

from gradplan.models import (
    ENROLLED,
    NOT_TAKEN,
    PASSED,
    Career,
    Exam,
    ExamSitting,
    GraduationSession,
)
from gradplan.planner import (
    PlannerOptions,
    assess,
    earliest_feasible,
    extrapolate_sessions,
    observed_pace,
    outstanding_requirements,
    project_mark,
)

TODAY = date(2026, 7, 30)

SEPTEMBER = GraduationSession(
    date=date(2026, 9, 23),
    location="Milano-Bicocca",
    application_deadline=date(2026, 8, 23),
    records_deadline=date(2026, 9, 16),
)
OCTOBER = GraduationSession(
    date=date(2026, 10, 28),
    location="Milano-Bicocca",
    application_deadline=date(2026, 9, 28),
    records_deadline=date(2026, 10, 21),
)
JULY_PAST = GraduationSession(
    date=date(2026, 7, 24),
    location="Pavia",
    application_deadline=date(2026, 6, 24),
    records_deadline=date(2026, 7, 17),
)
SESSIONS = [JULY_PAST, SEPTEMBER, OCTOBER]


def sittings():
    return [
        ExamSitting("Statistical modeling", date(2026, 9, 10), "autumn", "Milano-Bicocca"),
        ExamSitting("Statistical modeling", date(2026, 9, 24), "autumn", "Milano-Bicocca"),
        ExamSitting("Brain modeling", date(2026, 9, 3), "autumn", "Milano-Bicocca"),
    ]


def career_with(remaining_names):
    """A career whose credits add up to exactly 180, so only timing can block."""
    outstanding = 6.0 * len(remaining_names) + 3.0  # exams + final exam
    passed_cfu = 180.0 - outstanding
    exams = [
        Exam(name="passed block A", cfu=60.0, status=PASSED, mark_raw="28"),
        Exam(name="passed block B", cfu=passed_cfu - 60.0, status=PASSED, mark_raw="25"),
    ]
    for name in remaining_names:
        exams.append(Exam(name=name, cfu=6.0, status=NOT_TAKEN))
    exams.append(Exam(name="Final exam", cfu=3.0, status=NOT_TAKEN, code="509535"))
    return Career(exams=exams)


def test_past_and_closed_sessions_are_blocked():
    career = career_with(["Brain modelling"])
    results = {a.session.date: a for a in assess(career, SESSIONS, sittings(), TODAY)}
    assert not results[date(2026, 7, 24)].feasible
    assert "was held" in results[date(2026, 7, 24)].blockers[0]


def test_recording_lag_decides_between_two_sessions():
    """A sitting on 10 Sep is in time for 16 Sep only if recording is instant."""
    career = career_with(["Statistical modelling"])

    instant = assess(
        career, SESSIONS, sittings(), TODAY, PlannerOptions(recording_lag_days=0)
    )
    assert earliest_feasible(instant).session.date == date(2026, 9, 23)

    lagged = assess(
        career, SESSIONS, sittings(), TODAY, PlannerOptions(recording_lag_days=7)
    )
    assert earliest_feasible(lagged).session.date == date(2026, 10, 28)


def test_exam_with_no_published_sitting_blocks_sessions_within_the_calendar():
    career = career_with(["Some Course Not In The Calendar"])
    results = assess(career, SESSIONS, sittings(), TODAY)

    september = next(a for a in results if a.session.date == date(2026, 9, 23))
    assert september.sittings_known
    assert not september.feasible
    plan = september.exam_plans[0]
    assert not plan.feasible and "no sitting" in plan.reason


def test_sessions_past_the_calendar_horizon_fall_back_to_the_forecast():
    """Beyond the published sittings, a missing sitting proves nothing."""
    career = career_with(["Some Course Not In The Calendar"])
    results = assess(career, SESSIONS, sittings(), TODAY)

    # The fixture's last sitting is 24 Sep 2026, so October is past the horizon.
    october = next(a for a in results if a.session.date == date(2026, 10, 28))
    assert not october.sittings_known
    assert october.exam_plans == []
    assert october.feasible


def test_outstanding_credits_push_the_answer_past_the_calendar():
    """A large backlog is bounded by pace, not by deadline arithmetic."""
    career = Career(
        exams=[Exam(name="passed", cfu=12.0, status=PASSED, mark_raw="25")]
        + [Exam(name=f"todo {i}", cfu=12.0, status=NOT_TAKEN) for i in range(14)]
    )
    options = PlannerOptions(pace_cfu_per_year=60.0)
    results = assess(career, SESSIONS, sittings(), TODAY, options)
    assert earliest_feasible(results) is None  # 168 CFU cannot fit by Oct 2026
    assert any("CFU still to earn" in b for a in results for b in a.blockers)


def test_extrapolated_sessions_repeat_the_pattern_and_are_flagged():
    extended = extrapolate_sessions(SESSIONS, until=date(2029, 12, 31))
    future = [s for s in extended if s.projected]
    assert future, "expected the calendar to be extended"
    assert all(s.date > SESSIONS[-1].date for s in future)
    # The published July/September/October pattern should recur.
    assert any(s.date == date(2027, 9, 23) for s in future)
    sample = next(s for s in future if s.date == date(2027, 9, 23))
    # Deadlines follow the regulation leads: one month and one week.
    assert sample.application_deadline == date(2027, 8, 24)
    assert sample.records_deadline == date(2027, 9, 16)


def test_observed_pace_is_reported_from_the_first_recorded_exam():
    career = Career(
        exams=[
            Exam(name="a", cfu=6.0, status=PASSED, mark_raw="23", date=date(2025, 9, 9)),
            Exam(name="b", cfu=6.0, status=PASSED, mark_raw="27", date=date(2025, 9, 17)),
        ]
    )
    pace = observed_pace(career, date(2026, 9, 9))
    assert pace["available"] and pace["since"] == "2025-09-09"
    assert pace["cfu_per_year"] == pytest.approx(12.0, abs=0.2)


def test_chosen_sitting_is_the_earliest_usable_one():
    career = career_with(["Statistical modelling"])
    results = assess(
        career, SESSIONS, sittings(), TODAY, PlannerOptions(recording_lag_days=0)
    )
    september = next(a for a in results if a.session.date == date(2026, 9, 23))
    assert september.exam_plans[0].sitting.date == date(2026, 9, 10)


def test_thesis_lead_time_can_block_an_otherwise_reachable_session():
    career = career_with([])
    options = PlannerOptions(recording_lag_days=0, thesis_days_needed=120)
    results = assess(career, SESSIONS, sittings(), TODAY, options)
    september = next(a for a in results if a.session.date == date(2026, 9, 23))
    assert not september.feasible
    assert any("report" in b for b in september.blockers)


def test_short_study_plan_is_flagged():
    career = Career(exams=[Exam(name="only thing", cfu=12.0, status=PASSED, mark_raw="30")])
    results = assess(career, SESSIONS, sittings(), TODAY)
    assert any("180 required" in b for a in results for b in a.blockers)


def test_outstanding_requirements_add_thesis_when_absent():
    career = Career(exams=[Exam(name="Calculus", cfu=12.0, status=PASSED, mark_raw="30")])
    kinds = [r.kind for r in outstanding_requirements(career)]
    assert kinds == ["thesis"]


def test_booked_exams_are_still_outstanding_but_labelled():
    career = Career(
        exams=[Exam(name="Statistical modelling", cfu=6.0, status=ENROLLED)]
    )
    requirement = next(
        r for r in outstanding_requirements(career) if r.name == "Statistical modelling"
    )
    assert requirement.note == "already booked"


# --- mark projection ---------------------------------------------------------
def test_base_score_follows_the_regulation_formula():
    career = Career(
        exams=[
            Exam(name="a", cfu=12.0, status=PASSED, mark_raw="30"),
            Exam(name="b", cfu=6.0, status=PASSED, mark_raw="24"),
        ]
    )
    # weighted average = (30*12 + 24*6) / 18 = 28 ; 28 * 11/3 = 102.67 -> 103
    assert career.weighted_average() == pytest.approx(28.0)
    assert career.base_graduation_score() == 103


def test_pass_fail_activities_are_excluded_from_the_average():
    career = Career(
        exams=[
            Exam(name="graded", cfu=6.0, status=PASSED, mark_raw="30"),
            Exam(name="lab", cfu=3.0, status=PASSED, mark_raw="IDONEO"),
        ]
    )
    assert career.weighted_average() == pytest.approx(30.0)
    assert career.cfu_earned == 9.0


def test_projection_caps_at_110_and_reports_in_corso_bonus():
    career = Career(exams=[Exam(name="a", cfu=12.0, status=PASSED, mark_raw="30")])
    projection = project_mark(career, [], PlannerOptions(in_corso=True))
    assert projection["base_score"] == 110
    assert projection["in_corso_bonus"] == 2
    assert projection["final_range"] == [110, 110]
    assert projection["cum_laude_possible"] is True


def test_projection_without_graded_exams_is_unavailable():
    career = Career(exams=[Exam(name="lab", cfu=3.0, status=PASSED, mark_raw="IDONEO")])
    assert project_mark(career, [], PlannerOptions())["available"] is False
