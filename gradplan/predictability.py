"""How predictable is each exam?

Counting past papers says nothing. What decides preparation time is whether
five years of papers are the same handful of exercises with different numbers,
or five years of genuinely new problems. This module answers that from the
papers themselves.

Method, per course:

1. split each paper into individually-marked items;
2. classify each item into a topic using an explicit, inspectable keyword map;
3. build a topic x paper matrix weighted by marks;
4. derive recurrence, structure stability, novelty and the minimum topic set
   that covers a target share of the marks.

Novelty is measured, not asserted: two items on the same topic are compared
after stripping all digits. A high similarity means the problem is a template
being renumbered; a low one means it was rewritten.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Iterable

# Marks attached to an item: "(10 points)", "[2 points]", "max 31 points".
MARK_PATTERNS = [
    re.compile(r"\[\s*(\d{1,2}(?:[.,]\d)?)\s*point", re.I),
    re.compile(r"\(\s*(\d{1,2}(?:[.,]\d)?)\s*point", re.I),
    re.compile(r"(\d{1,2}(?:[.,]\d)?)\s*point", re.I),
    re.compile(r"\[\s*(\d{1,2})\s*(?:punti|p)\.?\s*\]", re.I),
    # KRR style: 'Exercise 1. Boolean Functions (7)' - marks bare in brackets
    # right after the exercise title, with no word 'points' anywhere.
    re.compile(
        r"^(?:Exercise|Esercizio|Question|Questione)\s+\d{1,2}\.?[^(\n]{0,60}\((\d{1,2})\)",
        re.I,
    ),
]

# Where a new exercise starts.
ITEM_START = re.compile(
    r"(?:^|\s)(?:"
    r"Question\s+\d{1,2}|Questione\s+\d{1,2}|Exercise\s+\d{1,2}|Esercizio\s+\d{1,2}|"
    r"Problem\s+\d{1,2}|Es\.\s*\d{1,2}|"
    r"\d{1,2}[a-z]?\)\s|\(\d{1,2}\)\s"
    r")",
    re.I,
)


@dataclass
class Item:
    """One marked exercise on one paper."""

    paper: str
    index: int
    marks: float | None
    text: str
    topic: str = "unclassified"

    @property
    def weight(self) -> float:
        """Marks where published, otherwise one unit per item.

        Falling back to counting keeps the matrix usable for papers that print
        marks only as a header total; the report says which weighting was used.
        """
        return self.marks if self.marks is not None else 1.0

    @property
    def fingerprint(self) -> str:
        """The item with all numbers removed, for template detection."""
        stripped = re.sub(r"\d+([.,]\d+)?", "#", self.text.lower())
        stripped = re.sub(r"[^a-z#\s]", " ", stripped)
        return re.sub(r"\s+", " ", stripped).strip()


@dataclass
class Paper:
    label: str
    session: str
    items: list[Item] = field(default_factory=list)

    @property
    def total_marks(self) -> float:
        return sum(i.weight for i in self.items)

    @property
    def has_explicit_marks(self) -> bool:
        return any(i.marks is not None for i in self.items)


@dataclass
class Analysis:
    course: str
    papers: list[Paper]
    topics: dict[str, dict[str, float]]  # topic -> paper -> marks
    recurrence: float | None
    structure_stability: str
    novelty_score: float | None
    novelty_examples: list[tuple[str, str, float]]
    min_topic_set: list[tuple[str, float]]
    coverage_of_min_set: float
    weighting: str = "published marks"

    @property
    def n_papers(self) -> int:
        return len(self.papers)

    def to_json(self) -> dict[str, Any]:
        return {
            "course": self.course,
            "n_papers": self.n_papers,
            "weighting": self.weighting,
            "papers": [p.label for p in self.papers],
            "recurrence": self.recurrence,
            "structure_stability": self.structure_stability,
            "novelty_score": self.novelty_score,
            "novelty_examples": [
                {"a": a, "b": b, "similarity": round(s, 3)}
                for a, b, s in self.novelty_examples
            ],
            "min_topic_set": [{"topic": t, "share": round(s, 3)} for t, s in self.min_topic_set],
            "coverage_of_min_set": round(self.coverage_of_min_set, 3),
            "matrix": {t: {p: round(m, 1) for p, m in v.items()} for t, v in self.topics.items()},
        }


def split_items(text: str, paper: str) -> list[Item]:
    """Split a paper into marked items."""
    flat = re.sub(r"[ \t]+", " ", text)
    positions = [m.start() for m in ITEM_START.finditer(flat)]
    if len(positions) < 2:
        return [Item(paper=paper, index=0, marks=extract_marks(flat), text=flat[:4000])]

    items: list[Item] = []
    bounds = positions + [len(flat)]
    for index, (start, end) in enumerate(zip(bounds, bounds[1:])):
        chunk = flat[start:end].strip()
        if len(chunk) < 40:
            continue
        items.append(
            Item(paper=paper, index=index, marks=extract_marks(chunk), text=chunk[:2500])
        )
    return items


def extract_marks(chunk: str) -> float | None:
    for pattern in MARK_PATTERNS:
        found = pattern.search(chunk)
        if found:
            try:
                return float(found.group(1).replace(",", "."))
            except ValueError:
                continue
    return None


def classify(items: Iterable[Item], taxonomy: dict[str, list[str]]) -> None:
    """Assign a topic to each item by counting keyword hits."""
    for item in items:
        low = item.text.lower()
        best, best_score = "unclassified", 0
        for topic, keywords in taxonomy.items():
            score = sum(low.count(k.lower()) for k in keywords)
            if score > best_score:
                best, best_score = topic, score
        item.topic = best


def _novelty(items: list[Item]) -> tuple[float | None, list[tuple[str, str, float]]]:
    """Similarity between same-topic items from different papers.

    1.0 means the same template renumbered; near 0 means rewritten.
    """
    by_topic: dict[str, list[Item]] = {}
    for item in items:
        if item.topic != "unclassified":
            by_topic.setdefault(item.topic, []).append(item)

    scores: list[float] = []
    examples: list[tuple[str, str, float]] = []
    for topic, group in by_topic.items():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a.paper == b.paper:
                    continue
                ratio = SequenceMatcher(None, a.fingerprint[:600], b.fingerprint[:600]).ratio()
                scores.append(ratio)
                examples.append((f"{a.paper}: {a.text[:150]}", f"{b.paper}: {b.text[:150]}", ratio))
    if not scores:
        return None, []
    examples.sort(key=lambda x: -x[2])
    # One high-similarity pair and one low, so both cases are visible.
    picked = [examples[0]] if examples else []
    if len(examples) > 1:
        picked.append(examples[-1])
    return statistics.mean(scores), picked


def analyse(
    course: str,
    papers: list[Paper],
    taxonomy: dict[str, list[str]],
    target_coverage: float = 0.60,
) -> Analysis:
    all_items = [i for p in papers for i in p.items]
    classify(all_items, taxonomy)

    topics: dict[str, dict[str, float]] = {}
    for item in all_items:
        topics.setdefault(item.topic, {}).setdefault(item.paper, 0.0)
        topics[item.topic][item.paper] += item.weight

    # recurrence: share of the newest paper's marks on topics that appeared in
    # at least half of the earlier papers.
    recurrence = None
    if len(papers) >= 3:
        newest, prior = papers[-1], papers[:-1]
        threshold = len(prior) / 2
        recurring = {
            topic
            for topic, per_paper in topics.items()
            if topic != "unclassified"
            and sum(1 for p in prior if per_paper.get(p.label, 0) > 0) >= threshold
        }
        covered = sum(i.weight for i in newest.items if i.topic in recurring)
        total = newest.total_marks
        recurrence = (covered / total) if total else None

    counts = [len(p.items) for p in papers]
    if len(set(counts)) == 1:
        stability = f"identical skeleton: every paper has {counts[0]} items"
    elif counts and (max(counts) - min(counts)) <= 2:
        stability = f"stable: {min(counts)}-{max(counts)} items per paper"
    else:
        stability = f"variable: {min(counts)}-{max(counts)} items per paper"

    novelty_score, novelty_examples = _novelty(all_items)

    total_marks = sum(sum(v.values()) for t, v in topics.items() if t != "unclassified")
    ranked = sorted(
        ((t, sum(v.values())) for t, v in topics.items() if t != "unclassified"),
        key=lambda x: -x[1],
    )
    min_set: list[tuple[str, float]] = []
    running = 0.0
    for topic, marks in ranked:
        if total_marks and running / total_marks >= target_coverage:
            break
        min_set.append((topic, marks / total_marks if total_marks else 0))
        running += marks

    explicit = sum(1 for p in papers if p.has_explicit_marks)
    weighting = (
        "published marks" if explicit >= len(papers) * 0.6
        else f"item count ({explicit}/{len(papers)} papers print per-item marks)"
    )

    return Analysis(
        course=course,
        papers=papers,
        weighting=weighting,
        topics=topics,
        recurrence=recurrence,
        structure_stability=stability,
        novelty_score=novelty_score,
        novelty_examples=novelty_examples,
        min_topic_set=min_set,
        coverage_of_min_set=(running / total_marks) if total_marks else 0.0,
    )
