#!/usr/bin/env python3
"""Build the study cockpit, in two shapes from one codebase.

  data/bundle/index.html   the full thing: reads the rendered exam pages from
                           pages/ beside it, so papers are shown as the actual
                           pages rather than as mangled extracted text
  data/cockpit.html        standalone single file, no page images, small enough
                           to keep on a phone

Same markup and behaviour in both; the page viewer simply has nothing to show in
the standalone build and falls back to the extracted text.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app_template import TEMPLATE  # noqa: E402

BUNDLE = Path("data/bundle")
STANDALONE = Path("data/cockpit.html")
ZIPPED = Path("data/study-bundle.zip")

EXAMS = [
    ("509496", "Information Retrieval & RecSys", "2026-08-31", "Pavia", 30, 6,
     "Written exam AND a project with presentation. Two past papers exist, both with full model answers.", "2026-08-26"),
    ("509521", "Laboratory of Machine Learning", "2026-09-01", "Pavia", 25, 3,
     "Nine report submissions — the reports are the grade. Check the windows are still open.", "2026-08-27"),
    ("509519", "Ethics, Law and AI", "2026-09-02", "Pavia", 28, 12,
     "Multiple choice, single unsplit exam. No gate beyond 18. Nothing is archived for this course.", "2026-08-28"),
    ("509494", "Brain Modelling", "2026-09-03", "Pavia", 26, 6,
     "Coding project 30% + written 70%. The written is 6–8 open questions with marks in brackets. The project mark carries to later sessions.", "2026-08-29"),
    ("509495", "Data Mining", "2026-09-04", "Pavia", 19, 6,
     "Assignments (12/30) were set during delivery and cannot be recovered — you sit for the full 30.", "2026-08-30"),
    ("509485", "Cognitive Psychology", "2026-09-08", "Bicocca", 27, 6,
     "Written 25 pts + COMPULSORY ORAL 6 pts. Edition 7392 binds: threshold 12, marks summed. Do not contact Bricolo.", "2026-09-03"),
    ("509477", "Computer Programming", "2026-09-09", "Statale", 44, 12,
     "TWO GATES: theory ≥12/20 AND code ≥6/10. Non-running code is an automatic fail.", "2026-09-04"),
    ("509481", "Calculus", "2026-09-11", "Pavia", 44, 12,
     "Part 1 ≥15/30 on top of the overall 18. Closed book. No Part 1/Part 2 split exists in autumn 2026.", "2026-09-06"),
    ("509486", "Machine Learning / ANN / DL", "2026-09-15", "Pavia", 28, 12,
     "The exam IS an upload: Colab notebook + PDF, on the day. Respect the assignment numbering exactly.", "2026-09-10"),
    ("509492", "Theoretical & Quantum Physics", "2026-09-22", "Statale", 30, 12,
     "Module 1 is multiple choice. MODULE 2 IS NOT — short computational questions. Treat 30 h as a floor.", "2026-09-17"),
    ("509488", "Text Mining and NLP", "2026-09-24", "Pavia", 30, 6,
     "THREE PARTS, up to 32 points. WRONG CLOSED ANSWERS SCORE −0.5 — leave them blank unless you can eliminate two options.", "2026-09-19"),
]

WINTER = [
    ("510109", "Probability and Statistical Inference", 52, 12,
     "The deepest archive you have: 27 published answer keys, 178 questions."),
    ("509478", "Knowledge Representation and Reasoning", 44, 12,
     "Final mark is the MEAN of the two modules; a strong module carries a weak one."),
    ("504464", "Organization Theory and Design", 45, 6,
     "8 tests × 30 MCQ in one sitting, +1/−1/0. To average 18 you need net +18 per section: ~22 right, 4 wrong, 4 blank."),
    ("510638", "Web and Social Media Search and Analysis", 38, 6,
     "Project + presentation + written. One past paper recovered — half the marks are hand computations on a small graph."),
    ("509483", "Computational Logic", 30, 6,
     "293 published answer keys — the SMT-LIB encodings. Install z3 and run them."),
    ("509487", "Fuzzy Systems and Evolutionary Computing", 27, 6,
     "Questions recur with published model answers. Skip the optional project."),
    ("509493", "Statistical Modelling", 22, 6,
     "12 papers and 4 answer keys. The lecture notes were image-only and are now OCR'd."),
    ("509498", "AI for Communication and Marketing", 16, 6,
     "85 solved MCQs cover the written half. Blocked until a lab window opens."),
]


def load_json(path: str, default):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else default


def load_packs() -> dict[str, str]:
    return {
        p.stem: p.read_text()
        for p in Path("reference/packs").glob("*.md")
        if p.stem != "README"
    }


def build_drill(library: dict) -> tuple[dict, dict, dict]:
    """Drill cards, timed papers and topic frequency, all from the full question set.

    The old drill bank held 161 clustered "question types" while the library
    held 988 questions and 365 answer keys, so the best material - every solved
    Computational Logic sitting, every Probability paper with its worked
    solutions - was unreachable from the place you actually revise. Cards are
    now built from the questions themselves and reference them by index, so
    nothing is duplicated into the payload.

    Recurrence is carried across from the clustered bank where a question
    matches one, because "this appears in 25 of 28 papers" is the single most
    useful thing to sort by.
    """
    recurrence: dict[str, dict[str, tuple[int, float, str]]] = {}
    for path in sorted(Path("data/drill").glob("*.json")):
        bank = json.loads(path.read_text())
        for group in bank["question_types"]:
            key = " ".join(group["statement"].split())[:140]
            recurrence.setdefault(path.stem, {})[key] = (
                group["seen_in_papers"], group["share_of_papers"], group["solution_key"] or ""
            )

    drill: dict[str, list] = {}
    papers: dict[str, list] = {}
    topics: dict[str, list] = {}

    for code, course in library.items():
        questions = course["questions"]
        if not questions:
            continue

        cards = []
        for index, question in enumerate(questions):
            key = " ".join(question["text"].split())[:140]
            seen, share, _ = recurrence.get(code, {}).get(key, (1, 0.0, ""))
            cards.append({
                "q": index,
                "seen": seen,
                "share": round(share, 3),
                "keyed": bool(question.get("answer")),
            })
        # Most-recurring first, then answered ones ahead of unanswered: a card
        # you cannot check is worth less than one you can.
        cards.sort(key=lambda c: (-c["seen"], not c["keyed"]))
        drill[code] = cards

        by_paper: dict[str, list[int]] = {}
        for index, question in enumerate(questions):
            by_paper.setdefault(question["paper"], []).append(index)
        docs = {d["name"]: d["i"] for d in course["documents"]}
        papers[code] = [
            {"name": name, "doc": docs.get(name), "qs": qs,
             "keyed": sum(1 for i in qs if questions[i].get("answer"))}
            for name, qs in by_paper.items()
            if len(qs) >= 2
        ]
        papers[code].sort(key=lambda p: -len(p["qs"]))

        counts: dict[str, int] = {}
        keyed: dict[str, int] = {}
        for question in questions:
            topic = question["topic"]
            counts[topic] = counts.get(topic, 0) + 1
            if question.get("answer"):
                keyed[topic] = keyed.get(topic, 0) + 1
        total = sum(counts.values())
        topics[code] = sorted(
            (
                {"topic": t, "n": n, "share": round(n / total, 3), "keyed": keyed.get(t, 0)}
                for t, n in counts.items()
            ),
            key=lambda t: -t["n"],
        )

    return drill, papers, topics


# The specific ways each paper takes marks off you. Verbatim on the exam card,
# because these are the facts that are expensive to remember wrongly.
TRAPS = {
    "509488": [
        "Wrong closed answers score −0.5. Leave one blank unless you can eliminate two options.",
        "Answer every open question — no penalty there.",
        "Three parts (PART 1/2/3 OF 3) and lettered tracks. Check which track you were given.",
        "Paper is out of 32; you need 18. You can afford roughly six blanks.",
    ],
    "509477": [
        "TWO independent gates: theory ≥12/20 AND code ≥6/10. Passing one does not carry the other.",
        "Non-running code is an automatic fail. Run every function before you submit.",
        "The theory gate is what fails people, not the code. AVL rotations recur in every paper.",
    ],
    "509481": [
        "Part 1 needs ≥15/30 on top of the overall 18.",
        "Closed book. Part 1 is one hour.",
        "No Part 1 / Part 2 split exists in autumn 2026 — one combined sitting.",
        "The published theory-question list is the exam's own bank, with answers.",
    ],
    "509485": [
        "Compulsory ORAL as well as the written — both are mandatory.",
        "Edition 7392 binds: written threshold 12, and the final mark is the SUM.",
        "Do NOT contact Bricolo about the syllabus — silence keeps you on the lower threshold.",
        "Bicocca, not Pavia.",
    ],
    "509486": [
        "The exam IS an upload: Colab notebook + PDF, submitted on the day.",
        "Respect the assignment numbering exactly — marks are lost to formatting.",
        "Test the environment the day before.",
    ],
    "509492": [
        "Module 1 is multiple choice; MODULE 2 IS NOT — short computational questions.",
        "Expect: expectation values under time evolution, reduced density matrices, purity, commutators.",
        "Statale, not Pavia.",
        "30 h is a floor, not an estimate — the format is still unconfirmed by the lecturers.",
    ],
    "509496": [
        "There IS a written exam as well as the project — I had this wrong until the January papers turned up.",
        "Both past papers come with full model answers.",
        "The autumn presentation slot is unconfirmed. Chase Peikos.",
    ],
    "509494": [
        "Coding project is 30% and its mark CARRIES to later sessions of the same year.",
        "Written is 6–8 open questions with marks in brackets.",
        "Nernst reversal potential and a membrane capacitance/resistance calculation open almost every paper.",
    ],
    "509495": [
        "The 12/30 of assignments were set during delivery and cannot be recovered — you sit for the full 30.",
        "Novelty 0.54: half of each paper is genuinely new. Past papers give format, not answers.",
    ],
    "509519": [
        "Multiple choice, single unsplit exam, no gate beyond 18.",
        "Nothing is archived for this course. The non-attending reading list is the exam.",
    ],
    "509521": [
        "Nine report submissions ARE the grade — there is no exam.",
        "Check the submission windows are still open; closed windows killed AI Marketing.",
    ],
    "504464": [
        "8 tests × 30 MCQ in one ~3h20 sitting, +1 correct / −1 wrong / 0 blank.",
        "Final mark is the AVERAGE of the 8 sections — you cannot drop your worst.",
        "You need net +18 per section: about 22 right, 4 wrong, 4 blank.",
        "A random guess on four options has expected value −0.5. Answer only when two are eliminated.",
    ],
}


def drop_scenarios() -> dict:
    """What deferring each September exam to winter would actually free.

    Computed by re-running the real scheduler without that course, not
    estimated: 331 h in 52 days with five exams in five days has no slack, and
    a guess about what dropping one buys you is worth nothing.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("sched", "scripts/build_calendar.py")
    sched = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sched)

    full = [c for c in sched.PLAN]
    out: dict[str, dict] = {}
    for dropped, *_ in full:
        subset = [c for c in full if c[0] != dropped]
        try:
            result = sched.plan_for(subset)
        except AssertionError as exc:  # noqa: PERF203 - report, do not hide
            out[dropped] = {"feasible": False, "why": str(exc)[:160]}
            continue
        out[dropped] = {
            "feasible": True,
            "freed_hours": round(sched.HOURS[dropped], 1),
            "freed_cfu": sched.CFU[dropped],
            "worst_gap": result["worst_gap"],
            "overrun_days": result["overrun_days"],
            "peak_day": result["peak_day"],
            "slack": result["slack"],
        }
    baseline = sched.plan_for(full)
    out["_current"] = {
        "feasible": True, "freed_hours": 0, "freed_cfu": 0,
        "worst_gap": baseline["worst_gap"], "overrun_days": baseline["overrun_days"],
        "peak_day": baseline["peak_day"], "slack": baseline["slack"],
    }
    return out


