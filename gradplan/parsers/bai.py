"""Parsers for the public BAI course-site documents.

Three things are extracted here, all from archived files:

* the graduation calendar (day, location, application deadline, deadline for
  report upload and exam recording) from the *Final examination regulations* PDF;
* the exam session windows from the enrolled-students page;
* the per-course exam sittings from the published session spreadsheets.
"""

from __future__ import annotations

import html
import re
from datetime import date
from typing import Iterable

from ..models import ExamSitting, GraduationSession, SessionWindow

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

LOCATION_KEYS = (
    ("bicocca", "Milano-Bicocca"),
    ("statale", "Milano Statale"),
    ("milano statale", "Milano Statale"),
    ("pavia", "Pavia"),
    # Per the footnote on the sittings sheet, 'Aula Teorici' is the Physics
    # department of Milano Statale in via Celoria.
    ("aula teorici", "Milano Statale"),
    ("milano", "Milano Statale"),
)

# Month names, longest first, so 'september' wins over 'sep' in alternation.
_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))

# The spreadsheet-to-PDF export glues adjacent columns together
# ('3-Sep14:00', 'MEASURES10-Sep'), so these patterns must not rely on word
# boundaries around the date — only on the month name itself.
_DATE_DMY = re.compile(rf"(?<!\d)(\d{{1,2}})\s+({_MONTH_ALT})\.?\s+(\d{{4}})(?!\d)", re.I)
_DATE_DM = re.compile(rf"(?<!\d)(\d{{1,2}})\s*-\s*({_MONTH_ALT})", re.I)


