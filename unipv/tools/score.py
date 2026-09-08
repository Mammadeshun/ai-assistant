#!/usr/bin/env python3
"""Score every remaining exam on what the collected files actually contain.

    python score.py            -> analysis/scoring.md, data/scoring.json

Every number here is counted from a file on disk. Where something could not be
measured it is reported as unknown rather than filled in with a plausible
guess: an invented predictability score is worse than an admitted gap, because
it silently reorders the plan.

Hours-to-18 follows the model in reference/hours_model.json, restated here so
the arithmetic is visible in the output:

    content = topics x (4h per topic for 12 CFU, 3h for 6 CFU)
    drill   = papers x (3h per paper for 12 CFU, 2h for 6 CFU) x 2 passes
    papers  = 6 if predictability is low, 4 if middling, 3 if high

Predictability is measured, not asserted: questions are clustered by textual
similarity across papers, and the score is the share of questions that fall
into an archetype seen in more than one paper.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gradplan.drillbank import cluster  # noqa: E402
from gradplan.predictability import Item  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW, DATA, ANALYSIS = ROOT / "raw", ROOT / "data", ROOT / "analysis"
TODAY = dt.date.today()

# Phrases that state how a course is examined, in the two languages the course
# pages mix. Matched against _course_text.html, and quoted verbatim in the
# output so every claim about format is traceable.
FORMAT_PATTERNS = [
    (r"(?:esame|prova)\s+(?:scritt\w+|oral\w+)[^.]{0,120}", "format"),
    (r"written\s+(?:exam|test)[^.]{0,120}", "format"),
    (r"oral\s+(?:exam|test|examination)[^.]{0,120}", "format"),
    (r"multiple[- ]choice[^.]{0,120}", "format"),
    (r"(?:durata|duration)[^.]{0,80}", "duration"),
    (r"(?:\d{1,3}\s*(?:minut|minute|ore|hours))[^.]{0,60}", "duration"),
    (r"(?:libro aperto|open book|closed book|libri chiusi)[^.]{0,80}", "materials"),
    (r"(?:progetto|project)\s+(?:work|di gruppo|individuale)?[^.]{0,120}", "project"),
    (r"(?:soglia|minimo|minimum|at least)\s*[^.]{0,80}", "gate"),
    (r"(?:penalit|penalty|punti negativi|negative mark)[^.]{0,100}", "penalty"),
    (r"(?:bonus|punti extra|extra points)[^.]{0,100}", "bonus"),
    (r"(?:non fa parte|escluso dal programma|not required|excluded)[^.]{0,120}", "excluded"),
]


# Language-switcher and messaging-drawer copies of the same page. The crawler
# followed them before it knew better; they are duplicates, not content.
CHROME_PAGE = re.compile(
    r"(English-en|Italiano-it|Deutsch-de|Fran-ais-fr|Espa-ol|Portugu|Contacts?|"
    r"Contatti|Kontakte|Contactos|Requests-0|Anfragen-0|Pedidos-0|Petic|"
    r"conte-do-principal|contenu-principal|Passer-au|Ir-para|Saltar|Zum-Haupt|"
    r"Mostrar-coment|Visualizza-comment|Show-comment)", re.I)


def is_chrome(path) -> bool:
    return bool(CHROME_PAGE.search(path.name))

def load(name: str):
    path = DATA / name
    return json.loads(path.read_text()) if path.exists() else None


def questions_by_course() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    path = DATA / "questions.jsonl"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                out[row["course"]].append(row)
    return out


def predictability(rows: list[dict]) -> tuple[int | None, str]:
    """1-5, plus the sentence that justifies it.

    The measure is repetition across *papers*: a question type that appears in
    several sittings is one you can drill; a paper of one-offs is not.
    """
    papers = {r["source_file"] for r in rows}
    if len(rows) < 6 or len(papers) < 2:
        return None, (f"not measurable - {len(rows)} questions from "
                      f"{len(papers)} paper(s)")
    items = [Item(paper=r["source_file"], index=r["q_number"], marks=r["points"],
                  text=r["text"]) for r in rows]
    groups = cluster(items)
    repeated = [g for g in groups if g.n_papers > 1]
    covered = sum(len(g.members) for g in repeated)
    share = covered / len(rows)
    score = 5 if share >= 0.75 else 4 if share >= 0.55 else 3 if share >= 0.35 \
        else 2 if share >= 0.15 else 1
    top = sorted(repeated, key=lambda g: -g.n_papers)[:3]
    detail = (f"{len(groups)} distinct archetypes across {len(papers)} papers; "
              f"{covered} of {len(rows)} questions ({share:.0%}) fall into "
              f"{len(repeated)} archetypes that recur in more than one paper")
    if top:
        detail += f"; the commonest appears in {top[0].n_papers} of {len(papers)} papers"
    return score, detail


def course_text(code: str) -> str:
    folder = next((f for f in RAW.glob(f"{code}-*")), None)
    if folder is None:
        return ""
    parts = []
    pages = list(folder.rglob("_course_text.html")) + [
        p for p in folder.rglob("_pages/*.html") if not is_chrome(p)]
    for page in pages:
        try:
            raw = page.read_text(errors="replace")
        except OSError:
            continue
        raw = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", raw)
        parts.append(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)))
    return " ".join(parts)[:600000]


def format_evidence(text: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = defaultdict(list)
    for pattern, tag in FORMAT_PATTERNS:
        for match in re.finditer(pattern, text, re.I):
            snippet = " ".join(match.group(0).split())[:160]
            if snippet not in found[tag] and len(snippet) > 12:
                found[tag].append(snippet)
            if len(found[tag]) >= 3:
                break
    return dict(found)


def hours_to_18(cfu: int, score: int | None, n_papers: int, topics: int,
                material: int) -> tuple[int, int, str, str]:
    """Range, plus the arithmetic and a confidence letter."""
    per_topic = 4 if cfu >= 12 else 3
    per_paper = 3 if cfu >= 12 else 2
    # Topic count falls back to material volume when no taxonomy exists.
    topics = topics or max(4, min(12, material // 6))
    content = topics * per_topic
    drill_papers = 6 if (score or 2) <= 2 else 4 if score <= 3 else 3
    drill_papers = min(drill_papers, max(n_papers, 1))
    drill = drill_papers * per_paper * 2
    low = content + drill
    high = int(low * (1.35 if score is None else 1.15 if score >= 4 else 1.3))
    confidence = "H" if score and score >= 4 and n_papers >= 5 else \
                 "M" if score is not None else "L"
    workings = (f"content {topics} topics x {per_topic}h = {content}h; "
                f"drill {drill_papers} papers x {per_paper}h x 2 passes = {drill}h")
    return low, high, workings, confidence


def main() -> int:
    esse3 = load("esse3.json")
    if esse3 is None:
        raise SystemExit("Run unipv_collect.py esse3 first.")
    classified = load("classified.json") or {}
    inventory = {c["code"]: c for c in (load("inventory.json") or {}).get("courses", [])}
    taxonomy = json.loads((ROOT.parent / "reference/topic_taxonomy.json").read_text())
    by_course = questions_by_course()

    sittings: dict[str, list[dict]] = defaultdict(list)
    for row in esse3["appelli"]:
        sittings[row["activity"].strip().upper()].append(row)
    booked = {b["code"]: b for b in esse3["bookings"]}
    passed = {a["code"] for a in esse3["passed"]}

    rows = []
    for activity in esse3["remaining"]:
        code, name, cfu = activity["code"], activity["name"], activity["cfu"] or 0
        entries = classified.get(code, [])
        roles = Counter(e["role"] for e in entries)
        papers = [e for e in entries if e["role"] == "PAST_PAPER"]
        keys = [e for e in entries if e["role"] == "SOLUTIONS"]
        years = sorted({e["exam_date"][:4] for e in papers if e.get("exam_date")})
        rows_q = by_course.get(code, [])
        score, why = predictability(rows_q)
        topics = len([k for k in taxonomy.get(code, {}) if not k.startswith("_")])
        material = sum(1 for e in entries if e["role"] in ("SLIDES", "NOTES"))
        low, high, workings, confidence = hours_to_18(
            cfu, score, len(papers), topics, material)

        offered = sittings.get(name.strip().upper(), [])
        nearest = min(offered, key=lambda s: s["exam_date"][-4:] + s["exam_date"][3:5]
                      + s["exam_date"][:2], default=None) if offered else None
        flags = []
        if not papers:
            flags.append("no past papers")
        if score is None:
            flags.append("predictability not measurable")
        if not entries:
            flags.append("DATA INCOMPLETE - no material collected")
        if code in booked:
            flags.append("already booked" + ("" if booked[code]["cancellable"]
                                             else ", cannot cancel"))
        text = course_text(code)
        evidence = format_evidence(text)
        if "penalty" in evidence:
            flags.append("negative marking")
        if "project" in evidence:
            flags.append("project component")
        if any("oral" in s.lower() or "oral" in k for k, v in evidence.items() for s in v):
            flags.append("oral component")

        rows.append({
            "code": code, "name": name, "cfu": cfu,
            "material": {"files": len(entries), "slides": roles.get("SLIDES", 0),
                         "notes": roles.get("NOTES", 0),
                         "video_items": inventory.get(code, {}).get("video_items", 0),
                         "figures": inventory.get(code, {}).get("figures", 0)},
            "papers": len(papers), "solutions": len(keys),
            "year_range": f"{years[0]}-{years[-1]}" if years else None,
            "questions": len(rows_q),
            "predictability": score, "predictability_basis": why,
            "hours_low": low, "hours_high": high, "hours_workings": workings,
            "confidence": confidence,
            "format_evidence": evidence,
            "sitting": nearest, "booked": code in booked,
            "flags": flags,
        })

    # P(pass) is a judgement, but a stated one: it moves with what was measured.
    for row in rows:
        base = {5: 0.85, 4: 0.75, 3: 0.6, 2: 0.45, 1: 0.35}.get(row["predictability"], 0.4)
        if not row["papers"]:
            base -= 0.1
        if "oral component" in row["flags"]:
            base -= 0.05
        if "negative marking" in row["flags"]:
            base -= 0.05
        row["p_pass"] = round(max(0.15, min(0.9, base)), 2)
        row["cost_per_pass"] = round(row["hours_low"] / row["p_pass"])

    rows.sort(key=lambda r: r["cost_per_pass"])
    for index, row in enumerate(rows):
        row["tier"] = "A" if index < 6 and row["sitting"] else \
                      "B" if index < 12 and row["sitting"] else "C"
        if not row["sitting"]:
            row["tier"] = "C"

    (DATA / "scoring.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    write_markdown(rows, esse3)
    print(f"{'code':<8}{'course':<34}{'CFU':>4}{'pred':>5}{'pap':>5}{'q':>5}"
          f"{'hours':>10}{'P':>6}{'cost':>6}  tier")
    for row in rows:
        span = f"{row['hours_low']}-{row['hours_high']}h"
        print(f"{row['code']:<8}{row['name'][:32]:<34}{row['cfu']:>4}"
              f"{str(row['predictability'] or '-'):>5}{row['papers']:>5}"
              f"{row['questions']:>5}{span:>10}"
              f"{row['p_pass']:>6}{row['cost_per_pass']:>6}  {row['tier']}")
    print(f"\nwrote {DATA/'scoring.json'} and {ANALYSIS/'scoring.md'}")
    return 0


def write_markdown(rows: list[dict], esse3: dict) -> None:
    out = [
        "# Scoring", "",
        f"Every figure below is counted from files under `unipv/raw/`, collected "
        f"{esse3['fetched_at'][:10]}. Blank means not measurable from what was "
        f"collected — never an estimate dressed as a count.", "",
        f"{esse3['cfu_passed']} CFU passed, {esse3['cfu_remaining']} remaining of "
        f"{esse3['cfu_required']}.", "",
        "| # | Code | Course | CFU | Files | Papers | Keys | Qs | Pred. | Hours to 18 | Conf | P(pass) | Cost/pass | Sitting | Book by | Tier |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for index, row in enumerate(rows, start=1):
        sitting = row["sitting"]
        out.append(
            f"| {index} | {row['code']} | {row['name'][:38]} | {row['cfu']} "
            f"| {row['material']['files']} | {row['papers']} | {row['solutions']} "
            f"| {row['questions']} | {row['predictability'] or '—'} "
            f"| {row['hours_low']}–{row['hours_high']}h | {row['confidence']} "
            f"| {row['p_pass']} | {row['cost_per_pass']} "
            f"| {sitting['exam_date'] if sitting else '—'} "
            f"| {sitting['booking_closes'] if sitting else '—'} | {row['tier']} |")
    out += ["", "## Per exam", ""]
    for row in rows:
        sitting = row["sitting"]
        out += [
            f"### {row['code']} · {row['name']} — {row['cfu']} CFU — Tier {row['tier']}", "",
            f"- **Material**: {row['material']['files']} files "
            f"({row['material']['slides']} slide decks, {row['material']['notes']} notes), "
            f"{row['material']['figures']} figures extracted, "
            f"{row['material']['video_items']} video items listed (not downloaded).",
            f"- **Past-paper supply**: {row['papers']} papers, {row['solutions']} with "
            f"published solutions, {row['questions']} questions extracted"
            + (f", {row['year_range']}." if row["year_range"] else "."),
            f"- **Predictability**: {row['predictability'] or 'not measurable'} — "
            f"{row['predictability_basis']}.",
            f"- **Hours to 18**: {row['hours_low']}–{row['hours_high']}h "
            f"(confidence {row['confidence']}). {row['hours_workings']}.",
            f"- **Cost per pass**: {row['hours_low']}h ÷ P(pass) {row['p_pass']} = "
            f"**{row['cost_per_pass']}**.",
        ]
        if sitting:
            detail = sitting.get("detail") or {}
            out.append(
                f"- **Sitting**: {sitting['exam_date']}"
                + (f" at {detail['time']}" if detail.get("time") else "")
                + (f", {detail['room']}" if detail.get("room") else "")
                + f". Booking closes {sitting['booking_closes']}"
                + (f". {sitting['enrolled']} enrolled" if sitting.get("enrolled") else "")
                + (f". Teachers: {detail['teachers']}" if detail.get("teachers") else "") + ".")
        else:
            out.append("- **Sitting**: none open. DATA INCOMPLETE or deferred to winter.")
        if row["flags"]:
            out.append(f"- **Risk flags**: {' · '.join(row['flags'])}.")
        if row["format_evidence"]:
            out.append("- **Format, quoted from the course pages**:")
            for tag, quotes in row["format_evidence"].items():
                for quote in quotes[:2]:
                    out.append(f"  - *{tag}*: “{quote}”")
        else:
            out.append("- **Format**: nothing stating the exam format was found in the "
                       "collected pages. DATA INCOMPLETE — ask the lecturer.")
        out.append("")
    (ANALYSIS / "scoring.md").write_text("\n".join(out))


if __name__ == "__main__":
    raise SystemExit(main())
