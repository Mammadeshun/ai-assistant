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
        "Written exam AND a project with presentation. CORRECTION: I previously told you "
        "this was project-only with no written paper. That was wrong, and the evidence was "
        "already in my own data — the project instructions say the presentations happen "
        "'after the written exam'. Two past written papers now confirm it.",
        [
            "`IR past exam January 2025` and `IR past exam January 2026` — both come WITH full model answers. Work them first; they are the only two written papers in existence for this course.",
            "From those papers the written half is: the standard IR pipeline diagram (offline vs online), extending it to Neural IR with bi- and cross-encoders, offline evaluation and the Cranfield paradigm, benchmark collections, and choosing an evaluation measure with justification.",
            "Read `Project Instructions 2026 June - July` — build to the spec, not to your own taste.",
            "Email Peikos about an autumn presentation slot. Every slot in the forums is February, June or July.",
            "Build IR (index, retrieval, query expansion) and RecSys on one codebase; ten-minute deck.",
        ],
        "Do not start a second codebase for Web & Social — it is the same machinery.",
        "The two papers are answered in full, so this went from the least-covered exam on your "
        "calendar to one with model answers overnight. Budget more of the 30 hours to the "
        "written half than I originally implied.",
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
        "Coding project 30% + written 70%. The written is 8 open questions (6 in 2026, with "
        "marks in brackets summing to 32).",
        [
            "Work the seven recovered papers in reverse date order: 18 June 2026, 29 January 2025, 11 Sept 2024, 10 July 2024, 20 June 2024, 1 March 2024, 12 February 2024.",
            "The recurring spine, present in nearly every sitting: Nernst equation and reversal potentials · membrane capacitance/resistance numeric problems · encoding from dynamic stimuli to firing rates · entropy and mutual information of neural responses · Integrate-and-Fire and Leaky IF (including spike-rate adaptation and refractoriness) · Hodgkin-Huxley and gating variables · ion-channel state diagrams · synaptic conductance and release probability · STDP and Hebbian plasticity · FitzHugh-Nagumo · mean-field and whole-brain modelling.",
            "Learn to actually compute two things — they open the paper almost every time: the Nernst reversal potential given RT/F, and a membrane capacitance or resistance problem.",
            "Email Casellato for the project-topics document and confirm the 30/70 split still holds.",
            "Do the project. Its mark carries across every session of the same academic year — it is the only work here that cannot be wasted.",
        ],
        "Coding in the written part — the project exists precisely so the written has none.",
        "This course went from zero archived material to seven past papers, and they repeat "
        "heavily: the same twelve topics rotate through eight slots. That makes it one of the "
        "more predictable exams you have, not one of the blindest.",
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
            "`Cognitive Psychology - chapter quizzes with answers` — real chapter-quiz questions WITH the answers, recovered from the course group. Start here.",
            "`Cognitive Psychology - Esercizi chapter exercises` — multiple-choice exercises by chapter, with options.",
            "`Cognitive Psychology - full Q&A revision notes` — fourteen pages in question-and-answer form, which is exactly the shape of the written paper.",
            "`Oral exam topics` (PDF) is the oral question bank. Prepare a six-to-eight minute answer for every item.",
            "Read the research papers behind the `Questions on research paper` activities (STM, LTM, TPS, Language). The oral draws on them.",
        ],
        "The attendance bonus — it needed in-class presence and is not available to you.",
        "DO NOT email Bricolo about the syllabus. Silence keeps you on edition 7392, threshold 12 rather than 13. Asking costs you a mark. "
        "Correction to an earlier report: this course does NOT have 31 past papers on Kiro. Those were 31 Moodle quiz landing pages — "
        "opening times and 'only 1 attempt available', no questions. The quizzes were single-attempt and closed in 2024/25, "
        "so their content was never archivable from Kiro. What the course group supplied fills exactly that hole: the chapter "
        "quizzes, their answers, and a full Q&A revision set.",
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
            "Twenty real sittings are now archived, 2023 to 2026. Work backwards: Feb 2026, Jan 2026, 18 Sept 2025, 2 Sept 2025, 15 July 2025, 19 June 2025, 19 Feb 2025, 27 Jan 2025, then the four 2024 and four 2023 papers.",
            "Sit the three September papers under time before anything else — 19 Sept 2023, 3 Sept 2024, 17 Sept 2024, 2 Sept 2025, 18 Sept 2025. Your exam is 15 September.",
            "Every paper has the same shape: 'We are given a dataset containing N ... ' then design a model, justify the architecture, and analyse. Images, text reviews, graphs and tabular data all recur as the dataset type.",
            "Note the 2025 and 2026 papers are labelled 'Part 2' — check whether a Part 1 exists and whether it binds for you.",
            "`Mock Exam` and `Mock Exam 2` from Kiro as final dry runs.",
            "Build a reusable notebook: data loading, split, training loop, metrics, plots, numbered discussion sections. Test the environment the day before.",
        ],
        "Deep theory. This is an applied upload, not a viva.",
        "The instructions say to respect the assignment numbering exactly. Formatting is a genuine failure mode here — more people lose marks to a mis-numbered answer than to bad modelling. Twelve credits for 28 hours.",
    ),
    "509492": (
        "Theoretical and Quantum Physics for AI", "22 Sep", 30, 12,
        "Module 1 mocks are multiple choice. MODULE 2 IS NOT — it is short computational "
        "questions. Revise the budget upward: 30 h was costed on the assumption this was an "
        "Ethics-style MCQ paper throughout, and it is not.",
        [
            "Read `Quantum module 2 - recalled exam questions with answers` FIRST — a classmate's recall of ten module-2 questions with the expected answers. It is the only evidence of what module 2 actually asks.",
            "Module 2 topics, straight from that recall: time evolution and expectation values (compute <Z> on |psi(t)>), information capacity (log2 of the state-space dimension), commutators and shared eigenbases, reduced density matrices, purity of a density matrix, Bloch vectors, wave-function normalisation, the uncertainty relation, and finding a state with a certain measurement outcome with probability 1.",
            "Then `Another mock exam` and `Yet another mock exam` for module 1 — those are genuinely multiple choice, on dimensional analysis and the Rayleigh method.",
            "Email Gherardi and Guarnieri: are the two modules examined in one sitting?",
        ],
        "Long derivations. Every recalled question is a short calculation with a numeric or one-line answer.",
        "CORRECTION: I told you this was multiple choice on your verbal report, and the two "
        "archived mocks (module 1) supported it. The module-2 recall shows five of ten "
        "questions need real computation — density matrices, purity, expectation values under "
        "time evolution — and only three are recognition items. Treat 30 h as a floor, not an "
        "estimate, and confirm with the lecturers before you rely on it.",
    ),
    "509488": (
        "Text Mining and Natural Language Processing", "24 Sep", 30, 6,
        "Up to 32 points, minimum 18. WRONG CLOSED ANSWERS SCORE -0.5. The paper comes in "
        "THREE PARTS (the recovered 2024 papers are labelled 'PART 1 OF 3' and 'PART 3 OF 3') "
        "and there are lettered tracks — one photo shows 'Track 2.A'.",
        [
            "`TEXT MINING OPEN QUESTIONS - ANSWERS 2022-2023` FIRST. This is the only worked answer key the course has, and until now I had none.",
            "The three-part structure, from the recovered papers: Part 1 is linguistics (morphology, arguments vs adjuncts, derivational vs inflectional suffixes), Part 2 is true/false with brief justification plus closed questions, Part 3 is long open questions (attention and Transformers, contextualised embeddings/ELMo/BERT, PPMI).",
            "`[TMNLP 22_23]`, `[TMNLP 23_24]` and `[TM-NLP 23_24] Exam questions sample`.",
            "The recovered photographs: PART 1 and PART 3 of 28/06/2024, the 30/06/2023 paper, the TF-IDF exercise and the embeddings matching exercise.",
            "`[TMNLP-2025_2026] Practice Written Exam` — most recent, and it is PART 2 OF 3. Timed, last.",
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
        "Project + presentation + written. The written is now confirmed: Viviani, four "
        "questions carrying [3], [4], [5] and [3] points on page one.",
        [
            "`Web and Social Networks Search and Analysis - written exam 16 June 2025` — the only past paper, recovered from a photograph.",
            "From it, the written syllabus is concrete: complex vs regular vs random networks; maximal cliques; local clustering coefficient; average degree via the Handshaking Lemma; delta centrality; Web 1.0 vs Web 2.0; bridges and articulation points; incidence matrices; betweenness centrality; assortativity.",
            "Half the marks are hand computations on a small given graph. Practise those on paper, not in code.",
            "Email Viviani for the winter project deadline and the mark split.",
            "Reuse the Information Retrieval codebase; submit at least 7 days before the written.",
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
