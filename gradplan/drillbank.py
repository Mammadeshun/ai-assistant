"""Turn the raw paper archive into something you can actually revise from.

`predictability.py` answers "how much does this exam change?". This module
answers the next question: "so what do I sit down and drill?".

The pipeline, per course:

1. resolve every archived document that belongs to the course, from both the
   module index (mod-resource-<mid>) and the files pulled out of folders
   (file-<course>-<mid>-<name>);
2. extract text, and pair each paper with its published solution where one
   exists - solutions are what make an archive drillable rather than merely
   large;
3. split papers into individually-marked items;
4. cluster items across papers by fingerprint, so the same exercise reappearing
   with different numbers collapses into one *question type*;
5. rank question types by how many distinct papers they appear in.

The ranking is the deliverable. "This exercise has appeared in 9 of 12 papers"
is a revision instruction; "there are 47 past papers" is not.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from .predictability import Item, classify, split_items

LOG = logging.getLogger(__name__)

RAW = Path("data/raw")
MANIFEST = RAW / "manifest.jsonl"

# A document whose name carries one of these is an answer key, not a paper.
SOLUTION_TOKENS = re.compile(
    r"\b(solution|solutions|soluzion\w*|answer|answers|risposte|svolt\w+|"
    r"with\s+solutions|sol\.?)\b",
    re.I,
)

# Documents that are exam material rather than lecture material.
# The trailing `\d*` catches 'Esame1'..'Esame6', which are the Statistical
# Modelling past papers. It deliberately does not catch 'Examples', because a
# word character after the token still fails the boundary.
PAPER_TOKENS = re.compile(
    r"\b(exam|esame|esami|test|prova|mock|appello|assignment|questions?|quiz|"
    r"esonero|simulazione|practice|sample|topics)\d*\b",
    re.I,
)

# Computational Logic names its papers by sitting date alone: '31 1 22A',
# '13 6 2023B'. Without this they are invisible to PAPER_TOKENS.
DATE_NAME = re.compile(r"^\s*\d{1,2}[ ._-]\d{1,2}[ ._-]\d{2,4}\s*[ab]?\s*", re.I)

# Noise that survives PDF extraction and pollutes fingerprints.
BOILERPLATE = re.compile(
    r"(universit[aà]|degli studi|bachelor degree|corso di laurea|"
    r"artificial intelligence|name\s*:|surname\s*:|matricola|student id|"
    r"cognome|nome\s*:)",
    re.I,
)

# Two items are the same question type above this fingerprint similarity.
CLUSTER_THRESHOLD = 0.55


def _words(text: str) -> str:
    """Underscores are word characters, so `\\bexam\\b` never matches
    'Exam_Assignments'. Normalise separators before any token matching."""
    return re.sub(r"[_\-.]+", " ", text)


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@dataclass
class Document:
    """One archived file that belongs to a course."""

    course: str
    name: str
    path: Path
    kind: str
    mid: str = ""
    text: str = ""
    parent: str = ""  # name of the folder module this file came out of

    @property
    def is_activity_stub(self) -> bool:
        """A Moodle activity page carrying no questions.

        A closed quiz still publishes a page - completion criteria, an opening
        window, 'Only 1 attempt available' - and nothing else. Counted as a
        paper it inflates the archive with content that never existed:
        Cognitive Psychology reported 31 papers this way, all of them empty.
        Assignment briefs are deliberately not caught, because for Machine
        Learning the brief *is* the exam.
        """
        text = self.text
        if not text or "Aggregazione dei criteri" not in text:
            return False
        return text.count("?") < 2 and len(text) < 1200

    @property
    def in_exam_folder(self) -> bool:
        return bool(self.parent and PAPER_TOKENS.search(_words(self.parent)))

    @property
    def is_solution(self) -> bool:
        """An answer key, by name - or by being code sitting in an exam folder.

        Computational Logic ships each sitting as a PDF of the questions plus
        the SMT-LIB encodings that answer them. The encodings are the key, not
        the paper: treating them as papers would fabricate question types out
        of z3 source.
        """
        if SOLUTION_TOKENS.search(_words(self.name)):
            return True
        return self.kind == "text" and self.in_exam_folder

    @property
    def looks_like_paper(self) -> bool:
        """Exam material, judged by its own name or the folder it sat in.

        The folder matters: Computational Logic publishes its entire archive as
        bare date-named files inside 'Exam_Assignments', and no amount of
        keyword matching on 'ex2_1A.txt' will ever recognise it as an exam.
        """
        if PAPER_TOKENS.search(_words(self.name)) or DATE_NAME.match(self.name):
            return True
        return self.in_exam_folder

    @property
    def stem(self) -> str:
        """The name with solution wording stripped, for pairing."""
        bare = SOLUTION_TOKENS.sub(" ", _words(self.name))
        bare = re.sub(r"\b(text|testo|only|updated|copy)\b", " ", bare, flags=re.I)
        bare = re.sub(r"[()\[\]{}]", " ", bare)
        return _slug(bare)


@dataclass
class QuestionType:
    """A cluster of items that are the same exercise across papers."""

    topic: str
    members: list[Item] = field(default_factory=list)
    solution: str = ""

    @property
    def papers(self) -> list[str]:
        return sorted({i.paper for i in self.members})

    @property
    def n_papers(self) -> int:
        return len(self.papers)

    @property
    def representative(self) -> Item:
        """The longest member - the most fully-extracted statement of it."""
        return max(self.members, key=lambda i: len(i.text))

    @property
    def typical_marks(self) -> float | None:
        marks = [i.marks for i in self.members if i.marks is not None]
        if not marks:
            return None
        return round(sum(marks) / len(marks), 1)


def load_manifest() -> list[dict[str, Any]]:
    if not MANIFEST.exists():
        raise FileNotFoundError(f"{MANIFEST} missing - nothing has been archived yet")
    return [json.loads(line) for line in MANIFEST.read_text().splitlines() if line.strip()]


def _moodle_text(html: str) -> str:
    """The content of a Moodle page, without 160k characters of chrome.

    Quiz pages are handled first and separately: their questions live in
    `.qtext` blocks with the options in `.answer`, and that structure is worth
    far more than the flattened page - it is the difference between one
    unusable blob and thirty drillable questions.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    questions = soup.select("div.qtext, div.que")
    if questions:
        parts = []
        for number, block in enumerate(questions, start=1):
            text = block.get_text(" ", strip=True)
            if len(text) > 15:
                parts.append(f"Question {number}. {text}")
        if parts:
            return "\n\n".join(parts)

    main = soup.select_one("#region-main") or soup.select_one("[role=main]") or soup.body
    if main is None:
        return ""
    return re.sub(r"\n{3,}", "\n\n", main.get_text("\n", strip=True))


