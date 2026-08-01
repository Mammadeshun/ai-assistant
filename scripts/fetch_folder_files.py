#!/usr/bin/env python3
"""Download the folder contents the first crawl listed but never fetched.

The original crawl archived every folder *page* but only some of the files
inside them, which is why Computational Logic looked like one sitting instead
of four years of them. This walks the archived folder pages, diffs the
pluginfile links against the manifest, and fetches what is missing.

Sequential, with a delay between requests. Nothing is re-fetched.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bs4 import BeautifulSoup  # noqa: E402

from gradplan import config  # noqa: E402
from gradplan.archive import RawArchive  # noqa: E402
from gradplan.sources.http_session import http_session  # noqa: E402

RAW = Path("data/raw")
DELAY = 1.0

EXT_KIND = {
    ".pdf": "pdf",
    ".zip": "zip",
    ".ipynb": "text",
    ".py": "text",
    ".txt": "text",
    ".smt2": "text",
    ".csv": "text",
    ".md": "text",
}


def load_env() -> None:
    env = Path(".env")
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def folder_course_map(records: list[dict]) -> dict[str, str]:
    """mod-folder-<mid> -> course code, from the papers index."""
    index = json.load(open("data/audit/papers_index.json"))
    return {
        str(entry["mid"]): course
        for course, entries in index.items()
        for entry in entries
        if entry["kind"] == "folder"
    }


def main() -> int:
    load_env()
    records = [json.loads(l) for l in open(RAW / "manifest.jsonl") if l.strip()]
    have = {r["url"].split("?")[0] for r in records}
    course_of = folder_course_map(records)

    wanted: list[tuple[str, str, str]] = []  # (course, mid, url)
    for record in records:
        found = re.match(r"^mod-folder-(\d+)$", record["label"])
        if not found:
            continue
        mid = found.group(1)
        page = RAW / record["path"]
        if not page.exists():
            continue
        soup = BeautifulSoup(page.read_text(errors="replace"), "html.parser")
        for anchor in soup.select('a[href*="pluginfile.php"]'):
            url = anchor["href"]
            if url.split("?")[0] in have:
                continue
            if "favicon" in url or url.endswith(".ico"):
                continue
            wanted.append((course_of.get(mid, "unknown"), mid, url))

    # Deduplicate while preserving order.
    seen: set[str] = set()
    queue = []
    for course, mid, url in wanted:
        if url.split("?")[0] in seen:
            continue
        seen.add(url.split("?")[0])
        queue.append((course, mid, url))

    print(f"{len(queue)} files to fetch")
    archive = RawArchive(RAW)
    session = http_session(archive, delay=DELAY)
    ok = fail = 0
    try:
        for index, (course, mid, url) in enumerate(queue, start=1):
            name = re.sub(r"\?.*$", "", url).rsplit("/", 1)[-1]
            stem, dot, ext = name.rpartition(".")
            kind = EXT_KIND.get(f".{ext.lower()}", "text")
            label = f"file-{course}-{mid}-{re.sub(r'[^A-Za-z0-9]+', '-', name).strip('-')}"
            try:
                session.goto(url, source="kiro", label=label)
                ok += 1
            except Exception as exc:  # noqa: BLE001 - keep going, report at the end
                fail += 1
                print(f"  FAIL {name[:50]}: {type(exc).__name__}")
            if index % 20 == 0:
                print(f"  {index}/{len(queue)} ok={ok} fail={fail}")
            time.sleep(DELAY)
    finally:
        session.close()
    print(f"DONE fetched={ok} failed={fail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
