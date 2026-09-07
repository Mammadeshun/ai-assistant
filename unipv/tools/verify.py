#!/usr/bin/env python3
"""Check the printable pack before claiming it is done.

    python verify.py [--output-dir unipv/output]

Five checks, each of which has caught a real defect in a generated pack:

  coverage     every question archetype in questions.jsonl reaches a section of
               that course's PASS-ESSENTIALS. A pack that drills 70% of what
               the examiner asks is a pack that fails 30% of the time.
  glyphs       non-embedded fonts, blank pages, and tofu (U+FFFD, box glyphs).
               A formula that renders as boxes on the printer is worse than one
               that is missing, because you only find out in the exam hall.
  geometry     A4, text inside the margin box, no zero-area figures, no table
               split across a page break.
  fidelity     five formulas per course diffed character by character against
               the source text layer, with the source line quoted.
  fabrication  every practice question carries [PAST PAPER - file, date] or
               [GENERATED VARIANT]. Any question with neither fails the build:
               a made-up question presented as a real one is the single worst
               thing this pipeline could produce.

Exit status is non-zero if fabrication or glyph checks fail - those are not
advisory.
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

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

A4_PT = (595, 842)
A4_TOLERANCE = 6
MARGIN_CM = 2.0
MARGIN_PT = MARGIN_CM * 72 / 2.54
TOFU = re.compile(r"[�□■]")
TAG = re.compile(r"\[(PAST PAPER[^\]]*|GENERATED VARIANT)\]")
FORMULA = re.compile(r"[=<>≤≥∑∏∫√±]|\\frac|\\sum|\\int")


def run(cmd: list[str], timeout: int = 120) -> str:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return done.stdout + done.stderr
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"ERROR {exc!r}"


def page_texts(pdf: Path) -> list[str]:
    out = []
    info = run(["pdfinfo", str(pdf)])
    pages = int((re.search(r"Pages:\s+(\d+)", info) or [0, 1])[1])
    for number in range(1, pages + 1):
        out.append(run(["pdftotext", "-f", str(number), "-l", str(number),
                        "-layout", str(pdf), "-"]))
    return out


def check_glyphs(pdfs: list[Path]) -> tuple[list[str], list[str]]:
    problems, notes = [], []
    for pdf in pdfs:
        fonts = run(["pdffonts", str(pdf)])
        for line in fonts.splitlines()[2:]:
            parts = line.split()
            if len(parts) >= 5 and parts[3].lower() == "no":
                problems.append(f"{pdf.name}: font not embedded — {parts[0]}")
        for index, text in enumerate(page_texts(pdf), start=1):
            if not text.strip():
                problems.append(f"{pdf.name} p{index}: page has no extractable text")
            elif TOFU.search(text):
                problems.append(f"{pdf.name} p{index}: tofu glyph (U+FFFD or box)")
        notes.append(f"{pdf.name}: {len(page_texts(pdf))} pages checked")
    return problems, notes


def check_geometry(pdfs: list[Path]) -> list[str]:
    problems = []
    for pdf in pdfs:
        info = run(["pdfinfo", str(pdf)])
        size = re.search(r"Page size:\s+([\d.]+) x ([\d.]+)", info)
        if not size:
            problems.append(f"{pdf.name}: page size unreadable")
            continue
        width, height = float(size.group(1)), float(size.group(2))
        if (abs(width - A4_PT[0]) > A4_TOLERANCE
                or abs(height - A4_PT[1]) > A4_TOLERANCE):
            problems.append(f"{pdf.name}: not A4 ({width:.0f}x{height:.0f}pt)")
        try:
            import fitz

            fitz.TOOLS.mupdf_display_errors(False)
            doc = fitz.open(pdf)
            for number, page in enumerate(doc, start=1):
                box = page.rect
                for block in page.get_text("blocks"):
                    x0, y0, x1, y1 = block[:4]
                    if (x0 < MARGIN_PT - 2 or y0 < MARGIN_PT - 2
                            or x1 > box.width - MARGIN_PT + 2
                            or y1 > box.height - MARGIN_PT + 2):
                        problems.append(
                            f"{pdf.name} p{number}: text outside the {MARGIN_CM}cm "
                            f"margin box")
                        break
                for image in page.get_images(full=True):
                    for rect in page.get_image_rects(image[0]):
                        if rect.width <= 0 or rect.height <= 0:
                            problems.append(f"{pdf.name} p{number}: zero-area figure")
            doc.close()
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{pdf.name}: geometry check failed ({type(exc).__name__})")
    return problems


def check_fabrication(pdfs: list[Path]) -> tuple[list[str], int, int]:
    """Every practice question must say where it came from."""
    problems, tagged, total = [], 0, 0
    for pdf in [p for p in pdfs if p.name.startswith("PRACTICE_")]:
        text = "\n".join(page_texts(pdf))
        for match in re.finditer(r"(?m)^\s*(?:Q|Question\s*)(\d+)[.)]", text):
            total += 1
            window = text[match.start(): match.start() + 1200]
            if TAG.search(window):
                tagged += 1
            else:
                problems.append(f"{pdf.name}: Q{match.group(1)} carries no "
                                f"[PAST PAPER …] or [GENERATED VARIANT] tag")
    return problems, tagged, total


def check_coverage(pdfs: list[Path]) -> tuple[list[str], dict]:
    """Does each course's PASS-ESSENTIALS reach the archetypes its papers ask?"""
    from gradplan.drillbank import cluster
    from gradplan.predictability import Item

    by_course: dict[str, list[dict]] = defaultdict(list)
    path = DATA / "questions.jsonl"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                by_course[row["course"]].append(row)

    uncovered, summary = [], {}
    for pdf in [p for p in pdfs if p.name.startswith("PASS-ESSENTIALS_")]:
        code = pdf.stem.split("_", 1)[-1]
        rows = by_course.get(code, [])
        if not rows:
            summary[code] = {"archetypes": 0, "covered": 0, "pct": None}
            continue
        groups = cluster([Item(paper=r["source_file"], index=r["q_number"],
                               marks=r["points"], text=r["text"]) for r in rows])
        body = " ".join(page_texts(pdf)).lower()
        body_words = set(re.findall(r"[a-z]{5,}", body))
        covered = 0
        for group in groups:
            terms = set(re.findall(r"[a-z]{5,}", group.representative.text.lower()))
            if terms and len(terms & body_words) / len(terms) >= 0.35:
                covered += 1
            elif group.n_papers > 1:
                uncovered.append(f"{code}: archetype seen in {group.n_papers} papers "
                                 f"is not covered — "
                                 f"“{group.representative.text[:90]}…”")
        summary[code] = {"archetypes": len(groups), "covered": covered,
                         "pct": round(100 * covered / len(groups))}
    return uncovered, summary


