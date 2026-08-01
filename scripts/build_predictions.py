#!/usr/bin/env python3
"""Predict the shape of each September paper from the archive.

A prediction is only worth having if it comes with the grounds for doubting it,
so every course gets a confidence built from three measurable things:

* **novelty** - how much the papers change year to year (from predictability.py);
* **depth** - how many papers the archive actually contains;
* **splittability** - whether the papers could be broken into items at all.

Courses that fail any of those are printed as UNRELIABLE with the reason,
rather than given a confident-looking list of questions. Data Mining is the
worked example: novelty 0.54 means half of each paper is genuinely new, and a
prediction there would be a guess wearing a suit.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DRILL = Path("data/drill")
OUT = Path("reference/predicted")

# Courses sat in September, in exam order.
SEPTEMBER = [
    ("509496", "Information Retrieval & RecSys", "31 Aug"),
    ("509521", "Laboratory of Machine Learning", "01 Sep"),
    ("509519", "Ethics, Law and AI", "02 Sep"),
    ("509494", "Brain Modelling", "03 Sep"),
    ("509495", "Data Mining", "04 Sep"),
    ("509485", "Cognitive Psychology", "08 Sep"),
    ("509477", "Computer Programming", "09 Sep"),
    ("509481", "Calculus", "11 Sep"),
    ("509486", "Machine Learning / ANN / DL", "15 Sep"),
    ("509492", "Theoretical & Quantum Physics", "22 Sep"),
    ("509488", "Text Mining and NLP", "24 Sep"),
]

JANUARY = [
    ("510109", "Probability and Statistical Inference"),
    ("509478", "Knowledge Representation and Reasoning"),
    ("504464", "Organization Theory and Design"),
    ("510638", "Web and Social Media Search and Analysis"),
    ("509483", "Computational Logic"),
    ("509487", "Fuzzy Systems and Evolutionary Computing"),
    ("509493", "Statistical Modelling"),
    ("509498", "AI for Communication and Marketing"),
]

MIN_PAPERS = 4
MAX_NOVELTY = 0.40
MIN_ITEMS_PER_PAPER = 2.0


def confidence(bank: dict, novelty: float | None) -> tuple[str, list[str]]:
    """A verdict plus every reason it might be wrong."""
    reasons: list[str] = []
    n_papers = bank.get("n_papers", 0)
    n_items = bank.get("n_items", 0)
    per_paper = (n_items / n_papers) if n_papers else 0.0

    recurring = sum(1 for q in bank.get("question_types", []) if q["seen_in_papers"] >= 2)
    if recurring == 0 and n_papers >= 2:
        reasons.append(
            "no question type appears in two or more papers — whatever the novelty "
            "score says, this archive contains no measurable repetition to predict from"
        )
    if n_papers < MIN_PAPERS:
        reasons.append(f"only {n_papers} papers in the archive (need {MIN_PAPERS})")
    if per_paper < MIN_ITEMS_PER_PAPER:
        reasons.append(
            f"papers could not be split into questions ({per_paper:.1f} items/paper) — "
            "the recurrence numbers below are not trustworthy"
        )
    if novelty is not None and novelty > MAX_NOVELTY:
        reasons.append(
            f"novelty {novelty:.2f}: the paper is substantially rewritten each year, "
            "so past questions predict format but not content"
        )

    if reasons:
        return "UNRELIABLE", reasons
    if novelty is not None and novelty < 0.20 and recurring >= 5:
        return "STRONG", []
    return "MODERATE", []


def main() -> int:
    predictability = {}
    path = Path("data/audit/predictability.json")
    if path.exists():
        predictability = json.load(open(path))

    OUT.mkdir(parents=True, exist_ok=True)
    index_lines = [
        "# Predicted papers",
        "",
        "One file per course. Each lists the question types most likely to appear, "
        "ranked by how many past papers contained them, with the archived solution "
        "named where one exists.",
        "",
        "A prediction is a drill order, not a prophecy. Where the archive cannot "
        "support one, the file says so instead of guessing.",
        "",
        "| Course | Exam | Papers | Items | Confidence | Note |",
        "|---|---|---|---|---|---|",
    ]

    for code, name, when in SEPTEMBER + [(c, n, "Jan/Feb") for c, n in JANUARY]:
        bank_path = DRILL / f"{code}.json"
        if not bank_path.exists():
            index_lines.append(f"| {name} | {when} | 0 | 0 | NO DATA | nothing archived |")
            continue
        bank = json.load(open(bank_path))
        novelty = (predictability.get(code) or {}).get("novelty_score")
        verdict, reasons = confidence(bank, novelty)

        types = bank["question_types"]
        counts = [len(types)]
        typical = max(1, int(statistics.median(counts)))

        lines = [
            f"# {name} ({code}) — predicted paper",
            "",
            f"Exam: **{when}**  ·  archive: **{bank['n_papers']} papers, "
            f"{bank['n_items']} questions**  ·  "
            f"novelty: **{novelty:.2f}**" if novelty is not None else
            f"Exam: **{when}**  ·  archive: **{bank['n_papers']} papers, "
            f"{bank['n_items']} questions**  ·  novelty: not measurable",
            "",
            f"## Confidence: {verdict}",
            "",
        ]
        if reasons:
            lines.append("This prediction should not be relied on:")
            lines += [f"- {r}" for r in reasons]
            lines.append("")
            lines.append(
                "Use the papers below as a guide to *format and style*. Study the "
                "syllabus, not this list."
            )
            lines.append("")

        recurring = [q for q in types if q["seen_in_papers"] >= 2]
        lines += [
            f"## Question types that recur ({len(recurring)} of {len(types)})",
            "",
        ]
        if not recurring:
            lines.append(
                "_No question type appears in two or more papers. Either the archive "
                "is too shallow or the exam is genuinely new each session._"
            )
            lines.append("")
        for question in recurring[:25]:
            share = question["share_of_papers"]
            marks = question["typical_marks"]
            head = f"### {question['topic']} — seen in {question['seen_in_papers']} papers ({share:.0%})"
            if marks:
                head += f", typically {marks:g} marks"
            lines.append(head)
            lines.append("")
            if question["solution_key"]:
                lines.append(f"*Worked solution published in:* `{question['solution_key']}`")
                lines.append("")
            statement = question["statement"].strip().replace("\n", " ")
            lines.append("> " + statement[:600] + ("…" if len(statement) > 600 else ""))
            lines.append("")
            lines.append("*Appears in:* " + ", ".join(question["papers"][:6]))
            lines.append("")

        if bank["solution_keys"]:
            lines += [
                "## Published answer keys",
                "",
                *[f"- `{k}`" for k in bank["solution_keys"]],
                "",
            ]
        if bank["papers_without_a_published_key"]:
            lines += [
                "## Papers with no published key",
                "",
                "Do these last, timed, as mock exams — you cannot check yourself, so "
                "they are worth more as rehearsal than as practice.",
                "",
                *[f"- {p}" for p in bank["papers_without_a_published_key"][:30]],
                "",
            ]

        (OUT / f"{code}.md").write_text("\n".join(lines) + "\n")
        note = reasons[0][:60] if reasons else ""
        index_lines.append(
            f"| {name} | {when} | {bank['n_papers']} | {bank['n_items']} | "
            f"{verdict} | {note} |"
        )
        print(
            f"{code} {name[:34]:<34} papers={bank['n_papers']:>3} "
            f"items={bank['n_items']:>4} recurring={len(recurring):>3} {verdict}"
        )

    (OUT / "README.md").write_text("\n".join(index_lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
