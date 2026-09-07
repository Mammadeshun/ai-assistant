#!/usr/bin/env python3
"""Fold the student's own archive into the collected corpus.

    python ingest_upload.py <zip-or-folder>

The archive is material collected by hand from course WhatsApp groups: past
papers, photographed exam sheets, and one nested zip of sittings filed by year.
It overlaps the Kiro download and duplicates itself internally (the folder and
the zip inside it hold the same files), so everything is hashed and each
distinct file is kept once.

Routing to a course is by evidence, in order: the filename, then the first page
of text. A file that matches nothing is filed under _unassigned rather than
guessed at - a past paper filed under the wrong course is worse than one left
in a pile, because it corrupts that course's predictability score.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW, DATA = ROOT / "raw", ROOT / "data"

# Filename and content tokens per course code. Drawn from what the archive
# actually contains, not from the full course list.
ROUTES = {
    "509488": (r"tmnlp|text.?min|\btm\b|nlp",
               r"tm ?& ?nlp|tmnlp|text min|natural language|part of speech|"
               r"morpholog|tf.?idf|word2vec|perplexit|lemmatis|tokeni[sz]"),
    "509485": (r"cog.?psy|\bcog\b|cg.?psy", r"cognitive psycholog|working memory|phonological loop|attention"),
    "509493": (r"stat.?mod", r"statistical modelling|linear model|glm|residual deviance"),
    "509481": (r"calculus|analisi", r"calculus|supremum|infimum|derivative|integral"),
    "510109": (r"probab|statistical.?infer", r"probability|random variable|estimator|confidence interval"),
    "509483": (r"comp.?logic|logic", r"herbrand|skolem|resolution|satisfiab"),
    "509477": (r"comp.?prog|algorithm|data.?struct", r"algorithm|complexity|linked list|binary tree|python"),
    "509478": (r"\bkrr\b|knowledge.?repr", r"knowledge representation|ontolog|description logic|owl"),
    "509492": (r"quantum|physics", r"quantum|hamiltonian|wavefunction|hilbert space|qubit"),
    "509486": (r"machine.?learn|\bml\b|neural|deep", r"neural network|gradient descent|overfit|backpropagat"),
    "509519": (r"ethic|\blaw\b", r"ethics|gdpr|regulation|liability|fairness"),
    "509495": (r"data.?min", r"data mining|apriori|clustering|association rule"),
    "509496": (r"info.?retr|\bir\b|recommend", r"information retrieval|recommender|precision.{0,6}recall|inverted index"),
    "510638": (r"web.?social|social.?media", r"complex network|centrality|assortativ|small world"),
    "509487": (r"fuzzy|evolution", r"fuzzy|membership function|genetic algorithm"),
    "509494": (r"brain.?model", r"brain|neuron|hodgkin|spiking"),
    "504703": (r"computer.?vision|\bcv\b", r"computer vision|convolution|image segmentation"),
    "504464": (r"organi[sz]ation", r"organization theory|organizational structure|daft"),
    "509498": (r"marketing|comm.{0,4}market", r"marketing|brand|campaign|customer segment"),
    "509521": (r"lab.?of.?ml|lab.?ml", r"laboratory|notebook|colab"),
}


def head_text(path: Path) -> str:
    """Enough text to identify the course. Photographed sheets get OCR: a
    phone picture of an exam paper has no text layer, and without OCR every
    one of them lands in _unassigned."""
    if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        try:
            done = subprocess.run(["tesseract", str(path), "stdout", "-l", "ita+eng"],
                                  capture_output=True, text=True, timeout=120)
            return done.stdout[:6000].lower()
        except (subprocess.TimeoutExpired, OSError):
            return ""
    if path.suffix.lower() != ".pdf":
        return ""
    out = path.with_suffix(".probe.txt")
    try:
        subprocess.run(["pdftotext", "-l", "2", "-layout", str(path), str(out)],
                       capture_output=True, timeout=90)
        body = out.read_text(errors="replace")[:6000] if out.exists() else ""
    except (subprocess.TimeoutExpired, OSError):
        body = ""
    out.unlink(missing_ok=True)
    return body.lower()


def route(path: Path, text: str) -> tuple[str | None, str]:
    # OCR wraps lines mid-phrase, so "Natural Language Processing" arrives as
    # "natural\nlanguage processing" and a pattern with a literal space never
    # fires. Collapse whitespace before matching anything.
    text = re.sub(r"\s+", " ", text)
    name = re.sub(r"\s+", " ", path.name.lower())
    for code, (by_name, _) in ROUTES.items():
        if re.search(by_name, name):
            return code, f"filename matches /{by_name}/"
    for code, (_, by_text) in ROUTES.items():
        found = re.search(by_text, text)
        if found:
            return code, f"first pages contain {found.group(0)!r}"
    return None, "no filename or content match"


def expand(source: Path, into: Path) -> None:
    """Unpack recursively; nested zips are how the archive files by year."""
    into.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, into, dirs_exist_ok=True)
    else:
        with zipfile.ZipFile(source) as archive:
            archive.extractall(into)
    for _ in range(3):
        nested = [p for p in into.rglob("*.zip")]
        if not nested:
            break
        for zipped in nested:
            target = zipped.with_suffix("")
            try:
                with zipfile.ZipFile(zipped) as archive:
                    archive.extractall(target)
            except zipfile.BadZipFile:
                pass
            zipped.unlink()


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("usage: ingest_upload.py <zip-or-folder>")
    staging = RAW / "_student_upload" / "_expanded"
    if staging.exists():
        shutil.rmtree(staging)
    expand(Path(sys.argv[1]), staging)

    folders = {c.name.split("-")[0]: c for c in RAW.glob("[0-9]*")}
    names = {a["code"]: a["name"] for a in
             json.loads((DATA / "esse3.json").read_text())["remaining"]}

    seen: dict[str, Path] = {}
    manifest, unassigned, duplicates = [], 0, 0
    for path in sorted(p for p in staging.rglob("*") if p.is_file()):
        if path.suffix.lower() not in {".pdf", ".jpg", ".jpeg", ".png", ".txt",
                                       ".docx", ".doc", ".pptx", ".csv", ".ipynb"}:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen:
            duplicates += 1
            continue
        seen[digest] = path
        code, why = route(path, head_text(path))
        if code is None:
            target_dir = RAW / "_unassigned"
            unassigned += 1
        else:
            base = folders.get(code)
            if base is None:
                base = RAW / f"{code}-{re.sub(r'[^0-9A-Za-z]+','-',names.get(code,'course'))[:40]}"
                folders[code] = base
            target_dir = base / "_student"
        target_dir.mkdir(parents=True, exist_ok=True)
        # Keep the year folder the archive filed it under; it is the exam date.
        parent = path.parent.name
        prefix = f"{parent}_" if re.fullmatch(r"20\d\d", parent) else ""
        target = target_dir / f"{prefix}{path.name}"
        shutil.copy2(path, target)
        manifest.append({"source": str(path.relative_to(staging)),
                         "stored": str(target.relative_to(ROOT)),
                         "course": code, "why": why, "sha256": digest,
                         "bytes": target.stat().st_size})

    (DATA / "student_upload.json").write_text(
        json.dumps({"files": manifest, "duplicates_skipped": duplicates},
                   indent=1, ensure_ascii=False))
    shutil.rmtree(staging, ignore_errors=True)

    by_course: dict[str, int] = {}
    for row in manifest:
        by_course[row["course"] or "_unassigned"] = by_course.get(row["course"] or "_unassigned", 0) + 1
    print(f"{len(manifest)} distinct files kept, {duplicates} duplicates skipped")
    for code, count in sorted(by_course.items(), key=lambda kv: -kv[1]):
        label = names.get(code, code) if code != "_unassigned" else "UNASSIGNED"
        print(f"  {code:<12} {label[:44]:<46} {count:>3}")
    if unassigned:
        print(f"\n{unassigned} file(s) could not be routed - left in raw/_unassigned/, "
              "not guessed at.")
    print(f"wrote {DATA/'student_upload.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