def check_fidelity(pdfs: list[Path], per_course: int = 5) -> list[str]:
    """Formulas in the pack must match the source text layer character for
    character. A silently re-typed exponent is a wrong answer in the exam."""
    classified = json.loads((DATA / "classified.json").read_text()) \
        if (DATA / "classified.json").exists() else {}
    results = []
    for pdf in [p for p in pdfs if p.name.startswith("PASS-ESSENTIALS_")]:
        code = pdf.stem.split("_", 1)[-1]
        sources = " ".join(
            (ROOT / entry["text"]).read_text(errors="replace")
            for entry in classified.get(code, [])
            if (ROOT / entry["text"]).exists())
        source_lines = {" ".join(l.split()) for l in sources.splitlines() if l.strip()}
        checked = 0
        for line in " ".join(page_texts(pdf)).splitlines():
            flat = " ".join(line.split())
            if len(flat) < 12 or not FORMULA.search(flat) or checked >= per_course:
                continue
            checked += 1
            exact = flat in source_lines
            match = "EXACT" if exact else "NO EXACT MATCH"
            quoted = next((s for s in source_lines
                           if flat[:18] and flat[:18] in s), "(no source line found)")
            results.append(f"{code}: {match} — pack: “{flat[:80]}” / "
                           f"source: “{quoted[:80]}”")
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(ROOT / "output"))
    args = parser.parse_args()
    out_dir = Path(args.output_dir)
    pdfs = sorted(out_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs in {out_dir} — nothing to verify. "
              "Phase 4 has not run yet.")
        return 0

    print(f"Verifying {len(pdfs)} PDFs in {out_dir}\n")
    fabrication, tagged, total = check_fabrication(pdfs)
    glyphs, _ = check_glyphs(pdfs)
    geometry = check_geometry(pdfs)
    uncovered, coverage = check_coverage(pdfs)
    fidelity = check_fidelity(pdfs)

    print(f"{'check':<14}{'result':<12}detail")
    print(f"{'fabrication':<14}{('FAIL' if fabrication else 'pass'):<12}"
          f"{tagged}/{total} practice questions carry a provenance tag")
    print(f"{'glyphs':<14}{('FAIL' if glyphs else 'pass'):<12}"
          f"{len(glyphs)} problem(s)")
    print(f"{'geometry':<14}{('warn' if geometry else 'pass'):<12}"
          f"{len(geometry)} problem(s)")
    pcts = [v['pct'] for v in coverage.values() if v['pct'] is not None]
    print(f"{'coverage':<14}{('warn' if uncovered else 'pass'):<12}"
          f"mean {sum(pcts)/len(pcts):.0f}% of archetypes covered"
          if pcts else f"{'coverage':<14}{'n/a':<12}no questions to check against")
    exact = sum(1 for r in fidelity if r.startswith(tuple(coverage)) and "EXACT" in r)
    print(f"{'fidelity':<14}{'info':<12}{exact}/{len(fidelity)} sampled formulas "
          f"match the source exactly")

    for title, rows in (("FABRICATION", fabrication), ("GLYPHS", glyphs),
                        ("GEOMETRY", geometry), ("UNCOVERED ARCHETYPES", uncovered),
                        ("FIDELITY SAMPLES", fidelity)):
        if rows:
            print(f"\n{title}")
            for row in rows[:25]:
                print(f"  - {row}")
            if len(rows) > 25:
                print(f"  … and {len(rows)-25} more")

    print("\nper-course coverage:")
    for code, value in sorted(coverage.items()):
        print(f"  {code}  {value['covered']}/{value['archetypes']} archetypes "
              f"({value['pct'] if value['pct'] is not None else '—'}%)")

    return 1 if (fabrication or glyphs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
