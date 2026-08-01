#!/usr/bin/env python3
"""Assemble the complete offline corpus: data/library.json.

Everything reachable, in one place — every archived document with its text,
every exam question extracted from those documents, and the multiple-choice
banks that carry answer keys. The cockpit renders this; nothing here touches
the network.

Roles are assigned honestly:
  paper     an exam whose questions were extracted
  solution  a published answer key
  material  lecture notes, briefs, anything else worth reading
  stub      a Moodle activity page with no content (kept, but marked)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gradplan.drillbank import (  # noqa: E402
    Document,
    _clean,
    collect_documents,
    expand_zip,
    read_text,
    split_paper,
)
from gradplan.predictability import classify  # noqa: E402

OUT = Path("data/library.json")

# 'a. Data governance ✓ b. infrastructure' — the tick marks the answer.
OPTION = re.compile(r"(?:^|\s)([a-h])[.)]\s*")
TICK = "✓"


def parse_mcq(text: str) -> dict | None:
    """Split a solved multiple-choice item into stem, options and answers."""
    marks = list(OPTION.finditer(text))
    if len(marks) < 2:
        return None
    stem = text[: marks[0].start()].strip()
    if not stem:
        return None
    options = []
    bounds = [m for m in marks] + [None]
    for current, following in zip(bounds, bounds[1:]):
        end = following.start() if following is not None else len(text)
        body = text[current.end(): end].strip()
        correct = TICK in body
        options.append({
            "letter": current.group(1),
            "text": body.replace(TICK, "").strip(),
            "correct": correct,
        })
    if not any(o["correct"] for o in options):
        return None
    return {"stem": stem, "options": options}


def load_mcq_bank() -> list[dict]:
    path = Path("data/audit/509498_mcq_bank.json")
    if not path.exists():
        return []
    bank = json.loads(path.read_text())
    out = []
    for item in bank.get("items", []):
        parsed = parse_mcq(item["text"])
        if parsed:
            parsed["topic"] = item.get("topic", "")
            parsed["n"] = item.get("n")
            out.append(parsed)
    return out


def _key(name: str) -> str:
    """Names survive a round trip through a filename slug, which turns
    punctuation into runs of spaces. Compare on collapsed, lowercased words."""
    return " ".join(re.sub(r"[^0-9a-zA-Z]+", " ", name).split()).lower()


OVERRIDES = {
    _key(k): v
    for k, v in json.loads(Path("reference/document_roles.json").read_text()).items()
    if not k.startswith("_")
}


def role_of(doc: Document) -> str:
    # The automatic rules read a filename. Where the content is known - a quiz
    # published together with its answers reads as an answer key, and a recalled
    # paper reads as nothing at all - an explicit override wins.
    override = OVERRIDES.get(_key(doc.name))
    if override:
        return override
    if doc.is_activity_stub:
        return "stub"
    if doc.is_solution:
        return "solution"
    if doc.looks_like_paper and len(doc.text.strip()) > 150:
        return "paper"
    return "material"


def main() -> int:
    remaining = {c["code"]: c["name"] for c in json.load(open("data/audit/remaining.json"))}
    papers_index = json.load(open("data/audit/papers_index.json"))
    taxonomy = json.load(open("reference/topic_taxonomy.json"))
    resolved = collect_documents(remaining, papers_index)

    courses: dict[str, dict] = {}
    total_chars = 0

    for code, name in remaining.items():
        docs = resolved.get(code, [])
        if not docs:
            continue

        # Expand zips into their members, as the drill bank does.
        expanded: list[Document] = []
        for doc in docs:
            if doc.kind == "zip":
                for member, text in expand_zip(doc.path):
                    child = Document(
                        course=code,
                        name=f"{doc.name} / {member}",
                        path=doc.path,
                        kind="pdf" if member.lower().endswith(".pdf") else "text",
                        mid=doc.mid,
                        parent=doc.parent or doc.name,
                    )
                    child.text = text
                    expanded.append(child)
                continue
            doc.text = read_text(doc.path, doc.kind)
            expanded.append(doc)

        documents = []
        questions = []
        topics = {k: v for k, v in taxonomy.get(code, {}).items() if not k.startswith("_")}

        for index, doc in enumerate(expanded):
            text = doc.text.strip()
            # A PDF with no text layer is not absent, it is unsearchable. The
            # Statistical Modelling lecture notes are single-page image exports;
            # dropping them would hide 30 documents that exist on disk and are
            # perfectly readable by eye.
            role = role_of(doc) if text else "image-only"
            documents.append({
                "i": index,
                "name": doc.name,
                "kind": doc.kind,
                "role": role,
                "chars": len(text),
                "text": text,
                "path": str(doc.path),
            })
            total_chars += len(text)
            if not text:
                continue

            if role == "paper":
                items = split_paper(_clean(text), doc.name)
                if topics:
                    classify(items, topics)
                for item in items:
                    body = item.text.strip()
                    if len(body) < 40:
                        continue
                    questions.append({
                        "doc": index,
                        "paper": doc.name,
                        "topic": item.topic,
                        "marks": item.marks,
                        "text": body,
                        "mcq": parse_mcq(body) is not None,
                    })

        counts = {}
        for entry in documents:
            counts[entry["role"]] = counts.get(entry["role"], 0) + 1

        courses[code] = {
            "name": name,
            "documents": documents,
            "questions": questions,
            "counts": counts,
        }
        print(
            f"{code} {name[:34]:<34} docs={len(documents):>4} "
            f"questions={len(questions):>4} "
            f"papers={counts.get('paper',0):>3} keys={counts.get('solution',0):>3} "
            f"material={counts.get('material',0):>3} stubs={counts.get('stub',0):>3}"
        )

    library = {
        "courses": courses,
        "quiz_banks": {
            "509498": {
                "name": "AI for Communication and Marketing",
                "source": "solved MCQ bank supplied by the student",
                "items": load_mcq_bank(),
            }
        },
    }
    OUT.write_text(json.dumps(library, ensure_ascii=False))
    print(
        f"\nwrote {OUT} ({OUT.stat().st_size/1e6:.1f} MB) — "
        f"{len(courses)} courses, {total_chars/1e6:.2f} MB of text, "
        f"{sum(len(c['questions']) for c in courses.values())} questions, "
        f"{len(library['quiz_banks']['509498']['items'])} solved MCQs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
