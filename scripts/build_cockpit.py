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


def load_drill() -> dict:
    banks = {}
    for path in sorted(Path("data/drill").glob("*.json")):
        bank = json.loads(path.read_text())
        cards = [
            {"topic": q["topic"], "seen": q["seen_in_papers"], "share": q["share_of_papers"],
             "marks": q["typical_marks"], "key": q["solution_key"],
             "text": q["statement"][:1400], "papers": q["papers"][:4]}
            for q in bank["question_types"] if q["seen_in_papers"] >= 2
        ]
        if cards:
            banks[path.stem] = {"name": bank.get("name", path.stem).title(), "cards": cards}
    return banks


def build_payload(pages: dict, pages_dir: str) -> str:
    library = load_json("data/library.json", {"courses": {}, "quiz_banks": {}})
    calendar = load_json("data/audit/calendar.json", {"days": {}})

    names = {c: v["name"].title() for c, v in library["courses"].items()}
    for code, name, *_ in EXAMS:
        names[code] = name
    for code, name, *_ in WINTER:
        names.setdefault(code, name)

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
        "drill": load_drill(),
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
        "Everything works offline. Nothing is uploaded. Progress (drilled cards,\n"
        "quiz answers, ticked days) is stored in the browser on that device, so use\n"
        "the same browser to keep it.\n\n"
        "  Today    countdown, the day's plan, booking deadlines closing soon\n"
        "  Courses  one page per exam: Method, Papers, Questions, Files\n"
        "  Drill    recurring question types, most frequent first\n"
        "  Quiz     the 85 solved multiple-choice questions, scored\n"
        "  Plan     every sitting, booking window and the full calendar\n"
        "  Search   press / anywhere\n\n"
        "In Papers, click any page to open it full size. Arrow keys move between\n"
        "pages, Zoom enlarges, Esc closes.\n\n"
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
