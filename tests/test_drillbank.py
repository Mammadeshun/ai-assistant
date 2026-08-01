"""Tests for the drill-bank extraction layer.

Every case here is a bug that actually shipped and produced a wrong report,
not a hypothetical.
"""

from __future__ import annotations

from pathlib import Path

from gradplan.drillbank import (
    Document,
    QuestionType,
    _moodle_text,
    _words,
    cluster,
    split_mcq,
    split_paper,
)
from gradplan.predictability import Item


def _doc(name: str, *, parent: str = "", kind: str = "pdf") -> Document:
    return Document(course="509483", name=name, path=Path("/dev/null"), kind=kind, parent=parent)


class TestNameMatching:
    def test_underscore_does_not_break_the_word_boundary(self):
        """'Exam_Assignments' hid the whole Computational Logic archive: `\\b`
        does not fire between 'exam' and '_' because '_' is a word character."""
        assert "Exam Assignments" == _words("Exam_Assignments")
        assert _doc("ex2_1A.txt", parent="Exam_Assignments").looks_like_paper

    def test_trailing_digits_do_not_break_it_either(self):
        """'Esame1'..'Esame6' are the Statistical Modelling past papers."""
        assert _doc("Esame1.pdf").looks_like_paper
        assert _doc("Esame6.pdf").looks_like_paper

    def test_examples_is_not_an_exam(self):
        """Lecture 'Examples' folders must not be counted as papers."""
        assert not _doc("Examples").looks_like_paper

    def test_date_named_papers_are_recognised(self):
        assert _doc("31 1 22A pdf").looks_like_paper
        assert _doc("13 6 2023B pdf").looks_like_paper

    def test_code_in_an_exam_folder_is_a_key_not_a_paper(self):
        """SMT-LIB encodings answer the paper; treating them as papers would
        fabricate question types out of solver source."""
        assert _doc("martiansA txt", parent="Exam_Assignments", kind="text").is_solution
        assert not _doc("31 1 22A pdf", parent="Exam_Assignments").is_solution

    def test_named_solutions_are_keys(self):
        assert _doc("Exam 2022-02-07 (with solutions)").is_solution
        assert _doc("2025 Mock Exam Solutions").is_solution


class TestMoodleExtraction:
    def test_quiz_questions_are_pulled_out_structurally(self):
        markup = """<html><body><div id="region-main">
          <div class="que"><div class="qtext">Which store holds capacity of seven items?</div></div>
          <div class="que"><div class="qtext">Define the phonological loop.</div></div>
        </div></body></html>"""
        text = _moodle_text(markup)
        assert "Question 1." in text and "Question 2." in text
        assert "phonological loop" in text

    def test_chrome_is_stripped(self):
        markup = """<html><head><style>body{}</style></head><body>
          <nav>menu menu menu</nav>
          <div id="region-main">the actual content</div>
          <footer>footer junk</footer></body></html>"""
        text = _moodle_text(markup)
        assert "the actual content" in text
        assert "menu" not in text and "footer junk" not in text


class TestSplitting:
    def test_bare_numbered_mcq_is_split(self):
        """Quantum Physics numbers questions bare, with no 'Question' word, so
        the generic splitter returned the whole paper as one item."""
        paper = "\n".join(
            f"{n} Stem of question {n}?\n1. alpha\n2. beta\n3. gamma\n4. delta"
            for n in range(1, 7)
        )
        items = split_mcq(paper, "mock")
        assert len(items) == 6
        assert "Stem of question 1" in items[0].text

    def test_option_lists_do_not_start_new_questions(self):
        """Options are numbered lines too; only punctuation tells them apart."""
        paper = "\n".join(
            f"{n} Which of the following statements about topic {n} is true?\n"
            "1. the first plausible-looking distractor\n"
            "2. the second plausible-looking distractor\n"
            "3. the third plausible-looking distractor"
            for n in range(1, 5)
        )
        items = split_mcq(paper, "p")
        assert len(items) == 4
        assert all("Which of the following" in i.text for i in items)

    def test_split_paper_prefers_whichever_finds_more(self):
        mcq = "\n".join(
            f"{n} Stem number {n} asking something reasonably long here?\n"
            "1. alpha option\n2. beta option"
            for n in range(1, 9)
        )
        assert len(split_paper(mcq, "p")) == 8

    def test_too_few_numbers_is_not_an_mcq_paper(self):
        assert split_mcq("1 Only one numbered thing here, really.", "p") == []


