"""Parsers for archived Esse3 pages.

Esse3 is a Cineca product whose markup varies between installations and
releases, so nothing here depends on fixed column positions or CSS classes.
Tables are located by their *header keywords* (Italian and English), which is
the part that stays stable. Anything unrecognised is reported rather than
silently dropped, so parsing can be re-run against the archive and corrected.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Iterable

from bs4 import BeautifulSoup

from ..models import ENROLLED, NOT_TAKEN, PASSED, Exam

# Column header keywords -> logical field.
COLUMN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "name": ("attivit", "insegnamento", "descrizione", "activity", "course", "denominazione"),
    "code": ("codice", "cod.", "code"),
    "cfu": ("peso", "cfu", "crediti", "credits", "ects"),
    "mark": ("voto", "giudizio", "grade", "mark", "esito"),
    "date": ("data", "date"),
    "status": ("stato", "status"),
    "year": ("anno", "year"),
    "ssd": ("ssd", "settore"),
    "taf": ("taf", "tipo att", "ambito"),
}

_PASSED_WORDS = re.compile(r"superat|passed|sostenut|acquisit|convalidat|riconosciut", re.I)
_ENROLLED_WORDS = re.compile(r"prenotat|iscritt|booked|enrolled|in corso di", re.I)
_DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y")


def _text(node: Any) -> str:
    if node is None:
        return ""
    text = node.get_text(" ", strip=True)
    # Esse3 pads activity names with zero-width spaces and non-breaking spaces.
    text = text.replace("​", "").replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def split_mark_and_date(raw: str) -> tuple[str | None, date | None]:
    """Split a combined 'Voto - Data Esame' cell.

    The libretto reports the mark and the exam date in a single column, as
    ``'23 - 09/09/2025'``. Older installations use separate columns, so both
    shapes have to work.
    """
    if not raw:
        return None, None
    taken_on = parse_date(raw)
    if taken_on is None:
        return (raw.strip() or None), None
    mark_part = re.split(r"\d{1,4}[/-]\d{1,2}[/-]\d{2,4}", raw)[0]
    mark_part = mark_part.strip(" -–\t")
    return (mark_part or None), taken_on


def parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    match = re.search(r"\d{1,4}[/-]\d{1,2}[/-]\d{2,4}", raw)
    if not match:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(match.group(0), fmt).date()
        except ValueError:
            continue
    return None


def parse_cfu(raw: str | None) -> float | None:
    if not raw:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", raw)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _map_columns(header_cells: list[str]) -> dict[str, int]:
    """Map logical field -> column index, by keyword match on the header."""
    mapping: dict[str, int] = {}
    for index, raw in enumerate(header_cells):
        low = raw.lower()
        for field, keywords in COLUMN_KEYWORDS.items():
            if field in mapping:
                continue
            if any(keyword in low for keyword in keywords):
                mapping[field] = index
                break
    return mapping


def _header_rows(table) -> list[str]:
    head = table.find("thead")
    row = head.find("tr") if head else table.find("tr")
    if row is None:
        return []
    return [_text(cell) for cell in row.find_all(["th", "td"])]


def _row_status(cells: list[Any], texts: list[str], mapping: dict[str, int]) -> str:
    """Infer the lifecycle state of one libretto row.

    Esse3 shows the state as an icon, so the image ``alt``/``title`` matters as
    much as the cell text.
    """
    blob_parts: list[str] = []
    if "status" in mapping and mapping["status"] < len(cells):
        cell = cells[mapping["status"]]
        blob_parts.append(_text(cell))
        for img in cell.find_all("img"):
            blob_parts.extend(
                str(img.get(attr, "")) for attr in ("alt", "title", "src")
            )
    for cell in cells:
        for img in cell.find_all("img"):
            blob_parts.extend(str(img.get(attr, "")) for attr in ("alt", "title"))
    blob = " ".join(blob_parts)

    if _PASSED_WORDS.search(blob):
        return PASSED
    if _ENROLLED_WORDS.search(blob):
        return ENROLLED

    has_mark = bool(
        "mark" in mapping
        and mapping["mark"] < len(texts)
        and texts[mapping["mark"]].strip(" -")
    )
    has_date = bool(
        "date" in mapping
        and mapping["date"] < len(texts)
        and parse_date(texts[mapping["date"]])
    )
    if has_mark and has_date:
        return PASSED
    return NOT_TAKEN


def parse_activity_table(table, source: str, default_status: str | None = None) -> list[Exam]:
    """Turn one HTML table into Exam records, or return [] if it is not one."""
    header = _header_rows(table)
    mapping = _map_columns(header)
    if "name" not in mapping:
        return []

    exams: list[Exam] = []
    rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        texts = [_text(cell) for cell in cells]
        if all(cell.name == "th" for cell in cells):
            continue

        name = texts[mapping["name"]] if mapping["name"] < len(texts) else ""
        name = re.sub(r"^\s*\d{5,6}\s*[-–]\s*", "", name).strip()
        if not name or len(name) < 3:
            continue

        code = None
        if "code" in mapping and mapping["code"] < len(texts):
            code_match = re.search(r"\d{4,6}", texts[mapping["code"]])
            code = code_match.group(0) if code_match else None
        if code is None:
            code_match = re.match(r"\s*(\d{5,6})\s*[-–]", texts[mapping["name"]])
            code = code_match.group(1) if code_match else None

        cfu = parse_cfu(texts[mapping["cfu"]]) if "cfu" in mapping else None
        mark_raw = texts[mapping["mark"]].strip() if "mark" in mapping and mapping["mark"] < len(texts) else None
        if mark_raw in {"", "-", "--"}:
            mark_raw = None

        taken_on = parse_date(texts[mapping["date"]]) if "date" in mapping and mapping["date"] < len(texts) else None
        if mark_raw:
            # 'Voto - Data Esame' arrives as one cell on current Esse3.
            mark_raw, inline_date = split_mark_and_date(mark_raw)
            taken_on = taken_on or inline_date

        status = default_status or _row_status(cells, texts, mapping)
        year = None
        if "year" in mapping and mapping["year"] < len(texts):
            year_match = re.search(r"\b([1-9])\b", texts[mapping["year"]])
            year = int(year_match.group(1)) if year_match else None

        exams.append(
            Exam(
                name=name,
                cfu=cfu if cfu is not None else 0.0,
                status=status,
                code=code,
                mark_raw=mark_raw,
                date=taken_on,
                ssd=texts[mapping["ssd"]] if "ssd" in mapping and mapping["ssd"] < len(texts) else None,
                taf=texts[mapping["taf"]] if "taf" in mapping and mapping["taf"] < len(texts) else None,
                year=year,
                source=source,
            )
        )
    return exams


def parse_libretto(markup: str, source: str = "esse3:libretto") -> tuple[list[Exam], list[str]]:
    """Extract every activity from a libretto page.

    Returns ``(exams, diagnostics)``. Diagnostics list tables that looked like
    data but produced no rows, so the archive can be re-parsed after fixing.
    """
    soup = BeautifulSoup(markup, "lxml")
    exams: list[Exam] = []
    diagnostics: list[str] = []
    seen: set[tuple[str, str | None]] = set()

    for table in soup.find_all("table"):
        header = " | ".join(_header_rows(table))
        parsed = parse_activity_table(table, source)
        if not parsed:
            if re.search(r"cfu|crediti|voto|attivit", header, re.I):
                diagnostics.append(f"unparsed table with header: {header[:160]}")
            continue
        for exam in parsed:
            key = (exam.name.lower(), exam.code)
            if key in seen:
                continue
            seen.add(key)
            exams.append(exam)

    if not exams:
        diagnostics.append(
            "no activity rows found - the page may be a login redirect or the "
            "libretto may render its table via JavaScript"
        )
    return exams, diagnostics


def parse_exam_enrollments(markup: str) -> list[Exam]:
    """Parse the 'Bacheca prenotazioni' page (exams the student signed up for)."""
    soup = BeautifulSoup(markup, "lxml")
    exams: list[Exam] = []
    for table in soup.find_all("table"):
        exams.extend(parse_activity_table(table, "esse3:enrollments", default_status=ENROLLED))
    return exams


def parse_student_info(markup: str) -> dict[str, str]:
    """Best-effort scrape of the career header (enrolment year, course, status)."""
    soup = BeautifulSoup(markup, "lxml")
    info: dict[str, str] = {}
    for row in soup.find_all("tr"):
        cells = [_text(cell) for cell in row.find_all(["th", "td"])]
        if len(cells) == 2 and cells[0] and cells[1]:
            label = cells[0].rstrip(":").strip()
            if 2 < len(label) < 60 and len(cells[1]) < 200:
                info[label] = cells[1]
    return info


def merge_exams(*groups: Iterable[Exam]) -> list[Exam]:
    """Merge activity lists, preferring the most advanced known status.

    The same course appears in the libretto and in the enrolment board; passed
    beats enrolled, which beats not-yet-taken.
    """
    rank = {NOT_TAKEN: 0, ENROLLED: 1, PASSED: 2}
    merged: dict[tuple[str, str | None], Exam] = {}
    for group in groups:
        for exam in group:
            key = (exam.name.lower().strip(), exam.code)
            existing = merged.get(key)
            if existing is None:
                merged[key] = exam
                continue
            if rank[exam.status] > rank[existing.status]:
                # Keep whatever detail the weaker record had.
                exam.cfu = exam.cfu or existing.cfu
                exam.code = exam.code or existing.code
                merged[key] = exam
            else:
                existing.cfu = existing.cfu or exam.cfu
                existing.code = existing.code or exam.code
                existing.date = existing.date or exam.date
    return sorted(merged.values(), key=lambda e: (e.date or date.max, e.name))