def _squash(text: str) -> str:
    """pypdf emits doubled spaces and stray breaks; collapse to single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def normalise_location(text: str) -> str:
    low = text.lower()
    for key, label in LOCATION_KEYS:
        if key in low:
            return label
    return text.strip()


def _month(name: str) -> int | None:
    return MONTHS.get(name.lower().strip("."))


# --- graduation calendar -----------------------------------------------------
def parse_graduation_calendar(pdf_text: str, academic_year: str = "") -> list[GraduationSession]:
    """Read the graduation-calendar table out of the regulations PDF text.

    Each row carries exactly three dates: the graduation day, the application
    deadline, and the deadline for report submission plus recording of all
    exams. Rows are matched on that shape rather than on column positions,
    which pypdf does not preserve.
    """
    sessions: list[GraduationSession] = []
    text = _squash(pdf_text)

    # Re-split on graduation-day boundaries: a row starts at a date and ends
    # just before the next one.
    matches = list(_DATE_DMY.finditer(text))
    for index, match in enumerate(matches):
        window = text[match.start(): matches[index + 3].start()
                      if index + 3 < len(matches) else len(text)]
        row_dates = _DATE_DMY.findall(window)
        if len(row_dates) < 3:
            continue
        parsed = []
        for day, month_name, year in row_dates[:3]:
            month = _month(month_name)
            if month is None:
                break
            parsed.append(date(int(year), month, int(day)))
        if len(parsed) != 3:
            continue

        graduation_day, application_deadline, records_deadline = parsed
        # Sanity: deadlines must precede the graduation day, and the
        # application deadline must precede the records deadline.
        if not (application_deadline < records_deadline < graduation_day):
            continue
        if any(s.date == graduation_day for s in sessions):
            continue

        between = window[row_dates[0][0].__len__():]
        location_match = re.search(
            r"(Univ\.?\s*of\s*[A-Za-z\- ]+|Universit[àa][A-Za-z\- ]*)", between
        )
        location = normalise_location(
            location_match.group(1) if location_match else ""
        )
        sessions.append(
            GraduationSession(
                date=graduation_day,
                location=location,
                application_deadline=application_deadline,
                records_deadline=records_deadline,
                academic_year=academic_year,
            )
        )
    sessions.sort(key=lambda s: s.date)
    return sessions


# --- exam session windows ----------------------------------------------------
_SESSION_LINE = re.compile(
    r"(Winter|Summer|Autumn)\s+session\s*[–-]\s*from\s+(.+?)\s+to\s+(.+?)\s+at\s+(.+)$",
    re.I,
)


def _fix_split_digits(text: str) -> str:
    """The site renders '31 July' as '3 1 July'; rejoin the split day."""
    names = "|".join(sorted(MONTHS, key=len, reverse=True))
    return re.sub(rf"\b(\d)\s+(\d)\s+({names})\b", r"\1\2 \3", text, flags=re.I)


def _year_for_month(month: int, ay_start: int) -> int:
    """Academic year 2025/26 runs Oct 2025 → Sep 2026."""
    return ay_start if month >= 10 else ay_start + 1


def exam_sessions_section(page_text: str) -> str:
    """Isolate the 'Exam Sessions' block.

    The page names several academic years (teaching activities, class
    schedules, past regulations), so the session dates and their academic year
    must be read from this section alone rather than from the whole page.
    """
    start = re.search(r"^\s*Exam\s+Sessions\s*$", page_text, re.I | re.M)
    if not start:
        return page_text
    tail = page_text[start.end():]
    end = re.search(r"^\s*(Graduation|Course Regulation|OFA)\b", tail, re.I | re.M)
    return tail[: end.start()] if end else tail


def parse_session_windows(page_text: str, ay_start: int | None = None) -> list[SessionWindow]:
    """Parse the three exam-session windows.

    ``ay_start`` overrides the academic year; by default it is read from the
    Exam Sessions section itself.
    """
    section = exam_sessions_section(page_text)
    if ay_start is None:
        ay_start = parse_academic_year(section)
    if ay_start is None:
        return []

    windows: list[SessionWindow] = []
    for raw_line in section.splitlines():
        line = _fix_split_digits(_squash(raw_line))
        match = _SESSION_LINE.search(line)
        if not match:
            continue
        name, start_raw, end_raw, host = match.groups()
        start = _parse_day_month(start_raw, ay_start)
        end = _parse_day_month(end_raw, ay_start)
        if start and end:
            windows.append(
                SessionWindow(
                    name=name.lower(),
                    start=start,
                    end=end,
                    host=normalise_location(host),
                )
            )
    return windows


def _parse_day_month(raw: str, ay_start: int) -> date | None:
    match = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})", raw)
    if not match:
        return None
    month = _month(match.group(2))
    if month is None:
        return None
    return date(_year_for_month(month, ay_start), month, int(match.group(1)))


def parse_academic_year(page_text: str) -> int | None:
    """Return the first year of the academic year, e.g. 2025 for 2025/26."""
    match = re.search(r"Academic\s+Year\s+(\d{4})\s*/\s*(\d{2,4})", page_text, re.I)
    if match:
        return int(match.group(1))
    match = re.search(r"a\.?y\.?\s*(\d{4})\s*[/_]\s*(\d{2,4})", page_text, re.I)
    return int(match.group(1)) if match else None


# --- exam sittings -----------------------------------------------------------
_TIME = re.compile(r"(?<!\d)\d{1,2}[:.]\d{2}(?!\d)")


def parse_exam_sittings(
    pdf_text: str,
    session_name: str,
    windows: Iterable[SessionWindow] = (),
) -> list[ExamSitting]:
    """Parse the 'Exam dates and locations' spreadsheet export.

    Rows look like::

        Algorithms and Data Structures 3-Sep14:00 B1/B2 Pavia Dondi

    The course name runs up to the ``D-Mon`` date; the tail holds time, room,
    location and teachers, glued together unpredictably by the PDF exporter.
    """
    window = next((w for w in windows if w.name == session_name.lower()), None)
    sittings: list[ExamSitting] = []

    for line in pdf_text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith(("course ", "locations", "tbd =")):
            continue
        match = _DATE_DM.search(line)
        if not match:
            continue
        month = _month(match.group(2))
        if month is None:
            continue

        course = line[: match.start()].strip(" .\t")
        if not course:
            continue
        tail = line[match.end():]

        day = int(match.group(1))
        year = _resolve_year(day, month, window)
        if year is None:
            continue
        try:
            sitting_date = date(year, month, day)
        except ValueError:
            continue

        time_match = _TIME.search(tail)
        time_value = time_match.group(0) if time_match else None
        rest = tail[time_match.end():] if time_match else tail

        location = None
        for key, label in LOCATION_KEYS:
            # The exporter glues neighbouring columns to the location on both
            # sides ('TAUStatale', 'Aula TeoriciGherardi'), so no word boundary
            # can be required. These tokens are distinctive enough that a plain
            # substring match does not produce false positives.
            found = re.search(re.escape(key), rest, re.I)
            if found:
                location = label
                room = rest[: found.start()].strip()
                rest = rest[found.end():]
                break
        else:
            room = rest.strip()
            rest = ""

        sittings.append(
            ExamSitting(
                course=course,
                date=sitting_date,
                session=session_name.lower(),
                location=location,
                room=(room or None),
                time=time_value,
                teachers=(rest.strip() or None),
            )
        )
    return sittings


def _resolve_year(day: int, month: int, window: SessionWindow | None) -> int | None:
    """Sitting PDFs omit the year; recover it from the session window."""
    if window is None:
        return None
    for year in {window.start.year, window.end.year}:
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if window.start <= candidate <= window.end:
            return year
    # Slightly outside the advertised window (extra dates) — fall back to the
    # year whose month matches.
    for year in (window.start.year, window.end.year):
        if month == window.start.month:
            return window.start.year
        if month == window.end.month:
            return window.end.year
    return window.end.year


# --- HTML helpers ------------------------------------------------------------
def html_to_text(markup: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", markup, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(p|div|li|h[1-6]|tr|table)>", "\n", text, flags=re.I)
    text = re.sub(r"</t[dh]>", "\t", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"[ \t]{2,}", " ", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def find_document_links(markup: str) -> dict[str, str]:
    """Map anchor text to href for the documents we care about."""
    links: dict[str, str] = {}
    for match in re.finditer(r"<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", markup, re.S | re.I):
        label = html.unescape(re.sub(r"<[^>]+>", "", match.group(2))).strip()
        if label:
            links.setdefault(label, html.unescape(match.group(1)))
    return links


def infer_home_universities(
    sittings: Iterable[ExamSitting],
    windows: Iterable[SessionWindow],
) -> dict[str, tuple[str, str]]:
    """Guess which university owns each course.

    Exams are normally held wherever the session is hosted, so the host
    location carries no information. A course examined *away* from the host,
    though, is anchored to its own university — that deviation is the signal.
    Returns ``{normalised_course: (university, confidence)}``.
    """
    from ..models import normalise_course_name

    hosts = {w.name: w.host for w in windows}
    away: dict[str, set[str]] = {}
    seen: dict[str, set[str]] = {}

    for sitting in sittings:
        if not sitting.location:
            continue
        key = normalise_course_name(sitting.course)
        seen.setdefault(key, set()).add(sitting.location)
        host = hosts.get(sitting.session)
        if host and sitting.location != host:
            away.setdefault(key, set()).add(sitting.location)

    result: dict[str, tuple[str, str]] = {}
    for key, locations in seen.items():
        deviations = away.get(key)
        if deviations and len(deviations) == 1:
            result[key] = (next(iter(deviations)), "inferred")
        elif len(locations) == 1:
            # Always examined in the same place across differently-hosted
            # sessions — that is its home too.
            result[key] = (next(iter(locations)), "inferred")
        else:
            result[key] = ("", "unknown")
    return result
