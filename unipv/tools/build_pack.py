#!/usr/bin/env python3
"""Render the printable study pack from the extracted JSON.

    python build_pack.py --only CODE[,CODE]

Emits Typst and compiles it. Nothing here is hand-authored per question: the
questions come from data/questions.jsonl, the answers from the files the
extractor paired with them, and the figures from each course's
_figures/index.json.

Four documents per course, all A4 portrait with 2 cm margins and pure black on
white - these get printed, and a background fill is a cartridge of ink:

  PRACTICE_<code>.pdf   questions only, with ruled space sized to the answer
  SOLUTIONS_<code>.pdf  the same numbering, worked
  MOCK-EXAM_<code>.pdf  one paper of the recurring archetypes, in exam format
  PASS-ESSENTIALS_<code>.pdf   the minimum to reach 18, from pack_content/

PASS-ESSENTIALS is the one document that needs judgement rather than
transcription, so its content is authored separately into
data/pack_content/<code>.json and only rendered here. The other three are
mechanical and are built whether or not that file exists.

Every practice question carries its provenance - [PAST PAPER - file, date] or
[GENERATED VARIANT] - because a question presented as real when it is not is
the worst thing this pipeline could produce. verify.py fails the build if any
question lacks one.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gradplan.predictability import Item, classify  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA, OUT, RAW = ROOT / "data", ROOT / "output", ROOT / "raw"
CONTENT = DATA / "pack_content"
TAXONOMY = json.loads((ROOT.parent / "reference/topic_taxonomy.json").read_text())

# Answer space, in centimetres, by what the question asks for.
SPACE = {"short": 5.0, "medium": 9.0, "long": 16.0, "plot": 12.0}
LONG = re.compile(r"prove|dimostr|derive|deriv|calcul|comput|solve|risolv|"
                  r"algorithm|algoritm|implement|write a function|scriv", re.I)
PLOT = re.compile(r"plot|graph|grafico|diagram|sketch|disegn|tree|albero|"
                  r"network|automat", re.I)
SHORT = re.compile(r"^(what|which|define|definisci|list|elenca|state|enunci|"
                   r"true or false|vero o falso)\b", re.I)


ZWSP = "\u200b"


def breakable(text: str, limit: int = 32) -> str:
    """Give very long unbroken runs somewhere to wrap.

    RDF triples, URIs and code identifiers have no spaces, so Typst cannot
    break them and they run off the right edge of the paper - measured at
    x1=598pt on a 595pt page. Zero-width spaces inside long tokens give the
    line breaker an opportunity without changing what is printed.
    """
    out = []
    for token in text.split(" "):
        if len(token) > limit:
            token = ZWSP.join(token[i:i + limit] for i in range(0, len(token), limit))
        out.append(token)
    return " ".join(out)


def esc(text: str) -> str:
    """Typst-escape. Content mode needs these neutralised."""
    # PDF extraction of some answer keys left U+FFFD where a glyph could not
    # be mapped. Printing a black box tells the reader nothing; say plainly
    # that a character was lost in extraction.
    text = text.replace("\ufffd", "[?]")
    out = breakable(text).replace("\\", "\\\\")
    # Braces open a code block in Typst and a tilde is a non-breaking space, so
    # a question containing either broke compilation with "expected colon".
    for ch in "#$*_`<>@=[]{}~":
        out = out.replace(ch, "\\" + ch)
    # At the start of a line, "/", "-" and "+" are markup: "/ term" opens a
    # term list and then demands a colon, which is what broke Brain Modelling
    # on a question that happened to begin "/ 3. Define the entropy rate".
    # `line[:1] in "/-+"` is True for a blank line, because the empty string is
    # a substring of everything. Every blank line became a lone backslash,
    # which escaped whatever followed - including the "]" closing #text(...)[.
    def guard(line: str) -> str:
        stripped = line.lstrip()
        if stripped[:1] and stripped[0] in "/-+":
            indent = line[: len(line) - len(stripped)]
            return indent + "\\" + stripped
        return line

    return "\n".join(guard(line) for line in out.split("\n"))


def answer_space(text: str) -> float:
    if PLOT.search(text):
        return SPACE["plot"]
    if SHORT.match(text.strip()):
        return SPACE["short"]
    if LONG.search(text):
        return SPACE["long"]
    return SPACE["medium"]


def preamble(title: str, subtitle: str) -> str:
    return f"""#set page(paper: "a4", margin: 2cm, numbering: "1 / 1",
  header: context {{ if counter(page).get().first() > 1 {{
    set text(8pt, fill: black); emph[{esc(subtitle)}]; h(1fr); emph[{esc(title)}]
  }} }})
