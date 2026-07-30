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

    return {"fetched": fetched, "failed": failed}


def load_enrolled_courses(archive: RawArchive | None = None) -> list[dict[str, str]]:
    """Course names and ids the student is enrolled in on Moodle."""
    archive = archive or RawArchive()
    record = archive.latest(SOURCE, "my-courses") or archive.latest(SOURCE, "dashboard")
    if record is None:
        return []

    markup = record.read_text()
    courses: dict[str, dict[str, str]] = {}

    # Moodle 4 embeds the course list as JSON in a web-service preload.
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
