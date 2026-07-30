"""Fetch the public BAI course-site documents.

No authentication is involved: these are the published rules and calendars for
the degree. Requests are sequential with a delay, and every response is
archived before anything is parsed.
"""

from __future__ import annotations

import re
import time
import urllib.request
from datetime import date
from typing import Any

from .. import config
from ..archive import RawArchive
from ..models import ExamSitting, GraduationSession, SessionWindow
from ..parsers import bai as parser

SOURCE = "bai"

LABEL_ENROLLED = "enrolled-students"
LABEL_STUDY_PLAN = "study-plan"
LABEL_REGULATIONS = "final-examination-regulations"
LABEL_SITTINGS = "exam-sittings-{session}"


def _get(url: str) -> tuple[bytes, int]:
    request = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read(), response.status


def fetch_all(archive: RawArchive | None = None, delay: float | None = None) -> dict[str, Any]:
    """Download every public document we depend on and archive it.

    Returns a summary of what was fetched, including any document whose link
    could not be found on the page.
    """
    archive = archive or RawArchive()
    delay = config.REQUEST_DELAY_SECONDS if delay is None else delay
    fetched: list[str] = []
    missing: list[str] = []

    body, status = _get(config.BAI_ENROLLED_STUDENTS)
    markup = body.decode("utf-8", errors="replace")
    archive.save(
        source=SOURCE,
        label=LABEL_ENROLLED,
        url=config.BAI_ENROLLED_STUDENTS,
        payload=markup,
        kind="html",
        status=status,
    )
    fetched.append(LABEL_ENROLLED)
    time.sleep(delay)

    body, status = _get(config.BAI_STUDY_PLAN)
    archive.save(
        source=SOURCE,
        label=LABEL_STUDY_PLAN,
        url=config.BAI_STUDY_PLAN,
        payload=body.decode("utf-8", errors="replace"),
        kind="html",
        status=status,
    )
    fetched.append(LABEL_STUDY_PLAN)
    time.sleep(delay)

    links = parser.find_document_links(markup)

    regulations_url = _pick_regulations(links)
    if regulations_url:
        body, status = _get(regulations_url)
        archive.save(
            source=SOURCE,
            label=LABEL_REGULATIONS,
            url=regulations_url,
            payload=body,
            kind="pdf",
            status=status,
        )
        fetched.append(LABEL_REGULATIONS)
        time.sleep(delay)
    else:
        missing.append(LABEL_REGULATIONS)

    for session in ("winter", "summer", "autumn"):
        url = _pick_sitting_sheet(links, session)
        label = LABEL_SITTINGS.format(session=session)
        try:
            body, status = _get(url)
        except Exception as exc:  # noqa: BLE001 - one bad tab must not stop the rest
            missing.append(f"{label} ({type(exc).__name__})")
            continue
        if not body.startswith(b"%PDF"):
            missing.append(f"{label} (not a PDF, tab may be unpublished)")
            continue
        archive.save(
            source=SOURCE,
            label=label,
            url=url,
            payload=body,
            kind="pdf",
            status=status,
        )
        fetched.append(label)
        time.sleep(delay)

    return {"fetched": fetched, "missing": missing}


def _pick_regulations(links: dict[str, str]) -> str | None:
    """Prefer the most recent 'Final examination regulations and calendar'."""
    candidates = [
        (label, url)
        for label, url in links.items()
        if re.search(r"final\s+examination\s+regulations", label, re.I)
    ]
    if not candidates:
        candidates = [
            (label, url)
            for label, url in links.items()
            if "final-examination-regulations" in url.lower()
        ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: _year_key(item[0] + " " + item[1]))
    return candidates[-1][1]


def _year_key(text: str) -> tuple[int, int]:
    years = [int(y) for y in re.findall(r"(20\d{2})", text)]
    return (max(years) if years else 0, len(text))


def _pick_sitting_sheet(links: dict[str, str], session: str) -> str:
    for label, url in links.items():
        if re.fullmatch(rf"{session}\s+session", label.strip(), re.I):
            return url.replace("&amp;", "&")
    tab = config.BAI_EXAM_SHEET_TABS[session]
    return f"{config.BAI_EXAM_SHEET}?gid={tab}&single=true&output=pdf"


# --- loading from the archive ------------------------------------------------
def _pdf_text(path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def load_graduation_sessions(archive: RawArchive | None = None) -> list[GraduationSession]:
    archive = archive or RawArchive()
    record = archive.latest(SOURCE, LABEL_REGULATIONS)
    if record is None:
        return []
    text = _pdf_text(record.path)
    match = re.search(r"a\.?y\.?\s*(\d{4})\s*/\s*(\d{2,4})", text, re.I)
    academic_year = f"{match.group(1)}/{match.group(2)}" if match else ""
    return parser.parse_graduation_calendar(text, academic_year=academic_year)


def load_session_windows(archive: RawArchive | None = None) -> list[SessionWindow]:
    archive = archive or RawArchive()
    record = archive.latest(SOURCE, LABEL_ENROLLED)
    if record is None:
        return []
    text = parser.html_to_text(record.read_text())
    return parser.parse_session_windows(text)


def load_exam_sittings(archive: RawArchive | None = None) -> list[ExamSitting]:
    archive = archive or RawArchive()
    windows = load_session_windows(archive)
    sittings: list[ExamSitting] = []
    for session in ("winter", "summer", "autumn"):
        record = archive.latest(SOURCE, LABEL_SITTINGS.format(session=session))
        if record is None:
            continue
        sittings.extend(
            parser.parse_exam_sittings(_pdf_text(record.path), session, windows)
        )
    sittings.sort(key=lambda s: (s.course.lower(), s.date))
    return sittings
