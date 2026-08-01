#!/usr/bin/env python3
"""Render every exam paper to page images so they can actually be read.

Extracted text is fine for searching and useless for reading: PDF extraction
loses layout, tables and every formula, and OCR of a photographed exam paper is
worse than that. For a paper you are about to sit, the page itself is the
artefact you want in front of you.

Grayscale WebP at ~1.5x. Text pages come out around 60 KB, which is legible on
a phone and small enough that 600 of them fit in a bundle you can carry.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.getLogger("pypdf").setLevel(logging.CRITICAL)

OUT = Path("data/bundle/pages")
INDEX = Path("data/bundle/pages_index.json")

# Exam papers and answer keys are what you read closely, so they get the
# quality. 'image-only' is the scanned lecture notes: worth having to hand,
# not worth a third of the bundle.
SETTINGS = {
    "paper": (1.55, 50),
    "solution": (1.55, 50),
    "image-only": (1.10, 36),
}
MAX_PAGES = 6
RENDER_ROLES = set(SETTINGS)


def photo_map() -> dict[str, Path]:
    """Course+name slug -> the original photograph, where one was archived."""
    manifest = Path("data/raw/manifest.jsonl")
    if not manifest.exists():
        return {}
    out: dict[str, Path] = {}
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        label = record.get("label", "")
        if "-photo-" not in label or record.get("kind") != "image":
            continue
        course, _, slug = label[len("file-"):].partition("-photo-")
        out[f"{course}:{slug_of(slug)}"] = Path("data/raw") / record["path"]
    return out


def slug_of(name: str) -> str:
    """Collapse to alphanumeric words.

    The label slug and the library's tidied document name disagree on runs of
    punctuation - 'A - B' becomes 'A---B' one way and 'A-B' the other - so
    neither raw form can be used as a join key.
    """
    import re

    return re.sub(r"[^0-9a-z]+", "-", name.lower())[:70].strip("-")


def main() -> int:
    import pypdfium2 as pdfium
    from PIL import Image

    library = json.loads(Path("data/library.json").read_text())["courses"]
    photos = photo_map()
    OUT.mkdir(parents=True, exist_ok=True)

    index: dict[str, list[str]] = {}
    rendered = skipped = failed = 0
    total_bytes = 0

    for code, course in library.items():
        for doc in course["documents"]:
            if doc["role"] not in RENDER_ROLES:
                continue
            path = Path(doc["path"])
            key = hashlib.sha1(f"{code}/{doc['name']}/{doc['i']}".encode()).hexdigest()[:12]

            # A transcribed photograph has a .txt for its path. The image it was
            # typed from is archived separately and is the thing worth showing.
            if path.suffix.lower() != ".pdf":
                photo = photos.get(f"{code}:{slug_of(doc['name'])}")
                if photo is None or not photo.exists():
                    continue
                target = OUT / f"{key}-0.webp"
                if not target.exists():
                    try:
                        image = Image.open(photo)
                        image.thumbnail((1500, 1500))
                        image.convert("L").save(target, "WEBP", quality=62, method=5)
                        rendered += 1
                    except Exception:  # noqa: BLE001
                        failed += 1
                        continue
                else:
                    skipped += 1
                total_bytes += target.stat().st_size
                index[f"{code}:{doc['i']}"] = [target.name]
                continue

            if not path.exists():
                continue
            try:
                pdf = pdfium.PdfDocument(str(path))
                count = min(len(pdf), MAX_PAGES)
            except Exception:  # noqa: BLE001
                failed += 1
                continue

            files: list[str] = []
            for page in range(count):
                target = OUT / f"{key}-{page}.webp"
                files.append(target.name)
                if target.exists():
                    skipped += 1
                    total_bytes += target.stat().st_size
                    continue
                scale, quality = SETTINGS[doc["role"]]
                try:
                    image = pdf[page].render(scale=scale).to_pil().convert("L")
                    image.save(target, "WEBP", quality=quality, method=5)
                    rendered += 1
                    total_bytes += target.stat().st_size
                except Exception:  # noqa: BLE001
                    failed += 1
            if files:
                index[f"{code}:{doc['i']}"] = files

        print(f"  {code} done ({len(index)} docs so far)")

    # Page filenames are keyed by document name, so renaming a document orphans
    # its old images. Drop anything the current index does not reference.
    live = {name for files in index.values() for name in files}
    pruned = 0
    for stale in OUT.glob("*.webp"):
        if stale.name not in live:
            stale.unlink()
            pruned += 1

    INDEX.write_text(json.dumps(index))
    print(f"  pruned {pruned} orphaned page images")
    print(
        f"RENDER DONE docs={len(index)} pages rendered={rendered} reused={skipped} "
        f"failed={failed} total={total_bytes/1e6:.0f} MB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
