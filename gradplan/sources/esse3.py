"""Scrape Esse3 (studentionline.unipv.it).

Pages are visited one at a time with a delay, and each is archived before any
parsing happens.
"""

from __future__ import annotations

from typing import Any

from .. import config
from ..archive import RawArchive
from ..models import Career, Exam
from ..parsers import esse3 as parser
from .browser import Session

SOURCE = "esse3"

PAGES: list[tuple[str, str]] = [
    ("career", config.ESSE3_CAREER),
    ("libretto", config.ESSE3_LIBRETTO),
    ("study-plan", config.ESSE3_STUDY_PLAN),
    ("exam-enrollments", config.ESSE3_EXAM_ENROLLMENTS),
    ("available-exams", config.ESSE3_AVAILABLE_EXAMS),
]


def fetch_all(session: Session) -> dict[str, Any]:
    """Log in and archive every Esse3 page we parse."""
    session.login(config.ESSE3_LIBRETTO, success_marker="libretto")

    fetched: list[str] = []
    failed: list[str] = []
    for label, url in PAGES:
        try:
            session.goto(url, source=SOURCE, label=label)
            fetched.append(label)
        except Exception as exc:  # noqa: BLE001 - one bad page must not stop the run
            failed.append(f"{label}: {type(exc).__name__}: {exc}")
    return {"fetched": fetched, "failed": failed}


def load_career(archive: RawArchive | None = None) -> tuple[Career, list[str]]:
    """Build a Career from the archived Esse3 pages."""
    archive = archive or RawArchive()
    diagnostics: list[str] = []
    groups: list[list[Exam]] = []

    libretto = archive.latest(SOURCE, "libretto")
    if libretto is None:
        diagnostics.append("no archived Esse3 libretto page - run the scraper first")
    else:
        exams, notes = parser.parse_libretto(libretto.read_text())
        groups.append(exams)
        diagnostics.extend(notes)

    plan = archive.latest(SOURCE, "study-plan")
    if plan is not None:
        exams, notes = parser.parse_libretto(plan.read_text(), source="esse3:study-plan")
        groups.append(exams)

    enrollments = archive.latest(SOURCE, "exam-enrollments")
    if enrollments is not None:
        groups.append(parser.parse_exam_enrollments(enrollments.read_text()))

    student: dict[str, str] = {}
    career_page = archive.latest(SOURCE, "career")
    if career_page is not None:
        student = parser.parse_student_info(career_page.read_text())

    career = Career(
        exams=parser.merge_exams(*groups),
        student=student,
        scraped_at=libretto.fetched_at if libretto else None,
    )
    return career, diagnostics