def build_payload(pages: dict, pages_dir: str) -> str:
    library = load_json("data/library.json", {"courses": {}, "quiz_banks": {}})
    calendar = load_json("data/audit/calendar.json", {"days": {}})

    names = {c: v["name"].title() for c, v in library["courses"].items()}
    for code, name, *_ in EXAMS:
        names[code] = name
    for code, name, *_ in WINTER:
        names.setdefault(code, name)

    drill, papers, topics = build_drill(library["courses"])
    docs = sum(len(c["documents"]) for c in library["courses"].values())
    questions = sum(len(c["questions"]) for c in library["courses"].values())
    keys = sum(
        sum(1 for d in c["documents"] if d["role"] == "solution")
        for c in library["courses"].values()
    )

    data = {
        "built": dt.date.today().isoformat(),
        "stats": f"{docs} docs · {questions} questions · {keys} keys"
                 + (f" · {sum(len(v) for v in pages.values())} pages" if pages else ""),
        "names": names,
        "calendar": calendar.get("days", {}),
        "packs": load_packs(),
        "exams": [
            {"code": c, "name": n, "date": d, "campus": camp,
             "hours": h, "cfu": cfu, "gate": g, "book_by": b}
            for c, n, d, camp, h, cfu, g, b in EXAMS
        ],
        "winter": [
            {"code": c, "name": n, "hours": h, "cfu": cfu, "note": note}
            for c, n, h, cfu, note in WINTER
        ],
        "drill": drill,
        "papers": papers,
        "topics": topics,
        "scenarios": drop_scenarios(),
        "traps": TRAPS,
        "lib": library["courses"],
        "quiz": library["quiz_banks"],
        "pages": pages,
        "pagesDir": pages_dir,
    }
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def main() -> int:
    pages = load_json("data/bundle/pages_index.json", {})

    BUNDLE.mkdir(parents=True, exist_ok=True)
    (BUNDLE / "index.html").write_text(TEMPLATE.replace("__DATA__", build_payload(pages, "pages/")))
    STANDALONE.write_text(TEMPLATE.replace("__DATA__", build_payload({}, "")))

    page_dir = BUNDLE / "pages"
    n_pages = len(list(page_dir.glob("*.webp"))) if page_dir.exists() else 0

    if ZIPPED.exists():
        ZIPPED.unlink()
    readme = (
        "STUDY BUNDLE\n"
        "============\n\n"
        "Unzip anywhere, then open  index.html  in any browser.\n"
        "Everything works offline. Nothing is uploaded.\n\n"
        "SECTIONS\n"
        "  Today    countdown with campus, the day's plan split into new material\n"
        "           and spaced review, a Start-now button, weakest topics, and a\n"
        "           booking banner that turns red inside 48 hours\n"
        "  Courses  per exam: Method, Papers, Drill, Topics, Questions, Files\n"
        "  Drill    spaced repetition over every question, ordered by what is due\n"
        "           and by how often it recurs. Grade Again / Hard / Good / Easy\n"
        "  Quiz     the 85 solved multiple-choice questions, scored\n"
        "  Plan     eight-week heatmap, every sitting and booking window\n"
        "  Cards    one printable page per exam: gate, campus, scoring traps.\n"
        "           Ctrl+P gives one A4 page per exam\n"
        "  More     hours logged vs planned, re-flow, defer-an-exam simulator,\n"
        "           daily digest, and progress export/import\n\n"
        "KEYS\n"
        "  Ctrl+K or /   command palette - jump to any course, paper or topic\n"
        "  arrows        page through a paper when the viewer is open\n"
        "  Esc           close\n\n"
        "PAPERS\n"
        "  Click any page to open it full size. Zoom enlarges, swipe pages on a\n"
        "  phone, and 'Sit this paper timed' hides the answers and starts a clock.\n\n"
        "PROGRESS\n"
        "  Grading, quiz answers, ticked days and logged hours live in this\n"
        "  browser's localStorage. That is one device and one browser: use\n"
        "  More > Export regularly. Import merges a backup back in.\n\n"
        "The pages/ folder holds the rendered exam pages. Keep it beside\n"
        "index.html or the paper viewer will have nothing to show.\n"
    )
    with zipfile.ZipFile(ZIPPED, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        bundle.writestr("study/README.txt", readme)
        bundle.write(BUNDLE / "index.html", "study/index.html")
        for image in sorted(page_dir.glob("*.webp")):
            bundle.write(image, f"study/pages/{image.name}")

    print(
        f"bundle  {BUNDLE/'index.html'} "
        f"({(BUNDLE/'index.html').stat().st_size/1e6:.1f} MB) + {n_pages} page images\n"
        f"zip     {ZIPPED} ({ZIPPED.stat().st_size/1e6:.0f} MB)\n"
        f"phone   {STANDALONE} ({STANDALONE.stat().st_size/1e6:.1f} MB)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
