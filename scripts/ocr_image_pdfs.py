#!/usr/bin/env python3
"""OCR the archived PDFs that have no text layer.

Thirty of the Statistical Modelling lecture PDFs are single-page image exports.
They are perfectly readable by eye and completely invisible to search, which is
the worst of both worlds. Rendered with pypdfium2 and read with tesseract, the
text is imperfect but searchable, and it is stored beside the original rather
than replacing it.
"""
from __future__ import annotations
import json, sys, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.getLogger("pypdf").setLevel(logging.CRITICAL)

from gradplan.archive import RawArchive
from gradplan.drillbank import collect_documents, read_text

def main() -> int:
    import pypdfium2 as pdfium, pytesseract
    remaining = {c["code"]: c["name"] for c in json.load(open("data/audit/remaining.json"))}
    papers_index = json.load(open("data/audit/papers_index.json"))
    resolved = collect_documents(remaining, papers_index)
    archive = RawArchive(Path("data/raw"))
    done = 0
    for code, docs in resolved.items():
        for doc in docs:
            if doc.kind != "pdf" or read_text(doc.path, "pdf").strip():
                continue
            try:
                pdf = pdfium.PdfDocument(str(doc.path))
                text = "\n".join(
                    pytesseract.image_to_string(pdf[i].render(scale=2.6).to_pil())
                    for i in range(min(len(pdf), 12))
                )
            except Exception as exc:
                print(f"  FAIL {doc.name[:44]}: {type(exc).__name__}")
                continue
            if len(text.strip()) < 80:
                continue
            slug = "".join(ch if ch.isalnum() else "-" for ch in doc.name)[:70].strip("-")
            archive.save(
                source="ocr",
                label=f"file-{code}-ocr-{slug}",
                url=f"ocr://{doc.path.name}",
                payload=f"[OCR of an image-only PDF - expect errors]\n\n{text}",
                kind="text",
                status=200,
            )
            done += 1
            print(f"  OCR {code} {doc.name[:44]:<44} {len(text):>7} chars")
    print(f"OCR DONE {done} documents recovered")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
