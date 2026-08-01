#!/usr/bin/env python3
"""Build the per-course drill banks from the raw archive.

Usage:  python3 scripts/build_drillbank.py [course_code ...]

Writes data/drill/<course>.json and prints a coverage line per course so a
course that produced nothing is visible rather than silently absent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gradplan.drillbank import build, collect_documents  # noqa: E402

OUT = Path("data/drill")


def main(argv: list[str]) -> int:
    remaining = {c["code"]: c["name"] for c in json.load(open("data/audit/remaining.json"))}
    papers_index = json.load(open("data/audit/papers_index.json"))
    taxonomy = json.load(open("reference/topic_taxonomy.json"))

    wanted = argv or [c for c in remaining if c in taxonomy]
    documents = collect_documents(remaining, papers_index)

    OUT.mkdir(parents=True, exist_ok=True)
    summary = []
    for code in wanted:
        topics = {k: v for k, v in taxonomy.get(code, {}).items() if not k.startswith("_")}
        if not topics:
            print(f"{code:>7} {remaining.get(code,'?')[:34]:<34} SKIP no taxonomy")
            continue
        bank = build(code, documents.get(code, []), topics)
        bank["name"] = remaining.get(code, "")
        (OUT / f"{code}.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1))
        top = bank["question_types"][:1]
        recurring = sum(1 for q in bank["question_types"] if q["seen_in_papers"] >= 2)
        print(
            f"{code:>7} {remaining.get(code,'?')[:34]:<34} "
            f"docs={bank['documents_resolved']:>3} papers={bank['n_papers']:>3} "
            f"items={bank['n_items']:>4} types={len(bank['question_types']):>4} "
            f"recurring={recurring:>3} keys={len(bank['solution_keys']):>3} "
            f"top={top[0]['seen_in_papers'] if top else 0}"
        )
        summary.append((code, bank))

    print(f"\nwrote {len(summary)} banks to {OUT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
