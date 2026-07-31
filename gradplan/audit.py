"""Build per-activity evidence dossiers from the archive.

Everything here reads archived files only. The point is that a claim about how
a course is assessed must be traceable to a document, so each extracted fact
carries the source path and the sentence it came from.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from bs4 import BeautifulSoup

from .archive import RawArchive

# Sentences that state how a course is assessed, rather than merely mentioning
# an exam. Ordered by what they establish.
SIGNALS: dict[str, re.Pattern] = {
    "project_option": re.compile(
        r"(can choose|may choose|possono scegliere|in alternativa|alternatively)[^.]{0,160}"
        r"(project|progetto)|(?:exam|esame)[^.]{0,60}(?:consist|consiste)[^.]{0,60}(project|progetto)",
        re.I,
    ),
    "project_required": re.compile(
        r"(exam|esame|assessment|valutazione)[^.]{0,80}"
        r"(consists? (?:in|of)|consiste)[^.]{0,80}(project|progetto|elaborato)",
        re.I,
    ),
    "upload": re.compile(
        r"(upload|caricare|submit)[^.]{0,80}(pdf|notebook|colab|file|zip)", re.I
    ),
    "partial_credit": re.compile(
        r"(assignment|homework|midterm|quiz|esercitazion)[^.]{0,90}"
        r"(worth|vale|up to|at most|points|punti|bonus)",
        re.I,
    ),
    "pass_gate": re.compile(
        r"(at least|almeno|minimum|minimo|necessary to reach|necessario)[^.]{0,90}"
        r"(point|punt|/\d{1,2}|score)|both[^.]{0,40}mandatory|obbligator",
        re.I,
    ),
    "negative_marking": re.compile(
        r"(wrong answer|risposta errata)[^.]{0,50}(-|minus|penal)", re.I
    ),
    "oral": re.compile(
        r"(oral|orale|colloquio)[^.]{0,80}(exam|esame|part|parte|point|punt|mandatory|obbligator)"
        r"|(exam|esame)[^.]{0,60}(oral|orale)",
        re.I,
    ),
    "written": re.compile(
        r"(written|scritt)[^.]{0,60}(exam|test|prova|paper)"
        r"|(exam|esame)[^.]{0,50}(is|consists?|sar[àa]|consiste)[^.]{0,50}(written|scritt)",
        re.I,
    ),
    "grade_formula": re.compile(
        r"(final|overall|complessiv)[^.]{0,40}(grade|mark|score|voto|punteggio)[^.]{0,120}"
        r"(sum|mean|average|media|somma|determined|composed|risulta)"
        r"|(grade|voto)[^.]{0,60}(is the|sar[àa] la|è la)[^.]{0,60}(sum|mean|average|media|somma)",
        re.I,
    ),
    "closed_book": re.compile(r"closed[- ]book|libri chiusi|senza materiale|no material", re.I),
    "duration": re.compile(r"(duration|durata)[^.]{0,40}\d|\d\s*(hours?|ore)\b[^.]{0,30}exam", re.I),
    "lab_component": re.compile(
        r"(laborator|lab)[^.]{0,70}(exam|esame|part|parte|exercise|grade|voto)", re.I
    ),
}

# pypdf is chatty about malformed cross-reference tables in university PDFs;
# the extracted text is still usable, so keep the audit output readable.
_LOG_SILENCED = False


def _silence_pdf_warnings() -> None:
    global _LOG_SILENCED
    if _LOG_SILENCED:
        return
    import logging

    for name in ("pypdf", "pypdf._reader", "pypdf.generic", "pypdf._utils"):
        logging.getLogger(name).setLevel(logging.ERROR)
    _LOG_SILENCED = True


@dataclass
class Finding:
    signal: str
    quote: str
    source_label: str
    source_path: str

    def to_json(self) -> dict[str, str]:
        return {
            "signal": self.signal,
            "quote": self.quote,
            "source": self.source_label,
            "path": self.source_path,
        }


@dataclass
class Dossier:
    code: str
    name: str
    cfu: float
    editions: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    past_papers: list[str] = field(default_factory=list)
    appelli: list[dict[str, str]] = field(default_factory=list)
    docs_read: int = 0
    pages_read: int = 0

    @property
    def tier(self) -> str:
        """Evidence tier. A needs quoted rules AND solved past papers."""
        rules = any(
            f.signal in ("project_option", "project_required", "pass_gate", "written", "oral", "upload")
            for f in self.findings
        )
        solved = any(re.search(r"solu|soluzion", p, re.I) for p in self.past_papers)
        if rules and solved:
            return "A"
        if rules and self.past_papers:
            return "A"
        if rules:
            return "B"
        if self.pages_read:
            return "C"
        return "D"

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "cfu": self.cfu,
            "editions_read": self.editions,
            "pages_read": self.pages_read,
            "docs_read": self.docs_read,
            "evidence_tier": self.tier,
            "findings": [f.to_json() for f in self.findings],
            "past_papers": self.past_papers[:40],
            "appelli": self.appelli,
        }


def _text(record) -> str:
    if record.kind == "pdf":
        _silence_pdf_warnings()
        from pypdf import PdfReader

        try:
            return "\n".join((p.extract_text() or "") for p in PdfReader(str(record.path)).pages)
        except Exception:  # noqa: BLE001 - a corrupt PDF must not stop the audit
            return ""
    soup = BeautifulSoup(record.read_text(), "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    main = soup.select_one("#region-main, [role=main]") or soup
    return main.get_text(" ", strip=True)


def scan(text: str, label: str, path: str) -> list[Finding]:
    """Pull out sentences that state assessment rules."""
    flat = re.sub(r"\s+", " ", text)
    out: list[Finding] = []
    for sentence in re.split(r"(?<=[.;!?])\s+", flat):
        sentence = sentence.strip()
        if not (25 <= len(sentence) <= 320):
            continue
        for signal, pattern in SIGNALS.items():
            if pattern.search(sentence):
                out.append(Finding(signal, sentence, label, path))
                break
    return out


def build(
    remaining: Iterable[dict[str, Any]],
    editions: dict[str, list[dict[str, str]]],
    inventory: dict[str, Any],
    appelli: dict[str, list[dict[str, str]]],
    archive: RawArchive | None = None,
) -> list[Dossier]:
    archive = archive or RawArchive()
    # Module codes roll up into the parent activity they are examined under.
    rollup = {
        "509479": "509478", "509480": "509478",
        "509490": "510109",
    }
    dossiers: dict[str, Dossier] = {}
    for item in remaining:
        dossiers[item["code"]] = Dossier(
            code=item["code"], name=item["name"], cfu=item["cfu"]
        )

    for code, eds in editions.items():
        target = rollup.get(code, code)
        dossier = dossiers.get(target)
        if dossier is None:
            continue
        for edition in eds:
            cid = edition["id"]
            page = archive.latest("kiro", f"course-{cid}")
            info = archive.latest("kiro", f"info-{cid}")
            for record, kind in ((page, "course"), (info, "info")):
                if record is None:
                    continue
                dossier.pages_read += 1
                dossier.editions.append(f"{kind}-{cid}")
                dossier.findings.extend(
                    scan(_text(record), f"kiro {kind}/{cid}", str(record.path))
                )
            for activity in inventory.get(cid, {}).get("mods", []):
                name = activity["name"]
                if re.search(r"exam|esame|prova|test|mock|past|previous|appello", name, re.I):
                    dossier.past_papers.append(f"{name} [{activity['kind']}/{activity['mid']}]")
                doc = archive.latest("kiro", f"mod-{activity['kind']}-{activity['mid']}")
                if doc is None:
                    continue
                dossier.docs_read += 1
                dossier.findings.extend(
                    scan(_text(doc), f"{name} ({activity['kind']})", str(doc.path))
                )

    for name, entries in appelli.items():
        for dossier in dossiers.values():
            if name[:24].lower() in dossier.name.lower():
                dossier.appelli = entries
                break

    # Deduplicate findings, keeping the first source for each quote.
    for dossier in dossiers.values():
        seen: set[str] = set()
        unique: list[Finding] = []
        for finding in dossier.findings:
            key = finding.quote[:120].lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(finding)
        dossier.findings = unique
        dossier.past_papers = list(dict.fromkeys(dossier.past_papers))

    return sorted(dossiers.values(), key=lambda d: d.name)


def save(dossiers: Iterable[Dossier], path) -> None:
    payload = [d.to_json() for d in dossiers]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


# --- effort rubric -----------------------------------------------------------
# Rated for one specific goal: reaching 18/30 by drilling past papers. This is
# why a hard subject with a large solved archive scores low, and an easy subject
# with a mandatory oral or independent minimums scores high.
RUBRIC = {
    1: "Solved past papers for many sessions, single assessment, no gate beyond 18 overall.",
    2: "Past papers or samples exist; one straightforward written or coursework assessment.",
    3: "Either no published papers, or two components to satisfy, or a large syllabus (12 CFU).",
    4: "Independent pass gates, negative marking, or a compulsory oral on top of a written part.",
    5: "Rules not published anywhere reachable, or several gates at once; cannot be drilled blind.",
}

TIER_MEANING = {
    "A": "quoted exam rules + past papers available",
    "B": "quoted exam rules, no past papers",
    "C": "course pages read, exam rules not published there",
    "D": "thin or no evidence",
}


def ledger_markdown(
    dossiers: Iterable[Dossier],
    ratings: dict[str, dict[str, Any]],
    generated: str,
) -> str:
    """Render the coverage ledger. Findings and judgement are kept apart."""
    dossiers = list(dossiers)
    lines: list[str] = []
    lines.append("# Coverage ledger\n")
    lines.append(f"Generated {generated} from the archive under `data/raw/`.\n")
    lines.append(
        "Every row is one remaining activity. **Findings** columns are quoted from a "
        "source; **judgement** columns are mine and can be overridden.\n"
    )

    lines.append("\n## Effort rubric (judgement)\n")
    for score, meaning in RUBRIC.items():
        lines.append(f"- **{score}** - {meaning}")
    lines.append("\n## Evidence tiers (findings)\n")
    for tier, meaning in TIER_MEANING.items():
        lines.append(f"- **{tier}** - {meaning}")

    lines.append("\n## Ledger\n")
    header = (
        "| code | activity | CFU | assessment_format | project_option | partial_credit | "
        "pass_gates | past_papers | appelli (autumn 2026) | tier | effort | read: kiro / docs / syllabus / appelli |"
    )
    lines.append(header)
    lines.append("|" + "---|" * 12)
    for d in dossiers:
        r = ratings.get(d.code, {})
        appelli = ", ".join(a["appello"] for a in d.appelli) or "UNVERIFIED"
        read = (
            f"{d.pages_read} / {d.docs_read} / "
            f"{'yes' if r.get('syllabus_read') else 'no'} / "
            f"{'yes' if d.appelli else 'no'}"
        )
        lines.append(
            f"| {d.code} | {d.name[:44]} | {d.cfu:g} | {r.get('assessment_format','UNVERIFIED')} | "
            f"{r.get('project_option','UNVERIFIED')} | {r.get('partial_credit','UNVERIFIED')} | "
            f"{r.get('pass_gates','UNVERIFIED')} | {len(d.past_papers)} | {appelli} | "
            f"{d.tier} | {r.get('effort','?')} | {read} |"
        )

    unverified = [
        (d, r)
        for d in dossiers
        if (r := ratings.get(d.code, {}))
        and any(
            r.get(k, "UNVERIFIED") == "UNVERIFIED"
            for k in ("assessment_format", "project_option", "pass_gates")
        )
    ]
    lines.append("\n## Cannot rate honestly\n")
    if not unverified:
        lines.append("None - every activity has quoted assessment rules.")
    for d, r in unverified:
        lines.append(f"### {d.code} {d.name}")
        lines.append(f"- missing: {r.get('missing','assessment rules')}")
        lines.append(f"- resolves by: {r.get('action','ask the lecturer directly')}\n")

    lines.append("\n## Quoted evidence per activity\n")
    for d in dossiers:
        lines.append(f"### {d.code} - {d.name} ({d.cfu:g} CFU) - tier {d.tier}")
        lines.append(f"editions read: {len(d.editions)} | documents read: {d.docs_read}\n")
        if not d.findings:
            lines.append("_no assessment-rule sentence found in any archived source_\n")
        for f in d.findings[:8]:
            lines.append(f"- **{f.signal}** - \"{f.quote[:260]}\"")
            lines.append(f"  - source: `{f.source_label}` -> `{f.source_path}`")
        lines.append("")
    return "\n".join(lines)
