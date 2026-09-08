#!/usr/bin/env python3
"""Turn the downloaded course material into text, figures and questions.

    python extract.py [--only CODE,CODE] [--skip-figures]

Three passes over unipv/raw/:

  text      pdftotext -layout per PDF into <course>/_text/. A PDF that yields
            under 100 characters has no text layer and is marked SCANNED; past
            papers and solutions are then OCRed, slides are not (a scanned deck
            is worth having to look at, not worth an hour of OCR).
  figures   embedded images at their native resolution, re-rendered at 200 DPI
            where the page places them larger than they are; plus a full-page
            200 DPI render of any page that draws vector graphics and embeds no
            image, which is what catches plots and architecture diagrams.
  questions past papers split into individual questions.

Prints counts. Never prints file contents - the point of this stage is that
nothing has to be read by hand.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import fitz  # noqa: E402  PyMuPDF

fitz.TOOLS.mupdf_display_errors(False)

from gradplan.drillbank import _clean, split_paper  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW, DATA = ROOT / "raw", ROOT / "data"

SCANNED_CHARS = 100
# Several courses publish Word and PowerPoint rather than PDF. Converting them
# once means the text and figure passes below have a single input format.
OFFICE_EXT = {".doc", ".docx", ".ppt", ".pptx", ".ppsx", ".pps", ".odt", ".odp",
              ".xls", ".xlsx", ".rtf"}
# Photographed exam sheets. They carry no text layer at all, so without OCR
# they are invisible to classification and contribute no questions - 30 of the
# student's own past papers would simply vanish.
IMAGE_EXT = {".jpg", ".jpeg", ".png"}
FIGURE_DPI = 200
MIN_FIGURE_PT = 60.0        # ignore bullets, rules and logos
TEMPLATE_SHARE = 0.30       # an image on a third of the pages is furniture
MAX_FIGURES_PER_DOC = 80    # a runaway document should not swamp the index

# Classification. Filename first, then first-page text; the filename is usually
# honest and the text settles the rest.
PATTERNS = {
    "SOLUTIONS": r"soluzion|solution|svolgiment|answer.?key|risolt|con.?sol|_sol\b|risposte",
    "PAST_PAPER": (r"appell|prova.?d.?esame|prova.?scritt|compito|esame\d*\b|exam\d*\b|"
                   r"\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|gen|"
                   r"mag|giu|lug|ago|set|ott|dic)[a-z]*\s+20\d\d|"
                   r"esame.?di|past.?paper|mock|simulazione|testo.?esame|tema.?d.?esame|"
                   r"\d{1,2}[-_ .]\d{1,2}[-_ .]\d{2,4}"),
    "ASSIGNMENT": r"assignment|homework|progett|project|consegna|rubric|elaborato|task\d|lab\d",
    "ADMIN": (r"programm|syllabus|regolament|calendari|orari|avvis|modalit|"
              r"info.?cors|presentazione.?cors|bibliograf"),
    "NOTES": r"appunt|dispens|handout|note[s]?\b|summary|riassunt|book|chapter|capitolo",
    "SLIDES": r"slide|lezione|lecture|lez\d|deck|part[e]?\d|modul|week\d|unit\d|cap\d",
}
ORDER = ["SOLUTIONS", "PAST_PAPER", "ASSIGNMENT", "ADMIN", "NOTES", "SLIDES"]
OCR_ROLES = {"PAST_PAPER", "SOLUTIONS"}

DATE = re.compile(r"(\d{1,2})[-_ ./](\d{1,2})[-_ ./](\d{2,4})")
# Papers are very often named by month rather than by number - '19 September
# 2023', 'exam test JULY24', 'esame 5 giugno 2024'.
MONTHS = {m: n for n, names in enumerate(
    [("january", "gennaio", "jan", "gen"), ("february", "febbraio", "feb"),
     ("march", "marzo", "mar"), ("april", "aprile", "apr"),
     ("may", "maggio", "mag"), ("june", "giugno", "jun", "giu"),
     ("july", "luglio", "jul", "lug"), ("august", "agosto", "aug", "ago"),
     ("september", "settembre", "sep", "sept", "set"),
     ("october", "ottobre", "oct", "ott"), ("november", "novembre", "nov"),
     ("december", "dicembre", "dec", "dic")], start=1) for m in names}
MONTH_DATE = re.compile(
    r"\b(?:(\d{1,2})\s*)?(" + "|".join(sorted(MONTHS, key=len, reverse=True))
    + r")\s*(\d{2,4})?\b", re.I)
POINTS = re.compile(r"\b(?:punt[io]|points?|marks?|pt)\s*[:.]?\s*(\d{1,2})|\((\d{1,2})\s*"
                    r"(?:punt[io]|points?|marks?)\)", re.I)


def run(cmd: list[str], timeout: int = 180) -> tuple[int, str]:
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return done.returncode, done.stdout
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 1, repr(exc)


def ocr_image(source: Path, out: Path) -> int:
    """OCR a photographed page. Italian and English: the papers mix both."""
    if out.exists() and out.stat().st_size > 0:
        return len(out.read_text(errors="replace").strip())
    out.parent.mkdir(parents=True, exist_ok=True)
    code, text = run(["tesseract", str(source), "stdout", "-l", "ita+eng"], timeout=180)
    body = text if code == 0 else ""
    out.write_text(body)
    return len(body.strip())


def to_pdf(source: Path, out_dir: Path) -> Path | None:
    """Convert one Office file to PDF, once. Returns the PDF, or None."""
    target = out_dir / (source.stem + ".pdf")
    if target.exists() and target.stat().st_size > 0:
        return target
    out_dir.mkdir(parents=True, exist_ok=True)
    code, _ = run(["soffice", "--headless", "--norestore", "--convert-to", "pdf",
                   "--outdir", str(out_dir), str(source)], timeout=300)
    if code != 0 or not target.exists():
        return None
    return target


def _words(text: str) -> str:
    """Separators to spaces, so word boundaries actually fire.

    '_' '-' and '.' are word characters to a regex engine or sit inside one, so
    /exam\d*\b/ never matches 'exam_test_JULY24.pdf' and
    /\d{1,2}[-_ .]\d{1,2}/ never sees '19 September' in
    '2023_19_September_2023'. Both silently classified 15 past papers as notes.
    This is the third time this bug class has cost real data; it is the same
    normalisation gradplan.drillbank already does.
    """
    return re.sub(r"[_\-.]+", " ", text)


def classify(path: Path, head: str) -> str:
    """SLIDES / NOTES / PAST_PAPER / SOLUTIONS / ASSIGNMENT / ADMIN."""
    # A .ppsx called "Chapter 12" is a deck, not a chapter. The container
    # format is the more reliable signal, so it wins over the filename.
    if path.suffix.lower() in {".ppt", ".pptx", ".ppsx", ".pps", ".odp"}:
        return "SLIDES"
    name = _words(path.name.lower())
    parents = " ".join(_words(p.lower()) for p in path.parts[-3:-1])
    haystack = f"{parents} {name}"
    for role in ORDER:
        if re.search(PATTERNS[role], haystack):
            # A paper filed beside its answers is still a paper unless it says
            # otherwise; check the stronger signal first.
            if role == "PAST_PAPER" and re.search(PATTERNS["SOLUTIONS"], haystack):
                return "SOLUTIONS"
            return role
    front = head[:1500].lower()
    if re.search(PATTERNS["SOLUTIONS"], front):
        return "SOLUTIONS"
    if re.search(r"prova.?scritt|appello|compito|esercizi[oz]|punti\s*\d|durata|"
                 r"tempo a disposizione", front):
        return "PAST_PAPER"
    if re.search(PATTERNS["ADMIN"], front):
        return "ADMIN"
    return "SLIDES" if head.count("\f") > 8 else "NOTES"


def exam_date(path: Path, head: str) -> str | None:
    for source in (_words(path.name), head[:600]):
        found = DATE.search(source)
        if not found:
            named = MONTH_DATE.search(source)
            if not named:
                continue
            day = named.group(1) or "1"
            month = str(MONTHS[named.group(2).lower()])
            # The archive files sittings under a year folder, and that prefix
            # survives into the name, so use it when the name carries no year.
            year = named.group(3) or (re.search(r"\b(20\d\d)\b", source) or ["", ""])[1]
            if not year:
                continue
        else:
            day, month, year = found.groups()
        if not (1 <= int(day) <= 31 and 1 <= int(month) <= 12):
            continue
        year = int(year)
        year += 2000 if year < 100 else 0
        if 2015 <= year <= 2027:
            return f"{year:04d}-{int(month):02d}-{int(day):02d}"
    return None


def extract_text(pdf: Path, out: Path) -> tuple[int, bool]:
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        code, _ = run(["pdftotext", "-layout", str(pdf), str(out)])
        if code != 0 or not out.exists():
            out.write_text("")
    body = out.read_text(errors="replace")
    return len(body.strip()), len(body.strip()) < SCANNED_CHARS


def ocr(pdf: Path, out: Path) -> int:
    """OCR a scanned paper. Italian plus English - the papers mix both."""
    side = pdf.with_suffix(".ocr.pdf")
    code, _ = run(["ocrmypdf", "-l", "ita+eng", "--force-ocr", "--optimize", "0",
                   "--quiet", str(pdf), str(side)], timeout=600)
    if code != 0 or not side.exists():
        return 0
    run(["pdftotext", "-layout", str(side), str(out)])
    side.unlink(missing_ok=True)
    return len(out.read_text(errors="replace").strip()) if out.exists() else 0


def caption_below(page, box) -> str:
    """The nearest text line under a figure, which is usually its caption."""
    best, gap = "", 1e9
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        if y0 < box.y1 - 2 or x1 < box.x0 - 20 or x0 > box.x1 + 20:
            continue
        if y0 - box.y1 < gap:
            gap, best = y0 - box.y1, " ".join(text.split())[:200]
    return best if gap < 90 else ""


def extract_figures(pdf: Path, out_dir: Path, stem: str,
                    render_vector_pages: bool = True) -> list[dict]:
    """Embedded images plus rendered vector pages.

    An image is kept at its own resolution when that already exceeds 200 DPI at
    the size the page draws it, and re-rendered from the page otherwise - an
    80x60 logo blown up to half a page is useless either way, but a 200 DPI clip
    of the page is at least readable.
    """
    try:
        doc = fitz.open(pdf)
    except Exception:  # noqa: BLE001
        return []
    figures: list[dict] = []
    counts: Counter[str] = Counter()
    staged: list[tuple[str, bytes, dict]] = []
    zoom = FIGURE_DPI / 72.0

    for number in range(len(doc)):
        page = doc[number]
        images = page.get_images(full=True)
        placed = 0
        for xref, *_ in images:
            try:
                boxes = page.get_image_rects(xref)
            except Exception:  # noqa: BLE001
                continue
            for box in boxes:
                if box.width < MIN_FIGURE_PT or box.height < MIN_FIGURE_PT:
                    continue
                placed += 1
                try:
                    info = doc.extract_image(xref)
                    native_dpi = info["width"] / max(box.width / 72.0, 1e-6)
                    if native_dpi >= FIGURE_DPI:
                        blob, ext = info["image"], info["ext"]
                    else:
                        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=box)
                        blob, ext = pix.tobytes("png"), "png"
                except Exception:  # noqa: BLE001
                    continue
                digest = hashlib.sha256(blob).hexdigest()[:16]
                counts[digest] += 1
                staged.append((digest, blob, {
                    "source_pdf": str(pdf.relative_to(ROOT)),
                    "page": number + 1,
                    "bbox": [round(v, 1) for v in (box.x0, box.y0, box.x1, box.y1)],
                    "caption_guess": caption_below(page, box),
                    "ext": ext,
                }))
        # A page that draws but embeds nothing is a vector plot or diagram -
        # except in a slide deck, where every slide is drawn shapes and
        # rendering all of them just reproduces the deck.
        if render_vector_pages and not placed and page.get_drawings():
            spans = [b for b in page.get_text("blocks")]
            if len(page.get_drawings()) > 8 or len(spans) < 25:
                try:
                    blob = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
                except Exception:  # noqa: BLE001
                    continue
                digest = hashlib.sha256(blob).hexdigest()[:16]
                counts[digest] += 1
                staged.append((digest, blob, {
                    "source_pdf": str(pdf.relative_to(ROOT)),
                    "page": number + 1,
                    "bbox": [round(v, 1) for v in page.rect],
                    "caption_guess": "[full-page render: vector drawing, no embedded image]",
                    "ext": "png",
                }))
    pages = max(len(doc), 1)
    doc.close()

    out_dir.mkdir(parents=True, exist_ok=True)
    written: set[str] = set()
    for digest, blob, meta in staged[:MAX_FIGURES_PER_DOC]:
        # A logo repeated on every slide is template furniture, not a figure.
        if counts[digest] > max(3, pages * TEMPLATE_SHARE) or digest in written:
            continue
        written.add(digest)
        name = f"{stem}-p{meta['page']:03d}-{digest[:8]}.{meta['ext']}"
        (out_dir / name).write_bytes(blob)
        meta["png"] = name
        meta.pop("ext")
        figures.append(meta)
    return figures


def split_questions(course: str, path: Path, body: str, role: str,
                    has_solution: bool) -> list[dict]:
    items = split_paper(_clean(body), path.name)
    when = exam_date(path, body[:800])
    out = []
    for index, item in enumerate(items, start=1):
        text = item.text.strip()
        if len(text) < 25:
            continue
        marks = item.marks
        if marks is None:
            found = POINTS.search(text)
            marks = int(found.group(1) or found.group(2)) if found else None
        out.append({
            "course": course,
            "source_file": str(path.relative_to(ROOT)),
            "exam_date": when,
            "q_number": index,
            "text": text[:4000],
            "points": marks,
            "has_solution": has_solution,
            "role": role,
        })
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated course codes")
    parser.add_argument("--skip-figures", action="store_true")
    args = parser.parse_args()
    only = set(args.only.split(",")) if args.only else None

    DATA.mkdir(parents=True, exist_ok=True)
    classified: dict[str, list[dict]] = {}
    questions: list[dict] = []
    rows = []

    for folder in sorted(RAW.glob("[0-9]*")):
        code = folder.name.split("-")[0]
        if only and code not in only:
            continue
        # Convert Office documents first so everything downstream sees a PDF.
        converted: dict[Path, Path] = {}
        office = sorted(p for p in folder.rglob("*")
                        if p.is_file() and p.suffix.lower() in OFFICE_EXT
                        and "_converted" not in p.parts)
        for source in office:
            made = to_pdf(source, folder / "_converted")
            if made is not None:
                converted[made] = source
        pdfs = sorted(p for p in folder.rglob("*.pdf") if ".ocr." not in p.name)
        others = sorted(p for p in folder.rglob("*")
                        if p.is_file() and p.suffix.lower() in
                        {".txt", ".md", ".csv", ".py", ".ipynb", ".smt2"}
                        and "_text" not in p.parts)
        text_dir, fig_dir = folder / "_text", folder / "_figures"
        entries, figures = [], []
        scanned = ocred = 0

        for pdf in pdfs:
            rel = pdf.relative_to(folder)
            out = text_dir / rel.with_suffix(".txt")
            chars, is_scanned = extract_text(pdf, out)
            head = out.read_text(errors="replace")[:4000]
            origin = converted.get(pdf, pdf)
            role = classify(origin, head)
            if is_scanned:
                scanned += 1
                if role in OCR_ROLES:
                    got = ocr(pdf, out)
                    if got > chars:
                        chars, ocred = got, ocred + 1
                        head = out.read_text(errors="replace")[:4000]
                        role = classify(origin, head)
            entries.append({
                "path": str(pdf.relative_to(ROOT)),
                "original": str(origin.relative_to(ROOT)),
                "converted": pdf in converted,
                "text": str(out.relative_to(ROOT)),
                "role": role,
                "chars": chars,
                "scanned": is_scanned,
                "exam_date": exam_date(origin, head),
            })
            if not args.skip_figures and role != "ADMIN":
                figures += extract_figures(pdf, fig_dir, pdf.stem[:40],
                                           render_vector_pages=role != "SLIDES")

        # Photographed papers: OCR, classify, and keep the photo itself as the
        # figure - the picture of the page is the artefact worth printing.
        images = sorted(p for p in folder.rglob("*")
                        if p.is_file() and p.suffix.lower() in IMAGE_EXT
                        and "_figures" not in p.parts)
        for image in images:
            out = text_dir / image.relative_to(folder).with_suffix(".txt")
            chars = ocr_image(image, out)
            head = out.read_text(errors="replace")[:4000]
            role = classify(image, head)
            entries.append({
                "path": str(image.relative_to(ROOT)),
                "original": str(image.relative_to(ROOT)),
                "converted": False,
                "text": str(out.relative_to(ROOT)),
                "role": role,
                "chars": chars,
                "scanned": True,
                "ocr": True,
                "exam_date": exam_date(image, head),
            })
            if chars >= 120:
                ocred += 1
                figures.append({
                    "png": str(image.relative_to(folder)),
                    "source_pdf": str(image.relative_to(ROOT)),
                    "page": 1,
                    "bbox": None,
                    "caption_guess": "[photographed exam sheet, supplied by the student]",
                })

        for other in others:
            body = other.read_text(errors="replace")[:200000]
            entries.append({
                "path": str(other.relative_to(ROOT)),
                "text": str(other.relative_to(ROOT)),
                "role": classify(other, body[:3000]),
                "chars": len(body),
                "scanned": False,
                "exam_date": exam_date(other, body[:600]),
            })

        keys = {Path(e["path"]).stem.lower() for e in entries if e["role"] == "SOLUTIONS"}
        papers = 0
        for entry in entries:
            if entry["role"] not in ("PAST_PAPER", "SOLUTIONS") or entry["chars"] < 120:
                continue
            body = Path(ROOT / entry["text"]).read_text(errors="replace")
            if entry["role"] == "PAST_PAPER":
                papers += 1
                stem = Path(entry["path"]).stem.lower()
                paired = any(stem in k or k.startswith(stem[:12]) for k in keys)
                questions += split_questions(code, ROOT / entry["path"], body,
                                             entry["role"], paired)

        if figures:
            (fig_dir / "index.json").write_text(json.dumps(figures, indent=1,
                                                           ensure_ascii=False))
        classified[code] = entries
        rows.append({
            "code": code, "name": folder.name.split("-", 1)[-1].replace("-", " ")[:34],
            "files": len(entries), "scanned": scanned, "ocred": ocred,
            "figures": len(figures), "papers": papers, "converted": len(converted),
            "questions": sum(1 for q in questions if q["course"] == code),
            "roles": Counter(e["role"] for e in entries),
        })
        print(f"  {code} done: {len(entries)} files, {len(figures)} figures, "
              f"{papers} papers")

    (DATA / "classified.json").write_text(json.dumps(classified, indent=1, ensure_ascii=False))
    with (DATA / "questions.jsonl").open("w") as handle:
        for question in questions:
            handle.write(json.dumps(question, ensure_ascii=False) + "\n")

    print(f"\n{'code':<8}{'course':<36}{'files':>6}{'conv':>5}{'scan':>6}{'ocr':>5}"
          f"{'figs':>6}{'papers':>7}{'quest':>7}  roles")
    for row in sorted(rows, key=lambda r: -r["questions"]):
        roles = " ".join(f"{k[:4]}={v}" for k, v in row["roles"].most_common(4))
        print(f"{row['code']:<8}{row['name']:<36}{row['files']:>6}{row['converted']:>5}"
              f"{row['scanned']:>6}{row['ocred']:>5}{row['figures']:>6}{row['papers']:>7}"
              f"{row['questions']:>7}  {roles}")
    print(f"\n{len(rows)} courses | {sum(r['files'] for r in rows)} files | "
          f"{sum(r['figures'] for r in rows)} figures | "
          f"{sum(r['papers'] for r in rows)} past papers | {len(questions)} questions")
    print(f"wrote {DATA/'classified.json'} and {DATA/'questions.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
