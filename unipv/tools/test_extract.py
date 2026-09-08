"""Tests for classification and date extraction.

Every case is a filename that actually appears in the archive and was
classified wrongly at some point, not a hypothetical.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract import _words, classify, exam_date  # noqa: E402


def role(name: str, head: str = "") -> str:
    return classify(Path(name), head)


def when(name: str) -> str | None:
    return exam_date(Path(name), "")


class TestSeparatorsBreakWordBoundaries:
    """'_' is a word character, so \\b never fires between 'exam' and '_'.
    This silently classified 15 Machine Learning past papers as lecture notes."""

    def test_underscore_normalised(self):
        assert _words("exam_test_JULY24") == "exam test JULY24"

    def test_underscored_exam_is_a_paper(self):
        assert role("2024_exam_test_JULY24.pdf") == "PAST_PAPER"

    def test_plain_exam_is_a_paper(self):
        assert role("exam_test.pdf") == "PAST_PAPER"

    def test_lecture_is_not_a_paper(self):
        assert role("Lecture_03_intro.pdf") == "SLIDES"


class TestMonthNamedPapers:
    """Sittings are named by month far more often than by number."""

    def test_english_month_with_day(self):
        assert role("2023_19_September_2023.pdf") == "PAST_PAPER"
        assert when("2023_19_September_2023.pdf") == "2023-09-19"

    def test_month_run_together_with_day(self):
        assert when("2025_exam_18SEPT_2025.pdf") == "2025-09-18"

    def test_year_falls_back_to_the_folder_prefix(self):
        """The archive files by year and the prefix survives into the name."""
        assert when("2026_exam_test_FEB.pdf") == "2026-02-01"

    def test_italian_month(self):
        assert when("esame 5 giugno 2024.pdf") == "2024-06-05"


class TestRolePrecedence:
    def test_solutions_beat_papers(self):
        assert role("2024_exam_test_JULY24_soluzioni.pdf") == "SOLUTIONS"

    def test_presentation_format_beats_the_filename(self):
        """A .ppsx called 'Chapter 12' is a deck, not a chapter."""
        assert role("Chapter12.ppsx") == "SLIDES"

    def test_numeric_date_still_works(self):
        assert when("31_1_22A.pdf") == "2022-01-31"


class TestLectureMaterialIsNotAPaper:
    """A bare date pattern matched lecture numbering: "Prog2025_26_21b" reads
    as "25 26 21" and filed 154 Computer Programming slide decks as exam
    papers, inflating that course to 1039 questions extracted from slides."""

    def test_year_numbered_lecture_deck(self):
        assert role("Prog2025_26_21b_inheritance_double.pdf") != "PAST_PAPER"
        assert role("Prog2022_23_23_lab_inheritance_double.pdf") != "PAST_PAPER"

    def test_a_real_exam_in_the_same_folder_still_reads_as_one(self):
        assert role("Exam_09_09_2022.pdf") == "PAST_PAPER"
        assert role("Exam_21_07_2023.pdf") == "PAST_PAPER"

    def test_validated_date_alone_is_still_enough(self):
        """Computational Logic names its sittings by date and nothing else."""
        assert role("31_1_22A.pdf") == "PAST_PAPER"
        assert role("2023_19_September_2023.pdf") == "PAST_PAPER"

    def test_an_invalid_date_is_not_a_date(self):
        """Month 26 does not exist; the old pattern did not check."""
        from extract import exam_date
        assert exam_date(Path("Prog2025_26_21b_inheritance_double.pdf"), "") is None

    def test_dated_script_is_not_an_exam(self):
        assert role("wordle_2025-11-05.py") != "PAST_PAPER"