def _pdf_bytes_to_text(blob: bytes) -> str:
    import io

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(blob))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:  # noqa: BLE001
        return ""


def expand_zip(path: Path) -> list[tuple[str, str]]:
    """(member name, text) for the readable members of a zip.

    Computational Logic publishes each sitting as a zip - 'Jan2023.zip',
    'February2023_solutions.zip' - so without this its entire archive is 34
    opaque blobs and the course looks like it has five papers.
    """
    import zipfile

    out: list[tuple[str, str]] = []
    try:
        with zipfile.ZipFile(path) as bundle:
            for member in bundle.namelist():
                if member.endswith("/") or "__MACOSX" in member:
                    continue
                suffix = member.rsplit(".", 1)[-1].lower()
                if suffix not in {"pdf", "txt", "smt2", "md", "py", "tex"}:
                    continue
                try:
                    blob = bundle.read(member)
                except Exception:  # noqa: BLE001
                    continue
                text = (
                    _pdf_bytes_to_text(blob)
                    if suffix == "pdf"
                    else blob.decode("utf-8", "replace")
                )
                if text.strip():
                    out.append((member.rsplit("/", 1)[-1], text))
    except Exception as exc:  # noqa: BLE001
        LOG.debug("unreadable zip %s: %s", path, exc)
    return out


def read_text(path: Path, kind: str) -> str:
    """Extract text, tolerating the malformed PDFs universities publish."""
    if not path.exists():
        return ""
    if kind == "zip":
        return "\n\n".join(text for _, text in expand_zip(path))
    if kind == "pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:  # noqa: BLE001 - one bad PDF must not stop the run
            LOG.debug("unreadable pdf %s: %s", path, exc)
            return ""
    try:
        raw = path.read_text(errors="replace")
    except Exception:  # noqa: BLE001
        return ""
    if kind == "html" or raw.lstrip()[:200].lower().startswith(("<!doctype", "<html")):
        try:
            return _moodle_text(raw)
        except Exception as exc:  # noqa: BLE001
            LOG.debug("unparsable html %s: %s", path, exc)
            return ""
    return raw


