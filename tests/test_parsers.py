"""Parser tests. Everything runs offline against fixtures."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from gradplan.models import ENROLLED, NOT_TAKEN, PASSED, normalise_course_name, parse_mark
from gradplan.parsers import bai, esse3

FIXTURES = Path(__file__).parent / "fixtures"


# --- marks and names ---------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("28", (28, False, False)),
        ("30 e lode", (30, True, False)),
        ("30L", (30, True, False)),
        ("IDONEO", (None, False, True)),
        ("-", (None, False, False)),
        (None, (None, False, False)),
    ],
)
def test_parse_mark(raw, expected):
    assert parse_mark(raw) == expected


def test_normalise_folds_spelling_and_module_variants():
    assert normalise_course_name("Statistical modelling") == normalise_course_name(
        "Statistical modeling"
    )
    assert normalise_course_name("Calculus (part 1)") == normalise_course_name(
        "CALCULUS - mod. 2"
    )
    assert normalise_course_name(
        "Logic for Practical Reasoning and Artificial Intelligence"
    ) == normalise_course_name("Logics for practical reasoning and AI")


# --- BAI graduation calendar -------------------------------------------------
CALENDAR_TEXT = """
Graduation  Calendar  a.y.  2025/26
Graduation  Day  Location  Deadline  for  the  application
Deadline  for  the  submission  of  the  report  and  the  registration  of  all  exams
24  Jul  2026  Univ.  of  Pavia  24  Jun  2026  17  Jul  2026
23  Sep  2026  Univ.  of  Milano-Bicocca  23  Aug  2026  16  Sep  2026
16  Dec  2026  Univ.  of  Milano  Statale  16  Nov  2026  9  Dec  2026
"""


def test_parse_graduation_calendar():
    sessions = bai.parse_graduation_calendar(CALENDAR_TEXT, academic_year="2025/26")
    assert [s.date for s in sessions] == [
        date(2026, 7, 24),
        date(2026, 9, 23),
        date(2026, 12, 16),
    ]
    first = sessions[0]
    assert first.location == "Pavia"
    assert first.application_deadline == date(2026, 6, 24)
    assert first.records_deadline == date(2026, 7, 17)
    assert sessions[1].location == "Milano-Bicocca"
    assert sessions[2].location == "Milano Statale"


def test_graduation_rows_require_ordered_deadlines():
    """A row whose dates are out of order is not a calendar row."""
    assert bai.parse_graduation_calendar("1 Jan 2026 x 2 Feb 2026 3 Mar 2026") == []


# --- BAI session windows -----------------------------------------------------
SESSIONS_PAGE = """
Some intro mentioning the academic year 2026/27 for teaching activities.
Exam Sessions
Academic Year 2025/26
Winter session - from 19 January to 27 February at Universita di Milano Statale
Summer session - from 15 June to 3 1 July at Universita di Pavia
Autumn session - from 31 August to 25 September at Universita di Milano Bicocca
Graduation
Final examination regulations and calendar A.Y. 2024/25
"""


def test_session_windows_use_their_own_section_year():
    windows = bai.parse_session_windows(SESSIONS_PAGE)
    assert {w.name for w in windows} == {"winter", "summer", "autumn"}
    by_name = {w.name: w for w in windows}
    # 2025/26 runs Oct 2025 -> Sep 2026, so all three fall in 2026 ...
    assert by_name["winter"].start == date(2026, 1, 19)
    # ... and the '3 1 July' rendering glitch must still yield the 31st.
    assert by_name["summer"].end == date(2026, 7, 31)
    assert by_name["autumn"].start == date(2026, 8, 31)
    assert by_name["autumn"].host == "Milano-Bicocca"


# --- BAI exam sittings -------------------------------------------------------
SITTINGS_TEXT = """Course Date Time Room Location Teachers(s)
Algorithms and Data Structures 3-Sep14:00 B1/B2 Pavia Dondi
Computational Logic 31-Aug 9:30 LAB907 Bicocca Ghilardi
LABORATORY OF COGNITIVE AND BEHAVIOURAL MEASURES10-Sep 9:30 U6-30 Bicocca Amenta
Computer Programming 9-Sep 9:30Gamma, LambdaStatale Ferrari
Statistical modeling 10-Sep 9:30 U6-23 Bicocca D'Angelo
"""


def _autumn_window():
    return bai.parse_session_windows(SESSIONS_PAGE)


def test_sittings_survive_glued_columns():
    sittings = bai.parse_exam_sittings(SITTINGS_TEXT, "autumn", _autumn_window())
    assert len(sittings) == 5, [s.course for s in sittings]
    by_course = {s.course: s for s in sittings}

    # Date glued to the time.
    assert by_course["Algorithms and Data Structures"].date == date(2026, 9, 3)
    assert by_course["Algorithms and Data Structures"].time == "14:00"
    # Course name glued to the date.
    lab = by_course["LABORATORY OF COGNITIVE AND BEHAVIOURAL MEASURES"]
    assert lab.date == date(2026, 9, 10)
    # Room glued to the location.
    assert by_course["Computer Programming"].location == "Milano Statale"
    # A month at the other end of the session window still resolves its year.
    assert by_course["Computational Logic"].date == date(2026, 8, 31)


def test_home_university_inferred_from_deviation_from_host():
    sittings = bai.parse_exam_sittings(SITTINGS_TEXT, "autumn", _autumn_window())
    homes = bai.infer_home_universities(sittings, _autumn_window())
    # Autumn is hosted at Bicocca, so these two are examined away from the host.
    assert homes[normalise_course_name("Algorithms and Data Structures")] == (
        "Pavia",
        "inferred",
    )
    assert homes[normalise_course_name("Computer Programming")] == (
        "Milano Statale",
        "inferred",
    )


# --- Esse3 -------------------------------------------------------------------
def test_parse_libretto_statuses_marks_and_cfu():
    markup = (FIXTURES / "esse3_libretto.html").read_text(encoding="utf-8")
    exams, diagnostics = esse3.parse_libretto(markup)
    assert diagnostics == []
    by_name = {e.name: e for e in exams}

    calculus = by_name["Calculus"]
    assert calculus.status == PASSED
    assert (calculus.mark, calculus.lode, calculus.cfu) == (30, True, 12.0)
    assert calculus.date == date(2025, 6, 20)
    assert calculus.code == "509481"
    assert calculus.counts_for_average

    lab = by_name["LABORATORY OF COMPUTATIONAL INTELLIGENCE"]
    assert lab.status == PASSED
    assert lab.pass_fail and lab.mark is None
    # Pass/fail activities earn credits but must not move the average.
    assert lab.earned_cfu == 3.0
    assert not lab.counts_for_average

    assert by_name["Statistical modelling"].status == NOT_TAKEN
    assert by_name["Final exam"].cfu == 3.0


def test_enrolments_upgrade_status_on_merge():
    libretto, _ = esse3.parse_libretto(
        (FIXTURES / "esse3_libretto.html").read_text(encoding="utf-8")
    )
    booked = esse3.parse_exam_enrollments(
        (FIXTURES / "esse3_prenotazioni.html").read_text(encoding="utf-8")
    )
    merged = {e.name: e for e in esse3.merge_exams(libretto, booked)}
    assert merged["Statistical modelling"].status == ENROLLED
    # Merging must not demote anything already passed.
    assert merged["Calculus"].status == PASSED
    assert merged["Statistical modelling"].cfu == 6.0


def test_libretto_reports_when_nothing_parses():
    _, diagnostics = esse3.parse_libretto("<html><body>Sessione scaduta</body></html>")
    assert any("no activity rows" in note for note in diagnostics)