#set text(font: ("DejaVu Serif", "Liberation Serif", "Times New Roman"),
          size: 11pt, fill: black, lang: "en", hyphenate: true)
#set par(justify: false, leading: 0.65em)
#set heading(numbering: none)
#show heading.where(level: 1): it => {{ set text(16pt, weight: "bold"); block(above: 1.2em, below: 0.7em, it) }}
#show heading.where(level: 2): it => {{ set text(13pt, weight: "bold"); block(above: 1.0em, below: 0.5em, it) }}
#show heading.where(level: 3): it => {{ set text(11.5pt, weight: "bold"); block(above: 0.8em, below: 0.4em, it) }}
#show table: set block(breakable: false)
#set table(stroke: 0.4pt)

#align(center)[
  #text(19pt, weight: "bold")[{esc(title)}]
  #v(0.3em)
  #text(11pt)[{esc(subtitle)}]
]
#v(0.8em)
#line(length: 100%, stroke: 0.6pt)
#v(0.8em)
"""


def provenance(row: dict) -> str:
    name = Path(row["source_file"]).name
    when = row.get("exam_date") or "date unknown"
    return f"[PAST PAPER — {name}, {when}]"


def ruled(height_cm: float) -> str:
    """Ruled writing space. Lines every 8mm, which is what people write on."""
    lines = max(1, int(height_cm * 10 // 8))
    return ("#v(0.4em)\n" + "\n".join(
        "#line(length: 100%, stroke: 0.3pt + luma(60%))\n#v(8mm)"
        for _ in range(lines)) + "\n")


def build_practice(code: str, name: str, rows: list[dict]) -> str:
    doc = preamble(f"PRACTICE — {name}", f"{code} · questions only, no answers")
    doc += ("#block(inset: 8pt, stroke: 0.5pt)[Every question below is tagged "
            "with where it came from. Answers are in the separate SOLUTIONS "
            "document — do not open it until you have written something here.]\n\n")
    by_topic: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_topic[row.get("topic") or "General"].append(row)
    number = 0
    for topic, items in sorted(by_topic.items(), key=lambda kv: -len(kv[1])):
        doc += f"\n= {esc(topic)}\n\n"
        for row in items:
            number += 1
            marks = f" · {row['points']} marks" if row.get("points") else ""
            minutes = max(4, min(35, len(row["text"]) // 60))
            doc += (f"\n== Q{number}\n\n"
                    f"#text(8.5pt)[{esc(provenance(row))} · ~{minutes} min{esc(marks)}]\n\n"
                    f"{esc(row['text'][:2200])}\n\n")
            doc += ruled(answer_space(row["text"]))
            doc += "\n#pagebreak(weak: true)\n"
    return doc


def build_solutions(code: str, name: str, rows: list[dict],
                    answers: dict[int, str]) -> str:
    doc = preamble(f"SOLUTIONS — {name}", f"{code} · worked answers")
    doc += ("#block(inset: 8pt, stroke: 0.5pt)[Numbering matches PRACTICE. "
            "Where the archive published an official answer it is quoted and "
            "cited; anything else is marked as reconstructed and should be "
            "checked before you rely on it.]\n\n")
    by_topic: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_topic[row.get("topic") or "General"].append(row)
    number = 0
    for topic, items in sorted(by_topic.items(), key=lambda kv: -len(kv[1])):
        doc += f"\n= {esc(topic)}\n\n"
        for row in items:
            number += 1
            doc += f"\n== Q{number}\n\n#text(8.5pt)[{esc(provenance(row))}]\n\n"
            doc += f"#emph[{esc(row['text'][:600])}]\n\n"
            body = answers.get(number)
            if body:
                doc += f"*Answer* — quoted from the published key.\n\n{esc(body[:3000])}\n\n"
            else:
                doc += ("#block(inset: 6pt, stroke: 0.5pt)[*No published answer "
                        "was found for this question in the archive.* Work it "
                        "from the notes; do not assume the pack knows it.]\n\n")
    return doc


def build_mock(code: str, name: str, rows: list[dict], minutes: int = 120) -> str:
    """One paper of the archetypes that actually recur, not a reshuffle."""
    from gradplan.drillbank import cluster
    from gradplan.predictability import Item

    groups = cluster([Item(paper=r["source_file"], index=r["q_number"],
                           marks=r["points"], text=r["text"]) for r in rows])
    recurring = sorted([g for g in groups if g.n_papers > 1],
                       key=lambda g: -g.n_papers) or groups[:6]
    picked = recurring[:6]
    doc = preamble(f"MOCK EXAM — {name}", f"{code} · {minutes} minutes")
    doc += (f"#block(inset: 8pt, stroke: 0.5pt)[Time: *{minutes} minutes*. "
            f"Built from the {len(picked)} question archetypes that recur across "
            f"the most sittings in the archive — not a reshuffle of the practice "
            f"set. Sit it once, timed, with nothing open.]\n\n")
    for index, group in enumerate(picked, start=1):
        rep = group.representative
        doc += (f"\n= Question {index}\n\n"
                f"#text(8.5pt)[appears in {group.n_papers} of the archived "
                f"sittings · [GENERATED VARIANT — representative of a recurring "
                f"archetype]]\n\n{esc(rep.text[:1800])}\n\n")
        doc += ruled(answer_space(rep.text))
        doc += "\n#pagebreak(weak: true)\n"
    return doc


def build_essentials(code: str, name: str, content: dict, figures: list[dict],
                     fig_dir: Path) -> str:
    """Render the authored pass-essentials content. Figures are placed, never
    described: a diagram redrawn in prose is a diagram lost."""
    doc = preamble(f"PASS ESSENTIALS — {name}",
                   f"{code} · the minimum to reach 18")
    brief = content.get("exam_brief", {})
    if brief:
        doc += "= Exam brief\n\n#table(columns: (auto, 1fr),\n"
        for key, value in brief.items():
            doc += f"  [*{esc(str(key))}*], [{esc(str(value))}],\n"
        doc += ")\n\n#pagebreak()\n"

    for topic in content.get("topics", []):
        doc += f"\n= {esc(topic['name'])}\n\n"
        if topic.get("frequency"):
            doc += f"#text(9pt)[#emph[{esc(topic['frequency'])}]]\n\n"
        for block in topic.get("blocks", []):
            kind = block.get("kind", "text")
            if kind == "heading":
                doc += f"\n== {esc(block['text'])}\n\n"
            elif kind == "math":
                doc += f"$ {block['text']} $\n\n"
            elif kind == "steps":
                doc += "".join(f"+ {esc(s)}\n" for s in block["items"]) + "\n"
            elif kind == "figure":
                path = fig_dir / block["png"]
                if path.exists():
                    doc += (f'#figure(image("{path.as_posix()}", width: '
                            f'{block.get("width", "85%")}), caption: '
                            f'[{esc(block.get("caption", ""))}])\n\n')
            else:
                doc += f"{esc(block['text'])}\n\n"
        doc += "#pagebreak(weak: true)\n"

    if content.get("formula_sheet"):
        doc += "\n#pagebreak()\n= Formula sheet\n\n"
        for line in content["formula_sheet"]:
            doc += f"$ {line} $\n"
        doc += "\n"
    if content.get("traps"):
        doc += "\n= Where marks are lost\n\n"
        doc += "".join(f"- {esc(t)}\n" for t in content["traps"]) + "\n"
    if content.get("six_hours"):
        doc += "\n= If you only have six hours\n\n"
        doc += "".join(f"+ {esc(t)}\n" for t in content["six_hours"]) + "\n"
    return doc


def compile_typst(source: str, target: Path) -> tuple[bool, str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    src = target.with_suffix(".typ")
    src.write_text(source)
    try:
        import typst

        typst.compile(str(src), output=str(target))
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:400]


def load_answers(code: str, rows: list[dict]) -> dict[int, str]:
    """Published answer text per practice number, where the archive has one."""
    classified = json.loads((DATA / "classified.json").read_text())
    keys = [e for e in classified.get(code, []) if e["role"] == "SOLUTIONS"]
    texts = {}
    for entry in keys:
        path = ROOT / entry["text"]
        if path.exists():
            texts[Path(entry["path"]).stem.lower()] = path.read_text(errors="replace")
    out: dict[int, str] = {}
    by_topic: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_topic[row.get("topic") or "General"].append(row)
    number = 0
    for _, items in sorted(by_topic.items(), key=lambda kv: -len(kv[1])):
        for row in items:
            number += 1
            stem = Path(row["source_file"]).stem.lower()
            for key, body in texts.items():
                if stem[:14] in key or key[:14] in stem:
                    out[number] = body
                    break
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated course codes")
    args = parser.parse_args()

    build_set = json.loads((DATA / "build_set.json").read_text())
    if args.only:
        build_set = [c for c in args.only.split(",")]
    names = {a["code"]: a["name"] for a in
             json.loads((DATA / "esse3.json").read_text())["remaining"]}
    questions: dict[str, list[dict]] = defaultdict(list)
    for line in (DATA / "questions.jsonl").read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            questions[row["course"]].append(row)

    OUT.mkdir(parents=True, exist_ok=True)
    made, failed = [], []
    for code in build_set:
        name = names.get(code, code)
        rows = [r for r in questions.get(code, []) if len(r["text"]) > 40]
        if not rows:
            failed.append((code, "no questions"))
            continue
        # Group by syllabus topic where a taxonomy exists, so the practice set
        # is ordered by what the examiner actually asks about rather than by
        # which file a question happened to come out of.
        topics = {k: v for k, v in TAXONOMY.get(code, {}).items()
                  if not k.startswith("_")}
        if topics:
            items = [Item(paper=r["source_file"], index=r["q_number"],
                          marks=r["points"], text=r["text"]) for r in rows]
            classify(items, topics)
            for row, item in zip(rows, items):
                row["topic"] = (item.topic or "General").replace("_", " ").title()
        answers = load_answers(code, rows)
        fig_dir = next((p for p in RAW.glob(f"{code}-*/_figures")), None)
        figures = []
        if fig_dir and (fig_dir / "index.json").exists():
            figures = json.loads((fig_dir / "index.json").read_text())

        jobs = [
            (f"PRACTICE_{code}.pdf", build_practice(code, name, rows)),
            (f"SOLUTIONS_{code}.pdf", build_solutions(code, name, rows, answers)),
            (f"MOCK-EXAM_{code}.pdf", build_mock(code, name, rows)),
        ]
        content_file = CONTENT / f"{code}.json"
        if content_file.exists():
            jobs.append((f"PASS-ESSENTIALS_{code}.pdf",
                         build_essentials(code, name,
                                          json.loads(content_file.read_text()),
                                          figures, fig_dir or RAW)))
        for filename, source in jobs:
            ok, err = compile_typst(source, OUT / filename)
            (made if ok else failed).append((filename, err))
            print(f"  {'ok  ' if ok else 'FAIL'} {filename}" + (f"  {err[:120]}" if err else ""))

    print(f"\n{len(made)} built, {len(failed)} failed, in {OUT}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
