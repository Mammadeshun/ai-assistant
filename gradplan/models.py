"""Core data model shared by scrapers, parsers and the planner."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Iterable

# Exam lifecycle states, as reported by Esse3 and normalised here.
PASSED = "passed"
ENROLLED = "enrolled"
NOT_TAKEN = "not_yet_taken"

_LODE = re.compile(r"lode|cum\s*laude|30L", re.I)
_IDONEO = re.compile(r"idone|approv|pass(ed)?$", re.I)


def parse_mark(raw: str | None) -> tuple[int | None, bool, bool]:
    """Normalise an Esse3 mark string.

    Returns ``(numeric_mark, is_lode, is_pass_fail)``.

    Esse3 writes marks as ``"28"``, ``"30 e lode"``, ``"30L"`` or ``"IDONEO"``.
    Pass/fail activities (labs, stage, language) carry no number and are
    excluded from the weighted average by the degree regulations.
    """
    if raw is None:
        return None, False, False
    text = str(raw).strip()
    if not text or text in {"-", "--"}:
        return None, False, False
    lode = bool(_LODE.search(text))
    # Esse3 writes lode as '30L', with no boundary between number and letter.
    match = re.search(r"(?<!\d)(\d{1,2})(?!\d)", text)
    if match:
        value = int(match.group(1))
        if 0 <= value <= 30:
            return value, lode, False
    if _IDONEO.search(text):
        return None, False, True
    return None, lode, False


@dataclass
class Exam:
    """One activity in the student's libretto or study plan."""

    name: str
    cfu: float
    status: str = NOT_TAKEN
    code: str | None = None
    mark_raw: str | None = None
    mark: int | None = None
    lode: bool = False
    pass_fail: bool = False
    date: date | None = None
    university: str | None = None
    university_confidence: str = "unknown"  # esse3 | inferred | unknown
    ssd: str | None = None
    taf: str | None = None
    year: int | None = None
    source: str = ""

    def __post_init__(self) -> None:
        if self.mark is None and self.mark_raw is not None:
            self.mark, self.lode, self.pass_fail = parse_mark(self.mark_raw)

    @property
    def counts_for_average(self) -> bool:
        """Only graded exams feed the weighted average (regulations, p.2)."""
        return self.status == PASSED and self.mark is not None and not self.pass_fail

    @property
    def earned_cfu(self) -> float:
        return self.cfu if self.status == PASSED else 0.0

    def to_json(self) -> dict[str, Any]:
        out = asdict(self)
        out["date"] = self.date.isoformat() if self.date else None
        out["counts_for_average"] = self.counts_for_average
        return out


@dataclass
class ExamSitting:
    """A scheduled ``appello`` for a course, from the published calendar."""

    course: str
    date: date
    session: str  # winter | summer | autumn | extra
    location: str | None = None
    room: str | None = None
    time: str | None = None
    teachers: str | None = None

    def to_json(self) -> dict[str, Any]:
        out = asdict(self)
        out["date"] = self.date.isoformat()
        return out


@dataclass
class GraduationSession:
    """A graduation day plus its two binding deadlines.

    ``records_deadline`` is the date by which the report must be uploaded *and*
    every exam must already be recorded — one week before the graduation day.
    """

    date: date
    location: str
    application_deadline: date
    records_deadline: date
    academic_year: str = ""
    # True when the session is extrapolated from the published pattern rather
    # than taken from an official calendar.
    projected: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "location": self.location,
            "application_deadline": self.application_deadline.isoformat(),
            "records_deadline": self.records_deadline.isoformat(),
            "academic_year": self.academic_year,
            "projected": self.projected,
        }


@dataclass
class SessionWindow:
    """An exam session window (winter / summer / autumn)."""

    name: str
    start: date
    end: date
    host: str

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "host": self.host,
        }


@dataclass
class Requirement:
    """Something still standing between the student and the degree."""

    name: str
    cfu: float
    kind: str  # exam | thesis | free_choice | lab_or_stage
    code: str | None = None
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Career:
    """The parsed academic career."""

    exams: list[Exam] = field(default_factory=list)
    student: dict[str, Any] = field(default_factory=dict)
    scraped_at: str | None = None

    def by_status(self, status: str) -> list[Exam]:
        return [e for e in self.exams if e.status == status]

    @property
    def passed(self) -> list[Exam]:
        return self.by_status(PASSED)

    @property
    def cfu_earned(self) -> float:
        return sum(e.earned_cfu for e in self.exams)

    def weighted_average(self) -> float | None:
        """CFU-weighted average over graded, passed exams."""
        graded = [e for e in self.exams if e.counts_for_average]
        total_cfu = sum(e.cfu for e in graded)
        if not total_cfu:
            return None
        return sum(e.mark * e.cfu for e in graded) / total_cfu

    def base_graduation_score(self) -> int | None:
        """Weighted average scaled by 11/3 and rounded (regulations, p.2)."""
        avg = self.weighted_average()
        if avg is None:
            return None
        return round(avg * 11 / 3)

    def to_json(self) -> dict[str, Any]:
        return {
            "student": self.student,
            "scraped_at": self.scraped_at,
            "summary": {
                "cfu_earned": self.cfu_earned,
                "cfu_required": 180,
                "exams_passed": len(self.passed),
                "weighted_average": (
                    round(self.weighted_average(), 3)
                    if self.weighted_average() is not None
                    else None
                ),
                "base_graduation_score": self.base_graduation_score(),
            },
            "exams": [e.to_json() for e in self.exams],
        }


# The regolamento, the exam calendar and Esse3 spell the same course three
# ways: British vs American '-modelling', 'AI' vs 'Artificial Intelligence',
# singular vs plural 'Logic(s)'. Fold them onto one key.
_SYNONYMS = (
    (r"\bartificial intelligence\b", "ai"),
    (r"\bmodelling\b", "modeling"),
    (r"\blogics\b", "logic"),
    (r"\blaboratory of\b", "lab"),
    (r"\blaboratorio di\b", "lab"),
    (r"\band\b", "&"),
)


def normalise_course_name(name: str) -> str:
    """Key used to match libretto entries against calendar entries.

    Calendar and libretto disagree on case, module suffixes and punctuation:
    ``"Calculus (part 1)"`` vs ``"CALCULUS - mod. 1"``. Strip all of it.
    """
    text = name.lower().strip()
    text = re.sub(r"\((part|mod\.?|module)\s*\d+\)", " ", text)
    text = re.sub(r"[-–]\s*(mod\.?|module|part)\s*\d+", " ", text)
    text = re.sub(r"\b(written|oral|scritto|orale)\b", " ", text)
    for pattern, replacement in _SYNONYMS:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"[^a-z0-9&]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def match_course_key(name: str, candidates: Iterable[str], cutoff: float = 0.86) -> str | None:
    """Resolve a course name against known calendar keys.

    Exact normalised match first, then a close match, because the three
    sources phrase long titles differently ('Logic for Practical Reasoning and
    Artificial Intelligence' vs 'Logics for practical reasoning and AI').
    """
    from difflib import get_close_matches

    key = normalise_course_name(name)
    candidate_list = list(candidates)
    if key in candidate_list:
        return key
    close = get_close_matches(key, candidate_list, n=1, cutoff=cutoff)
    return close[0] if close else None


def index_by_course(sittings: Iterable[ExamSitting]) -> dict[str, list[ExamSitting]]:
    index: dict[str, list[ExamSitting]] = {}
    for sitting in sittings:
        index.setdefault(normalise_course_name(sitting.course), []).append(sitting)
    for values in index.values():
        values.sort(key=lambda s: s.date)
    return index
