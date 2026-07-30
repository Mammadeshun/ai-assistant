"""Assemble ``data/career.json`` from the archived sources."""

from __future__ import annotations

import json
from typing import Any

from . import config
from .archive import RawArchive
from .models import Career, normalise_course_name
from .parsers.bai import infer_home_universities
from .sources import bai, esse3


def attach_universities(career: Career, archive: RawArchive) -> list[str]:
    """Label each activity with the university that owns it.

    Esse3 wins when it says anything. Otherwise the label is inferred from the
    published exam calendars: sessions rotate between the three campuses, so a
    course examined away from the hosting university is anchored to its own.
    """
    notes: list[str] = []
    sittings = bai.load_exam_sittings(archive)
    windows = bai.load_session_windows(archive)
    if not sittings:
        notes.append("no archived exam calendars - university left unknown")
        return notes

    homes = infer_home_universities(sittings, windows)
    unresolved: list[str] = []
    for exam in career.exams:
        if exam.university:
            exam.university_confidence = "esse3"
            continue
        key = normalise_course_name(exam.name)
        university, confidence = homes.get(key, ("", "unknown"))
        if university:
            exam.university = university
            exam.university_confidence = confidence
        else:
            exam.university_confidence = "unknown"
            unresolved.append(exam.name)

    if unresolved:
        notes.append(
            f"{len(unresolved)} activities could not be attributed to a university "
            "(they are always examined wherever the session is hosted)"
        )
    return notes


def build(archive: RawArchive | None = None, write: bool = True) -> tuple[Career, list[str]]:
    archive = archive or RawArchive()
    career, diagnostics = esse3.load_career(archive)
    diagnostics.extend(attach_universities(career, archive))

    if write:
        config.ensure_dirs()
        payload: dict[str, Any] = career.to_json()
        payload["diagnostics"] = diagnostics
        config.CAREER_JSON.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return career, diagnostics


def load(path=None) -> Career:
    """Read back a previously written career.json."""
    from .models import Exam
    from datetime import date

    path = path or config.CAREER_JSON
    data = json.loads(path.read_text(encoding="utf-8"))
    exams = []
    for raw in data.get("exams", []):
        raw = dict(raw)
        raw.pop("counts_for_average", None)
        if raw.get("date"):
            raw["date"] = date.fromisoformat(raw["date"])
        exams.append(Exam(**raw))
    return Career(
        exams=exams,
        student=data.get("student", {}),
        scraped_at=data.get("scraped_at"),
    )
