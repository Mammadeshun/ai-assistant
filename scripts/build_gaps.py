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
        "Nothing at all is archived for this course — zero papers, zero questions.",
        "12 CFU for 28 h is the best rate in the plan, and I am currently sending you "
        "in blind. One recalled paper would be worth more here than anywhere else."),
    "509485": ("08 Sep", 27,
        "**Screenshots or notes from the chapter quizzes** (chapters 1, 2, 3, 5, 6, 8, 10) "
        "and **the research-paper questions** (STM, LTM, TPS, Language). Also anyone's "
        "recollection of the written paper's 20 open questions.",
        "The quizzes were single-attempt, time-limited, and closed in 2025, so their "
        "content was never archivable. Someone who sat them may have saved them."),
    "509494": ("03 Sep", 26,
        "**The project-topics document** (it lives on a course Google Drive, not Kiro) "
        "and **any past written paper**.",
        "Zero documents are archived. The project is 30% of the mark and carries across "
        "sessions, so getting the topic list early is worth more than the paper."),
    "509521": ("01 Sep", 25,
        "**The nine lab assignment briefs**, and whether anyone has submitted in an "
        "autumn session.",
        "Only one stub page is archived. If the submission windows are closed the course "
        "cannot be sat, and that changes the September plan by 25 hours."),
    "509496": ("31 Aug", 30,
        "**A past project report and slide deck**, and whether anyone has presented in "
        "an autumn session.",
        "One stub page archived. The autumn presentation slot is unconfirmed and this is "
        "your first exam."),
    "509486": ("15 Sep", 28,
        "**Solved notebooks for the June and July 2026 papers.**",
        "Both briefs are archived but no worked solutions. This exam is an upload, so "
        "seeing a full-mark submission is worth more than any theory."),
    "509492": ("22 Sep", 30,
        "**Confirmation of the exam format**, and any real past paper rather than a mock.",
        "Only two mock exams exist. Both parse as multiple choice, which supports what "
        "you told me — but if it is actually a written physics paper the budget is wrong "
        "by 15 to 60 hours. This is the largest single uncertainty in the plan."),
    "509495": ("04 Sep", 19,
        "**The assignment texts set during delivery**, and any solved mockup.",
        "Three papers, zero answer keys. Novelty is 0.54, so past papers help less here "
        "than anywhere else and worked solutions matter more."),
    "509488": ("24 Sep", 30,
        "**Solutions to any of the three TMNLP samples.**",
        "Four papers, zero answer keys. With -0.5 for a wrong closed answer, knowing the "
        "right answer is worth double."),
    "509481": ("11 Sep", 44,
        "**Part 2 tests and their solutions**, and Part 1 tests from 2025 and 2026.",
        "21 papers but only 3 answer keys, and the archive stops at the 2024 sittings "
        "plus one 2026 Feb set."),
    "509477": ("09 Sep", 44,
        "**Any paper after 2023** — the archive stops at July 2023.",
        "Six papers, 16 keys, all from 2022-2023. Three years stale on an exam with two "
        "independent pass gates."),
    "509493": ("Jan/Feb", 22,
        "**Text versions of the lecture notes, or anyone's typed notes.**",
        "Thirty of the 48 archived PDFs are single-page image exports with no text layer "
        "— readable by eye, not searchable and not drillable. The six past exams are fine."),
    "504464": ("Jan/Feb", 45,
        "**The per-Learning-Test example questions**, and anyone's recollection of the "
        "240-question sitting.",
        "One document archived, one question extracted. You need ~73% net accuracy across "
        "240 MCQs with -1 marking and I currently have almost nothing to drill."),
    "509498": ("Jan/Feb", 16,
        "**Whether anyone has an open autumn lab window**, and a copy of a submitted lab "
        "project.",
        "The written half is solved by your own 85-question bank. The lab gate is the "
        "entire blocker."),
    "510638": ("Jan/Feb", 38,
        "**A past project and the mark split** across project, presentation and written.",
        "No papers archived and the mark split is unverified, which is part of why it "
        "was deferred."),
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
        "The whole archive is 655 documents, 455 extracted questions and 353 published "
        "answer keys — but it is very unevenly spread. Two courses (Probability, KRR) "
        "carry more than half the questions between them. Four of your eleven September "
        "exams have **no exam material archived at all**.",
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