class TestClustering:
    def test_renumbered_template_collapses_to_one_type(self):
        stem = (
            "Given the AVL tree in figure add one by one nodes with the following "
            "keys: {}. NOTE: remember to verify the balancing after each insertion."
        )
        items = [
            Item(paper="2022", index=0, marks=6, text=stem.format("20, 7, 16"), topic="trees"),
            Item(paper="2023", index=0, marks=6, text=stem.format("32, 99, 55"), topic="trees"),
        ]
        groups = cluster(items)
        assert len(groups) == 1
        assert groups[0].n_papers == 2

    def test_different_exercises_stay_apart(self):
        items = [
            Item(paper="a", index=0, marks=5, text="Compute the eigenvalues of the matrix.", topic="t"),
            Item(paper="b", index=0, marks=5, text="Prove that the sample variance is unbiased.", topic="t"),
        ]
        assert len(cluster(items)) == 2

    def test_same_paper_twice_counts_as_one_paper(self):
        text = "Solve the recurrence relation given below by substitution."
        items = [
            Item(paper="a", index=0, marks=3, text=text, topic="t"),
            Item(paper="a", index=1, marks=3, text=text, topic="t"),
        ]
        groups = cluster(items)
        assert groups[0].n_papers == 1

    def test_representative_is_the_longest_member(self):
        group = QuestionType(
            topic="t",
            members=[
                Item(paper="a", index=0, marks=None, text="short"),
                Item(paper="b", index=0, marks=None, text="a much longer statement of it"),
            ],
        )
        assert group.representative.text.startswith("a much longer")


class TestSplitStrategies:
    """Six formats appear in the archive; one pattern never covered them."""

    def test_dotted_parts_split(self):
        """Computational Logic numbers its parts (1.1), (1.2)."""
        from gradplan.drillbank import split_dotted
        paper = (
            "Part I: Questions.\n"
            "(1.1) We are given a language L comprising binary predicate symbols R and S.\n"
            "(1.2) The Herbrand universe for the language L mentioned above is finite.\n"
            "(1.3) Which one of the following statements is correct about transformations?\n"
        )
        assert len(split_dotted(paper, "p")) == 3

    def test_numbered_with_marks_split(self):
        """Web & Social and Brain Modelling: '1. [3 points] Illustrate...'"""
        from gradplan.drillbank import split_numbered
        paper = (
            "1. [3 points] Illustrate the main characteristics underlying complex networks.\n"
            "2. [4 points] Given the undirected graph G, indicate the maximal cliques.\n"
            "3. [5 points] Illustrate the concepts of Web 1.0 and Web 2.0 in detail.\n"
            "4. [3 points] What is assortativity in network theory and why does it matter?\n"
        )
        assert len(split_numbered(paper, "p")) == 4

    def test_imperative_prompts_split(self):
        """Information Retrieval numbers nothing and answers in prose."""
        from gradplan.drillbank import split_imperative
        paper = (
            "Please, describe how offline evaluations are conducted in Information "
            "Retrieval, covering benchmark collections and how they are created in full.\n"
            "Offline evaluation rests on the Cranfield paradigm and a test collection "
            "which acts as a laboratory for simulating the behaviour of real users.\n"
            "Explain the concept of the cold start problem in recommender systems and "
            "describe briefly why it matters for a newly launched catalogue of items.\n"
            "The cold start problem arises whenever a new user or a new item has no "
            "interaction history at all, so collaborative signals are unavailable.\n"
        )
        assert len(split_imperative(paper, "p")) == 2

    def test_question_list_needs_its_header(self):
        """Calculus publishes a bank of one-line questions; other papers do not."""
        from gradplan.drillbank import split_question_list
        listed = (
            "Calculus - Part 1\nPossible questions for the theoretical part of the test\n"
            "Definitions of supremum, infimum, maximum and minimum.\n"
            "Definition of limit for a sequence and for a function.\n"
            "Uniqueness of the limit (with proof).\n"
            "Weierstrass Theorem and its consequences.\n"
        )
        assert len(split_question_list(listed, "p")) == 4
        assert split_question_list("An ordinary paper with no such header.\n" * 8, "p") == []

    def test_theoretical_in_a_title_is_not_a_question_list(self):
        """'theoretical & quantum physics' in a mock exam title split that paper
        into one item per line."""
        from gradplan.drillbank import split_question_list
        mock = (
            "theoretical & quantum physics for AI - MODULE 1\nMOCK EXAM\n"
            "1 What is a sufficient condition for the formula to be consistent?\n"
            "1. x and a have the same dimensions\n2. the dimensions are inverse\n"
            "3. x has the dimensions of length\n4. x and a are dimensionless\n"
            "2 Imagine applying the Rayleigh method to obtain a formula for x.\n"
            "1. both y and z appear explicitly\n2. only an inverse formula results\n"
            "3 A third numbered question follows here with its own set of options.\n"
            "4 A fourth numbered question follows here with its own set of options.\n"
        )
        assert split_question_list(mock, "p") == []

    def test_split_paper_picks_the_productive_strategy(self):
        paper = (
            "(1.1) First part of the question about Herbrand universes and models.\n"
            "(1.2) Second part of the question about Skolemization of the sentence.\n"
            "(1.3) Third part of the question about structural transformations here.\n"
        )
        assert len(split_paper(paper, "p")) == 3