def module_course_map(records: list[dict[str, Any]]) -> dict[str, str]:
    """Module id -> course code, read from the archived course pages.

    The papers index only knows the modules it classified as exam material, so
    resolving a downloaded file through it loses everything that sat in an
    unclassified folder. Every Kiro course page names its course in the title
    ('COMPUTATIO 509483_10589_2025') and links every module by id, which gives
    a complete map instead of a partial one.
    """
    from bs4 import BeautifulSoup

    mapping: dict[str, str] = {}
    for record in records:
        if not re.match(r"^course-\d+$", record["label"]) or record["kind"] != "html":
            continue
        path = RAW / record["path"]
        if not path.exists():
            continue
        try:
            markup = path.read_text(errors="replace")
        except Exception:  # noqa: BLE001
            continue
        title = re.search(r"<title>(.*?)</title>", markup, re.S)
        code = re.search(r"\b(\d{6})_\d+_\d{4}\b", title.group(1) if title else "")
        if not code:
            continue
        soup = BeautifulSoup(markup, "html.parser")
        for anchor in soup.select('a[href*="/mod/"][href*="view.php?id="]'):
            found = re.search(r"view\.php\?id=(\d+)", anchor["href"])
            if found:
                mapping.setdefault(found.group(1), code.group(1))
    return mapping


def collect_documents(
    course_names: dict[str, str],
    papers_index: dict[str, list[dict[str, Any]]],
) -> dict[str, list[Document]]:
    """Resolve every archived document to the course it belongs to.

    Two routes reach the same archive: the module index knows the human name of
    a `mod-resource`, and the folder crawl knows the course of a `file-...`
    record. Both are needed - Computational Logic's entire paper archive lives
    inside one folder, and Calculus keeps its per-session tests the same way.
    """
    records = load_manifest()
    by_label = {r["label"]: r for r in records}

    documents: dict[str, list[Document]] = {code: [] for code in course_names}
    seen: set[tuple[str, str]] = set()

    # Route 1: named modules from the papers index.
    for course, entries in papers_index.items():
        if course not in documents:
            continue
        for entry in entries:
            label = f"mod-{entry['kind']}-{entry['mid']}"
            record = by_label.get(label)
            if not record or record["kind"] not in {"pdf", "text", "html"}:
                continue
            key = (course, record["sha256"])
            if key in seen:
                continue
            seen.add(key)
            documents[course].append(
                Document(
                    course=course,
                    name=entry["name"],
                    path=RAW / record["path"],
                    kind=record["kind"],
                    mid=str(entry["mid"]),
                )
            )

    # The folder a file came out of names it. 'Exam_Assignments' is the only
    # thing marking 'ex2_1A.txt' as an exam paper rather than lecture code.
    folder_names = {
        str(entry["mid"]): entry["name"]
        for entries in papers_index.values()
        for entry in entries
    }

    # Route 2: files pulled out of folders. The label's course field is only
    # trustworthy when it is a six-digit code - the fetcher wrote 'unknown'
    # wherever the folder was not in the papers index - so fall back to the
    # module map, which covers every module on every archived course page.
    by_module = module_course_map(records)
    file_label = re.compile(r"^file-(\d{6}|unknown)-([^-]+)-(.+)$")
    for record in records:
        found = file_label.match(record["label"])
        if not found:
            continue
        course, mid, name = found.groups()
        if course == "unknown" or not course.isdigit():
            course = by_module.get(mid, "")
        if course not in documents or record["kind"] not in {"pdf", "text", "zip"}:
            continue
        if name.endswith("-ico") or "favicon" in name:
            continue
        key = (course, record["sha256"])
        if key in seen:
            continue
        seen.add(key)
        documents[course].append(
            Document(
                course=course,
                name=name.replace("-", " "),
                path=RAW / record["path"],
                kind=record["kind"],
                mid=mid,
                parent=folder_names.get(mid, ""),
            )
        )

    return documents


def pair_solutions(documents: Iterable[Document]) -> dict[str, Document]:
    """Map a paper's name-slug to its answer key, where one was published."""
    keys: dict[str, Document] = {}
    for doc in documents:
        if doc.is_solution and doc.text.strip():
            keys.setdefault(doc.stem, doc)
    return keys


def _clean(text: str) -> str:
    lines = [ln for ln in text.splitlines() if not BOILERPLATE.search(ln)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))


# On a multiple-choice paper the stems and the options are both numbered lines,
# and the only thing telling them apart is punctuation: Quantum Physics writes
# '1 What is a sufficient condition...' for the stem and '1. x and a have the
# same dimensions' for the options. Try the unpunctuated form first; fall back
# to the punctuated one for papers that number their stems '1.'.
MCQ_STEM_BARE = re.compile(r"^[ \t]*(\d{1,2})[ \t]+(?=[A-Z(\"'])", re.M)
MCQ_STEM_DOTTED = re.compile(r"^[ \t]*(\d{1,2})[.)][ \t]+(?=[A-Z(\"'])", re.M)


def _ascending_run(starts: list[tuple[int, int]]) -> list[int]:
    """Offsets of a 1,2,3,... run, ignoring numbers that break it."""
    kept: list[int] = []
    expected = 1
    for offset, number in starts:
        if number == expected:
            kept.append(offset)
            expected += 1
    return kept


