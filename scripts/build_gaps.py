#!/usr/bin/env python3
"""What is missing, ranked by what it would change.

Generated from the library rather than written by hand, so the counts are the
real ones. Each entry says what to ask for and what having it would buy — a
request list is only useful if it distinguishes 'this unblocks an exam' from
'this would be nice'.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = Path("reference/ASK_THE_GROUP.md")

# code: (when, hours, what to ask for, what it buys)
ASKS = {
    "509519": ("02 Sep", 28,
        "**Any past Ethics MCQ paper, and the current non-attending reading list.** "
        "Still nothing at all archived — zero papers, zero questions. This is now the "
        "ONLY September exam with no material whatsoever.",
        "12 CFU for 28 h is the best rate in the plan and it is the last blind spot left. "
        "One recalled paper is worth more here than anywhere else."),
    "504464": ("Jan/Feb", 45,
        "**The per-Learning-Test example questions**, and anyone's recollection of the "
        "240-question sitting.",
        "One document archived, one question extracted. You need ~73% net accuracy across "
        "240 MCQs with -1 marking and there is almost nothing to drill."),
    "509521": ("01 Sep", 25,
        "**The nine lab assignment briefs**, and whether anyone has submitted in an "
        "autumn session.",
        "Still only a stub page. If the submission windows are closed the course cannot be "
        "sat, which changes September by 25 hours."),
    "509498": ("Jan/Feb", 16,
        "**Whether anyone has an open autumn lab window**, and a copy of a submitted lab "
        "project.",
        "The written half is solved by your own 85-question bank. The lab gate is the "
        "entire blocker and no group material touched it."),
    "509495": ("04 Sep", 19,
        "**The assignment texts set during delivery**, and any solved mockup.",
        "Three papers, still zero answer keys. Novelty 0.54, so worked solutions matter "
        "more here than past papers do."),
    "509492": ("22 Sep", 30,
        "**A real module-1 paper, and confirmation of whether the two modules are one "
        "sitting.** The module-2 recall you supplied resolved the format question.",
        "PARTLY RESOLVED. The recalled module-2 paper shows short computational questions, "
        "not multiple choice — see the correction in the study pack. Module 1 still rests "
        "on two mocks."),
    "509485": ("08 Sep", 27,
        "**Anyone's recollection of the written paper's 20 open questions**, and the oral "
        "questions they were actually asked.",
        "MOSTLY RESOLVED: the chapter quizzes, their answers and a full Q&A revision set "
        "arrived from the group, taking this from 2 questions to 26. The written open "
        "section and the oral are still unseen."),
    "509477": ("09 Sep", 44,
        "**Any paper after 2023** — the archive still stops at July 2023.",
        "Six papers, 17 keys, all 2022-2023. Three years stale on an exam with two "
        "independent pass gates."),
    "509481": ("11 Sep", 44,
        "**Part 2 tests and their solutions**, and Part 1 tests from 2025 and 2026.",
        "21 papers but only 4 answer keys, and the archive thins out after the 2024 sittings."),
    "509496": ("31 Aug", 30,
        "**A past project report and slide deck**, and whether anyone has presented in an "
        "autumn session.",
        "RESOLVED for the written half — the two January papers you supplied come with full "
        "model answers, and they proved a written exam exists at all. The project side is "
        "still unseen."),
    "509494": ("03 Sep", 26,
        "**The project-topics document** (it lives on a course Google Drive, not Kiro).",
        "RESOLVED for the written half — seven past papers arrived, from zero. The project "
        "is 30% of the mark, carries across sessions, and its topic list is still missing."),
    "509486": ("15 Sep", 28,
        "**Solved notebooks for any recent paper**, and whether a 'Part 1' exists alongside "
        "the 'Part 2' the 2025-26 papers are labelled with.",
        "RESOLVED for coverage — 20 sittings from 2023 to 2026, and the top question type "
        "appears in 15 of them. Still zero worked solutions."),
    "509488": ("24 Sep", 30,
        "**Part 2 papers**, and solutions to the samples beyond the 2022-2023 open questions.",
        "LARGELY RESOLVED: 13 papers and 30 recurring question types, now the strongest "
        "prediction after KRR. The three-part structure only became visible from your photos."),
    "510638": ("Jan/Feb", 38,
        "**A past project, the figures referenced by the June 2025 paper, and the mark split.**",
        "PARTLY RESOLVED: one written paper recovered, so the syllabus is concrete. Its "
        "questions refer to Figure 1 and Figure 2, which the photograph does not show."),
    "509493": ("Jan/Feb", 22,
        "**Nothing urgent.**",
        "RESOLVED by OCR rather than by the group: 30 image-only PDFs were read with "
        "tesseract, recovering the lecture notes and four exercise-set solutions. 12 papers, "
        "39 questions."),
}


def main() -> int:
    library = json.loads(Path("data/library.json").read_text())["courses"]
    # Courses with nothing archived are absent from the library entirely, and
    # those are exactly the ones this document is about.
    titles = {
        c["code"]: c["name"].title()
        for c in json.loads(Path("data/audit/remaining.json").read_text())
    }

    rows = []
    for code, (when, hours, ask, why) in ASKS.items():
        course = library.get(code, {})
        docs = course.get("documents", [])
        rows.append({
            "code": code,
            "name": titles.get(code, course.get("name", code)).title(),
            "when": when,
            "hours": hours,
            "papers": sum(1 for d in docs if d["role"] == "paper"),
            "keys": sum(1 for d in docs if d["role"] == "solution"),
            "questions": len(course.get("questions", [])),
            "ask": ask,
            "why": why,
        })

    # Sooner and thinner first: an exam in four weeks with nothing archived
    # outranks a January exam with a shallow archive.
    order = {"31 Aug": 0, "01 Sep": 1, "02 Sep": 2, "03 Sep": 3, "04 Sep": 4,
             "08 Sep": 5, "09 Sep": 6, "11 Sep": 7, "15 Sep": 8, "22 Sep": 9,
             "24 Sep": 10, "Jan/Feb": 20}
    rows.sort(key=lambda r: (order.get(r["when"], 15), r["questions"]))

    lines = [
        "# What to ask the course group for",
        "",
        "Generated from `data/library.json`, so the counts are the real ones.",
        "",
        f"The whole archive is {sum(len(c['documents']) for c in library.values())} "
        f"documents, {sum(len(c['questions']) for c in library.values())} extracted "
        f"questions and {sum(1 for c in library.values() for d in c['documents'] if d['role']=='solution')} "
        "published answer keys. It is unevenly spread, and this document is about the "
        "thin end.",
        "",
        f"**September exams with no exam material at all: "
        f"{sum(1 for r in rows if r['when'] != 'Jan/Feb' and r['questions'] == 0)}.**",
        "",
        "Ranked by exam date, then by how thin the archive is.",
        "",
        "| Exam | Course | Papers | Keys | Questions | h |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['when']} | {r['name'][:38]} | {r['papers']} | {r['keys']} | "
            f"{r['questions']} | {r['hours']} |"
        )
    lines += ["", "---", ""]

    for r in rows:
        lines += [
            f"## {r['when']} — {r['name']}",
            "",
            f"*Archived: {r['papers']} papers, {r['keys']} answer keys, "
            f"{r['questions']} extracted questions.*",
            "",
            "**Ask for:** " + r["ask"],
            "",
            r["why"],
            "",
        ]

    lines += [
        "## What I would not bother asking for",
        "",
        "- **Probability** — 11 papers, 20 published answer keys, 178 extracted "
        "questions. The best-covered exam you have.",
        "- **KRR** — 18 papers, 16 keys, 92 questions, and a solved mock for every year "
        "2022 to 2026.",
        "- **Computational Logic** — 28 papers and 294 published answer keys, the SMT-LIB "
        "encodings for four years of sittings. Nothing is missing here.",
        "",
        "## One thing worth asking that is not about papers",
        "",
        "**Does anyone know whether a spring 2027 graduation still counts as *in corso* "
        "for the 2023/24 cohort?** It is worth 2 points on the final mark and a year's "
        "fees, it is not published anywhere I can read, and someone in the year above "
        "will simply know.",
        "",
    ]

    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} — {len(rows)} courses ranked")
    for r in rows[:5]:
        print(f"  {r['when']:>7} {r['name'][:34]:<34} papers={r['papers']} questions={r['questions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
