#!/usr/bin/env python3
"""One study pack per exam: what to do, in order, with the files named.

The method text is judgement and is kept here, in one place, separate from the
measured data (drill banks, novelty, gates) that gets merged into it. Anything
stated as a number comes from the archive; anything stated as an instruction is
mine, and is meant to be argued with.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = Path("reference/packs")
DRILL = Path("data/drill")

# code: (name, when, hours, cfu, gate, [steps], skip, tactic)
PACKS = {
    "509496": (
        "Information Retrieval and Recommender Systems", "31 Aug", 30, 6,
        "Project + presentation. No written paper exists.",
        [
            "Read `Project Instructions 2026 June - July` first — build to the spec, not to your own taste.",
            "Email Peikos about an autumn presentation slot. Every slot in the forums is February, June or July. Without one there is no exam.",
            "Build the IR half: index, retrieval, query expansion. Reuse the published dataset code.",
            "Build the RecSys half on the same codebase.",
            "Ten-minute deck: method, results, one honest limitation.",
        ],
        "Do not start a second codebase for Web & Social — it is the same machinery.",
        "This is work, not revision. It can be done tired, in the evening, which is why it sits first in the calendar.",
    ),
    "509521": (
        "Laboratory of Machine Learning", "01 Sep", 25, 3,
        "Nine report submissions. The reports are the grade — there is no exam.",
        [
            "TODAY: open the edition and read the nine due dates. If the windows are shut, this course is gone for September and you have saved 25 hours.",
            "If open, do them in numeric order and submit as you go — do not batch them.",
            "Keep each report short and complete. Completeness is what is marked, not elegance.",
        ],
        "Nothing. All nine count.",
        "This is the same failure mode that killed AI Marketing: a Moodle window that closed quietly. Check it before you plan around it.",
    ),
    "509519": (
        "Ethics, Law and AI", "02 Sep", 28, 12,
        "Multiple choice, one unsplit exam. No gate beyond 18.",
        [
            "Read the forum thread `Exam format and content` — it is the only statement of the rules.",
            "Get the non-attending syllabus (Kiro 5123, mod/resource/132265) and email Faroldi to confirm it still binds.",
            "Build a fact sheet: definitions, AI Act articles, named cases. One line each.",
            "Self-quiz from the fact sheet. There are no past papers, so recall practice has to be manufactured.",
        ],
        "Anything not on the non-attending list. The syllabus is the exam.",
        "Twelve credits for 28 hours — the best rate in your degree, tied with Machine Learning. Do not under-invest because it sounds soft.",
    ),
    "509494": (
        "Brain Modelling", "03 Sep", 26, 6,
        "Coding project 30% + written 70% (open questions, ~2h).",
        [
            "Email Casellato for the project-topics document and confirm the 30/70 split still holds.",
            "Do the project first. Its mark carries across every session of the same academic year — it is the only work here that cannot be wasted.",
            "Written: open questions on the lecture notes. No past papers exist.",
        ],
        "Coding in the written part — the forum states the project exists precisely so the written has none.",
        "If you fall behind, sit the project and skip the written. You keep 30% and lose nothing.",
    ),
    "509495": (
        "Data Mining and Knowledge Extraction", "04 Sep", 19, 6,
        "Assignments (12/30) + written. The assignments were set during delivery and cannot be recovered — you sit for the full 30.",
        [
            "`Past Assignment 1 (24/10)` then `Exercise on Past Assignment (25/10)`.",
            "Install PostgreSQL and load `Example Database (actordb)`. Do not read SQL, run it.",
            "`Mockup Exam (07/01/2026)`, then `Mockup Exam (12/01)`, then `Mockup Exam`.",
            "Frequent itemset mining from the LTI recording.",
        ],
        "Nothing safely — see the tactic.",
        "Novelty 0.54: the only partly-templated exam in the plan. Half of each paper is genuinely new, so past papers give you format, not answers. Do not let the high recurrence numbers fool you here.",
    ),
    "509485": (
        "Cognitive Psychology", "08 Sep", 27, 6,
        "Written 25 pts (5 MCQ + 20 open) AND a compulsory oral (6 pts). Edition 7392 binds: threshold 12, final mark is the SUM.",
        [
            "Work the chapter quizzes: chapters 1, 2, 3, 5, 6, 8, 10. These are your MCQ drill and they are already extracted into the cockpit.",
            "Read the research papers behind `Questions on research paper` (STM, LTM, TPS, Language). The oral draws on them.",
            "`Oral exam topics` (PDF) is the oral question bank. Prepare a six-to-eight minute answer for every item.",
            "`September 16th Oral exam questions' choice` shows how the question is picked.",
        ],
        "The attendance bonus — it needed in-class presence and is not available to you.",
        "DO NOT email Bricolo about the syllabus. Silence keeps you on edition 7392, threshold 12 rather than 13. Asking costs you a mark.",
    ),
    "509477": (
        "Computer Programming, Algorithms and Data Structures", "09 Sep", 44, 12,
        "TWO INDEPENDENT GATES on module 2: theory >=12/20 AND code >=6/10. Non-running code is an automatic fail.",
        [
            "`Exam 23/06/2022 - with Solutions`, then `Exam 14/07/2022 - with Solutions`.",
            "`Exam 09/09/2022 - with Solutions` — a September paper. Do it twice.",
            "`Exam 21/07/2023 - Code Solution Only`.",
            "The three `Examples` folders and `Stack-test-py` for the code half.",
            "Module 1 project option: `2021-22-castles-war-pdf`, `2022-23-planisuss-v0-95-pdf`. Your 2023/24 cohort qualifies.",
        ],
        "Nothing on trees or linear structures — they are 69% of every paper.",
        "The code gate is not what fails people; the 12/20 theory gate is. AVL insert-and-rebalance appears in both the 2022 and 2023 papers with only the key values changed (measured similarity 0.567). Memorise the rotation cases. For the code half: run every function before you submit.",
    ),
    "509481": (
        "Calculus", "11 Sep", 44, 12,
        "Part 1 >= 15/30 on top of the overall 18. Closed book. Oral at the board's request. No Part 1 / Part 2 split exists in autumn 2026.",
        [
            "`Theory-QuestionsAndAnswerForTheExam-Part1` — the exam's own question bank WITH answers. Start here and do not stop until you can answer every item.",
            "`2023-24 TheoryQuestions for Part1 exam`.",
            "Theory lists by year: 2025-2026 (Part 2), 2024-2025, 2023-2024, 2022-2023, 2021-2022.",
            "`2023-24-SampleTest-Part1`, then `Calculus-part1-2025-SampleTest` with its solution.",
            "2024 tests: Feb 7th, Feb 21st, June 25th, July 17th.",
            "Timed and last: `2024-Sept4th-Test-Part1`, `2024-Sept26th-Test-Part1`, `Calculus-part1-2026-Feb-Tests`.",
        ],
        "Nothing in Part 1. Part 2 can be thin if Part 1 is solid.",
        "The published theory-question lists are the cheapest 15/30 available anywhere in your degree — the questions are given to you in advance, with answers. Part 1 is one hour.",
    ),
    "509486": (
        "Machine Learning, ANN and Deep Learning", "15 Sep", 28, 12,
        "The exam IS an upload: Colab notebook + PDF, submitted on the session date. Not a closed-book paper.",
        [
            "`Mock Exam`, then `Mock Exam 2` — both as timed dry runs.",
            "`Exam Session 16 June 2026` and `Exam Session 14 July 2026` — these are real 2026 papers.",
            "Build a reusable notebook: data loading, split, training loop, metrics, plots, numbered discussion sections.",
            "Install and test the environment the day before.",
        ],
        "Deep theory. This is an applied upload, not a viva.",
        "The instructions say to respect the assignment numbering exactly. Formatting is a genuine failure mode here — more people lose marks to a mis-numbered answer than to bad modelling. Twelve credits for 28 hours.",
    ),
    "509492": (
        "Theoretical and Quantum Physics for AI", "22 Sep", 30, 12,
        "Multiple choice per the archived mocks. Format NOT confirmed by the lecturers.",
        [
            "Do `Another mock exam` and `Yet another mock exam` FIRST, before any study. An hour tells you what kind of exam this is.",
            "Email Gherardi and Guarnieri: is it MCQ, and are the two modules one sitting?",
            "Then the two modules' lecture notes, targeted at the mock question types.",
        ],
        "Derivations, if the MCQ format holds. Recognition beats reproduction on a multiple-choice paper.",
        "Both archived mocks parse as bare-numbered multiple choice with four options, which corroborates your report — but two mocks are not the rules. If it turns out to be a written physics paper, 30 hours is wrong by 15 to 60. This is the largest single uncertainty in the plan.",
    ),
    "509488": (
        "Text Mining and Natural Language Processing", "24 Sep", 30, 6,
        "Up to 32 points, minimum 18. WRONG CLOSED ANSWERS SCORE -0.5.",
        [
            "`[TMNLP 22_23] Exam questions sample`.",
            "`[TMNLP 23_24] Exam questions sample` and `[TM-NLP 23_24] Exam questions sample`.",
            "`example of exam for linguistic part`.",
            "`[TMNLP-2025_2026] Practice Written Exam` — most recent. Timed, last.",
        ],
        "Nothing on language models or sequence models — 67% of the paper.",
        "The paper is out of 32 and you need 18. Answer every open question (no penalty). On closed items, answer only where you can eliminate two options; otherwise leave blank. You can afford roughly six blanks. The guess-everything tactic that works elsewhere loses marks here.",
    ),
    # --- January / February ------------------------------------------------
    "510109": (
        "Probability and Statistical Inference", "Jan/Feb", 52, 12,
        "Written in a computer lab, open + closed items. No gate beyond 18.",
        [
            "`Sample Exam (with solutions)` and `Examples of exam problems (with solutions)`.",
            "September papers first — closest to what you will sit: `Exam 27 Sep 2023` + solutions, `Exam 25 Sep 2024, Solutions 1-2`.",
            "Then chronologically with solutions: Jan 2023 through Feb 2025 — twelve solved sittings.",
            "Timed mocks, unsolved, last: `Exam 20 Jan 2026 (text)`, `Exam 5 Feb 2026 (text)`.",
            "Inference block: the hypothesis-testing notes and `Hypothesis testing (solution)`.",
        ],
        "`Solution of Exercise 2, Session July 15, 2022 (exam for mathematicians)` — a different exam entirely.",
        "The deepest archive you have: 47 documents, 20 published answer keys. Four topics cover 73% of the marks. This is why it is in January — months of drilling convert reliably into a pass here.",
    ),
    "509478": (
        "Knowledge Representation and Reasoning", "Jan/Feb", 44, 12,
        "Two modules; the final mark is the MEAN of the two.",
        [
            "Module 2 first — it has a solved mock for every year: 2023, 2024, 2025, 2026 Mock Test, plus June and July 2022 with solutions.",
            "Module 1: `Mock Exam 2021` + solutions, `Mock Exam January 2022`, `Mock Exam 2022-2023`.",
            "Module 1 sittings: 2022/02/07 (with solutions), 2022/07/11, 2022/09/30, 2023/02/06, 2023/07/10 (with solutions).",
        ],
        "Nothing outside description logic and RDF/SPARQL until those two are solid — they are 65% of the marks.",
        "The mean lets a strong module carry a weak one. Push module 2 to about 22/30 and module 1 only needs 14. Check whether the bonus-exercise scheme still runs — past editions gave up to 2 points for bringing solutions on the day.",
    ),
    "504464": (
        "Organization Theory and Design", "Jan/Feb", 45, 6,
        "8 Learning Tests x 30 MCQ = 240 questions in one ~3h20 sitting. +1 correct, -1 wrong, 0 blank. Final mark = AVERAGE of the 8 sections.",
        [
            "Read the `EXAM` resource on Kiro — it carries the rules and the per-test example questions.",
            "Daft chapters 1-13, one chapter at a time, to recognition level only.",
            "Drill the example questions per Learning Test.",
        ],
        "Nothing. Because the final is the average of eight sections, a chapter you skip drags the whole mark down and cannot be dropped.",
        "To average 18/30 you need net +18 in every section: about 22 right, 4 wrong, 4 blank. That is ~73% net accuracy across 240 questions. A random guess on four options has expected value -0.5, so answer only when you can eliminate two. This is the hardest six credits in your degree and it needs months, not a crammed week.",
    ),
    "510638": (
        "Web and Social Media Search and Analysis", "Jan/Feb", 38, 6,
        "Project + presentation + written. Mark split UNVERIFIED.",
        [
            "Email Viviani for the winter project deadline and the mark split.",
            "Reuse the Information Retrieval codebase.",
            "Submit at least 7 days before the written — that is the stated rule.",
        ],
        "Building anything from scratch.",
        "Deferred out of September because its project deadline falls ~7 days before the written, which was already upon you, and because it is the worst credits-per-hour on the list.",
    ),
    "509483": (
        "Computational Logic", "Jan/Feb", 30, 6,
        "Written exam assignments. Structure never published — ask Ghilardi.",
        [
            "The `Exam_Assignments` folder: each sitting is a PDF of the questions with the SMT-LIB encodings that answer it.",
            "Take the most recent sittings first, PDF and .smt2 side by side.",
            "Install z3 and RUN every encoding. Reading them is not the same as writing them.",
            "Then work backwards through the earlier years.",
        ],
        "Nothing outside propositional SAT and SMT encoding until both are fluent.",
        "Lowest effort rating in the degree. If Ghilardi confirms the assignments are take-home, this drops to about 15 hours.",
    ),
    "509487": (
        "Fuzzy Systems and Evolutionary Computing", "Jan/Feb", 27, 6,
        "Written + lab component.",
        [
            "`Fuzzy Evo Questions and Exercises` — the question bank.",
            "`Example of answer to the open questions` — study the style the examiner wants, not just the content.",
            "`Text of the exam - June 2023`, `Text of the exam - July 2023`.",
            "`Exams 2022/23` and `Exams 2023/24` folders.",
            "`Exam example 5.6.2025`, then `Exam 2026-01`.",
            "Lab: `Lab - Exam Exercise Samples` with `Lab - Exam Sample Solutions`.",
        ],
        "The optional project. It adds up to 4 points on top of an 18 you already have — you want the exam finished, not decorated.",
        "Questions recur near-verbatim with published model answers.",
    ),
    "509493": (
        "Statistical Modelling", "Jan/Feb", 22, 6,
        "Written, closed book, 2-3 exercises. Calculator allowed, quantiles provided.",
        [
            "The exercise sets first — they are organised by topic and build the machinery.",
            "Then `Esame1` through `Esame6`, timed, in order.",
            "Priority: regression inference (t and F tests, confidence intervals), then diagnostics (residuals, leverage, influence), then GLM.",
        ],
        "Nothing outside inference and diagnostics until those are solid — 65% of the items.",
        "None of this is on Kiro. It is all on laura-dangelo.github.io, now archived locally — 48 PDFs including six full past exams and the complete lecture notes.",
    ),
    "509498": (
        "AI for Communication and Marketing", "Jan/Feb", 16, 6,
        "Compulsory lab project (gates admission) + written MCQ. BOTH 2026 LAB WINDOWS ARE CLOSED.",
        [
            "Email Suriano. Nothing else matters until a lab window exists.",
            "Read `Lab exam assignment - 2026 Summer session` now, so you can deliver inside a short window if one opens.",
            "Drill the 85-question solved MCQ bank — six topics cover 61%.",
        ],
        "Nothing; the written half is small.",
        "Sixteen hours if the lab reopens, impossible if it does not. The email is the whole course.",
    ),
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    for code, (name, when, hours, cfu, gate, steps, skip, tactic) in PACKS.items():
        bank_path = DRILL / f"{code}.json"
        bank = json.loads(bank_path.read_text()) if bank_path.exists() else None

        lines = [
            f"# {name}",
            "",
            f"**{when}** · {cfu} CFU · budget **{hours} h**",
            "",
            f"## Pass gate",
            "",
            gate,
            "",
            "## Do it in this order",
            "",
        ]
        lines += [f"{i}. {s}" for i, s in enumerate(steps, start=1)]
        lines += ["", "## Skip", "", skip, "", "## Tactic for 18", "", tactic, ""]

        if bank and bank["n_papers"]:
            recurring = [q for q in bank["question_types"] if q["seen_in_papers"] >= 2]
            lines += [
                "## What the archive says",
                "",
                f"- **{bank['n_papers']} papers**, {bank['n_items']} questions extracted",
                f"- **{len(bank['solution_keys'])} published answer keys**",
                f"- **{len(recurring)} question types appear in two or more papers**",
                "",
            ]
            if recurring:
                lines += ["| Seen in | Topic | Typical marks | Solution published in |", "|---|---|---|---|"]
                for q in recurring[:12]:
                    lines.append(
                        f"| {q['seen_in_papers']} papers ({q['share_of_papers']:.0%}) | "
                        f"{q['topic']} | {q['typical_marks'] or '—'} | "
                        f"{q['solution_key'] or '—'} |"
                    )
                lines.append("")
            lines.append(f"Full list with the question text: `reference/predicted/{code}.md`")
            lines.append("")
        else:
            lines += [
                "## What the archive says",
                "",
                "**No past papers are archived for this course.** Nothing here is drillable; "
                "the steps above are the whole method.",
                "",
            ]

        (OUT / f"{code}.md").write_text("\n".join(lines) + "\n")
        written += 1

    index = [
        "# Study packs",
        "",
        "One per exam. Gate, ordered file list, what to skip, and how to reach 18.",
        "",
        "## September",
        "",
    ]
    for code, v in PACKS.items():
        if v[1] != "Jan/Feb":
            index.append(f"- [{v[0]}]({code}.md) — {v[1]}, {v[3]} CFU, {v[2]} h")
    index += ["", "## January / February", ""]
    for code, v in PACKS.items():
        if v[1] == "Jan/Feb":
            index.append(f"- [{v[0]}]({code}.md) — {v[3]} CFU, {v[2]} h")
    (OUT / "README.md").write_text("\n".join(index) + "\n")

    print(f"wrote {written} packs to {OUT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