def split_mcq(text: str, paper: str) -> list[Item]:
    """Split a numbered multiple-choice paper into questions."""
    best: list[int] = []
    for pattern in (MCQ_STEM_BARE, MCQ_STEM_DOTTED):
        starts = [(m.start(), int(m.group(1))) for m in pattern.finditer(text)]
        run = _ascending_run(starts)
        if len(run) > len(best):
            best = run
    if len(best) < 4:
        return []

    bounds = best + [len(text)]
    items: list[Item] = []
    for index, (start, end) in enumerate(zip(bounds, bounds[1:])):
        chunk = text[start:end].strip()
        if len(chunk) < 30:
            continue
        items.append(Item(paper=paper, index=index, marks=None, text=chunk[:2500]))
    return items


def split_paper(text: str, paper: str) -> list[Item]:
    """Split a paper, using whichever strategy actually finds its questions.

    The generic splitter looks for 'Exercise n' / 'Question n' and is right for
    written papers. Multiple-choice papers number bare, and on those it returns
    the whole paper as a single item - which is worse than useless, because it
    silently reports one 'question type' covering 100% of the exam.
    """
    generic = split_items(text, paper)
    mcq = split_mcq(text, paper)
    return mcq if len(mcq) > len(generic) else generic


def cluster(items: list[Item], threshold: float = CLUSTER_THRESHOLD) -> list[QuestionType]:
    """Group items that are the same exercise renumbered.

    Greedy single-pass clustering against cluster representatives. Items are
    only compared within a topic, which keeps this near-linear in practice and
    stops a shared preamble from merging unrelated exercises.
    """
    by_topic: dict[str, list[Item]] = {}
    for item in items:
        by_topic.setdefault(item.topic, []).append(item)

    clusters: list[QuestionType] = []
    for topic, group in by_topic.items():
        # Longest first, so the representative is the best-extracted statement.
        group.sort(key=lambda i: -len(i.text))
        local: list[QuestionType] = []
        for item in group:
            fingerprint = item.fingerprint[:600]
            if not fingerprint:
                continue
            placed = False
            for candidate in local:
                ratio = SequenceMatcher(
                    None, candidate.representative.fingerprint[:600], fingerprint
                ).ratio()
                if ratio >= threshold:
                    candidate.members.append(item)
                    placed = True
                    break
            if not placed:
                local.append(QuestionType(topic=topic, members=[item]))
        clusters.extend(local)

    # Most-recurring first: the number of distinct papers is the drill order.
    clusters.sort(key=lambda c: (-c.n_papers, -(c.typical_marks or 0)))
    return clusters


def build(
    course: str,
    documents: list[Document],
    taxonomy: dict[str, list[str]],
) -> dict[str, Any]:
    """Build one course's drill bank."""
    # A zip is a sitting, not a document: expand it so each member counts as its
    # own paper. Counting the bundle as one item would collapse four years of
    # Computational Logic into a single "question type" seen once.
    expanded: list[Document] = []
    for doc in documents:
        if doc.kind == "zip":
            for member, text in expand_zip(doc.path):
                child = Document(
                    course=doc.course,
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
    documents = expanded

    solutions = pair_solutions(documents)
    papers = [
        d
        for d in documents
        if not d.is_solution
        and d.looks_like_paper
        and not d.is_activity_stub
        and len(d.text.strip()) > 150
    ]

    items: list[Item] = []
    for doc in papers:
        label = f"{doc.name} [{doc.mid}]"
        items.extend(split_paper(_clean(doc.text), label))
    classify(items, taxonomy)

    clusters = cluster(items)
    for group in clusters:
        source = group.representative.paper
        stem = _slug(SOLUTION_TOKENS.sub(" ", source.split(" [")[0]))
        key = solutions.get(stem)
        if key is not None:
            group.solution = key.name

    unsolved = [d.name for d in papers if _slug(d.stem) not in solutions]
    return {
        "course": course,
        "documents_resolved": len(documents),
        "papers_used": [d.name for d in papers],
        "n_papers": len(papers),
        "n_items": len(items),
        "solution_keys": sorted({d.name for d in solutions.values()}),
        "papers_without_a_published_key": unsolved,
        "question_types": [
            {
                "rank": rank,
                "topic": group.topic,
                "seen_in_papers": group.n_papers,
                "share_of_papers": round(group.n_papers / len(papers), 3) if papers else 0,
                "typical_marks": group.typical_marks,
                "papers": group.papers,
                "solution_key": group.solution,
                "statement": group.representative.text[:1200],
            }
            for rank, group in enumerate(clusters, start=1)
            if group.n_papers >= 1
        ],
    }
