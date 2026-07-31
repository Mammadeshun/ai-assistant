"""Scrape Kiro (elearning.unipv.it), the UniPV Moodle.

Kiro carries no official career data, so it is a secondary source: it confirms
which courses the student is actually enrolled in this year, which helps label
activities whose university is ambiguous in Esse3, and surfaces the course
pages where thesis and lab information is published.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .. import config
from ..archive import RawArchive
from ..parsers.bai import html_to_text
from .browser import Session

SOURCE = "kiro"


def fetch_all(session: Session) -> dict[str, Any]:
    session.login(config.KIRO_SAML_LOGIN, success_marker="moodle")

    fetched: list[str] = []
    failed: list[str] = []

    try:
        session.goto(
            f"{config.KIRO_BASE}/my/courses.php",
            source=SOURCE,
            label="my-courses",
        )
        fetched.append("my-courses")
    except Exception as exc:  # noqa: BLE001
        failed.append(f"my-courses: {type(exc).__name__}: {exc}")

    try:
        session.goto(f"{config.KIRO_BASE}/my/", source=SOURCE, label="dashboard")
        fetched.append("dashboard")
    except Exception as exc:  # noqa: BLE001
        failed.append(f"dashboard: {type(exc).__name__}: {exc}")

    # Moodle 4 renders the course list client-side, so the HTML alone is empty.
    # The same data comes from the web-service endpoint the page itself calls.
    record = archive_latest_html(session)
    sesskey = _sesskey(record) if record else None
    if sesskey and hasattr(session, "post_json"):
        url = f"{config.KIRO_COURSES_API}?sesskey={sesskey}&info={COURSES_METHOD}"
        payload = [
            {
                "index": 0,
                "methodname": COURSES_METHOD,
                "args": {
                    "offset": 0,
                    "limit": 0,
                    "classification": "all",
                    "sort": "fullname",
                },
            }
        ]
        try:
            session.post_json(url, payload, source=SOURCE, label="courses-api")
            fetched.append("courses-api")
        except Exception as exc:  # noqa: BLE001
            failed.append(f"courses-api: {type(exc).__name__}: {exc}")
    elif not sesskey:
        failed.append("courses-api: no sesskey found on the page")

    return {"fetched": fetched, "failed": failed}


COURSES_METHOD = "core_course_get_enrolled_courses_by_timeline_classification"


def archive_latest_html(session):
    """The most recently archived Kiro page, whichever transport fetched it."""
    return session.archive.latest(SOURCE, "my-courses") or session.archive.latest(
        SOURCE, "dashboard"
    )


def _sesskey(record) -> str | None:
    markup = record.read_text()
    match = re.search(r'"sesskey":"([^"]+)"', markup) or re.search(
        r"sesskey=([A-Za-z0-9]+)", markup
    )
    return match.group(1) if match else None


def load_enrolled_courses(archive: RawArchive | None = None) -> list[dict[str, str]]:
    """Course names and ids the student is enrolled in on Moodle."""
    archive = archive or RawArchive()
    courses: dict[str, dict[str, str]] = {}

    # Preferred: the web-service response, which is what the page itself uses.
    api = archive.latest(SOURCE, "courses-api")
    if api is not None:
        try:
            for entry in _walk_courses(api.read_json()):
                courses[str(entry.get("id"))] = {
                    "id": str(entry.get("id")),
                    "name": entry.get("fullname", ""),
                    "shortname": entry.get("shortname", ""),
                }
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    if courses:
        return sorted(courses.values(), key=lambda c: c["name"])

    record = archive.latest(SOURCE, "my-courses") or archive.latest(SOURCE, "dashboard")
    if record is None:
        return []
    markup = record.read_text()

    for blob in re.findall(r'"courses"\s*:\s*(\[.*?\])\s*[,}]', markup, re.S):
        try:
            for entry in json.loads(blob):
                if isinstance(entry, dict) and entry.get("fullname"):
                    courses[str(entry.get("id"))] = {
                        "id": str(entry.get("id")),
                        "name": entry["fullname"],
                        "shortname": entry.get("shortname", ""),
                    }
        except (json.JSONDecodeError, TypeError):
            continue

    if not courses:
        for course_id, label in re.findall(
            r'href="[^"]*course/view\.php\?id=(\d+)"[^>]*>(.*?)</a>', markup, re.S
        ):
            name = html_to_text(label).strip()
            if name and len(name) > 3:
                courses.setdefault(course_id, {"id": course_id, "name": name, "shortname": ""})

    return sorted(courses.values(), key=lambda c: c["name"])


def _walk_courses(payload: Any) -> list[dict[str, Any]]:
    """Pull the course list out of Moodle's ``[{data: {courses: [...]}}]``."""
    if isinstance(payload, list):
        found: list[dict[str, Any]] = []
        for item in payload:
            found.extend(_walk_courses(item))
        return found
    if isinstance(payload, dict):
        if payload.get("error"):
            raise ValueError(str(payload.get("exception", "web service error")))
        courses = payload.get("courses")
        if isinstance(courses, list):
            return [c for c in courses if isinstance(c, dict) and c.get("fullname")]
        return _walk_courses(payload["data"]) if "data" in payload else []
    return []
