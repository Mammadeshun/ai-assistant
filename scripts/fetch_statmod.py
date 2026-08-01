#!/usr/bin/env python3
"""Archive the Statistical Modelling material from the lecturer's public site.

509493 publishes nothing on Kiro. Its six past exams, its exercise sets and its
whole set of lecture notes live on laura-dangelo.github.io, which is why the
course showed zero documents while being one of the better-papered exams in the
plan. Public site, no authentication, same raw-first archiving as everything
else so parsing can be re-run without re-fetching.
"""

from __future__ import annotations

import re
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gradplan.archive import RawArchive  # noqa: E402

INDEX = "https://laura-dangelo.github.io/statistical_modelling/"
COURSE = "509493"
DELAY = 0.8


def fetch(url: str) -> tuple[bytes, int]:
    request = urllib.request.Request(url, headers={"User-Agent": "gradplan/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read(), response.status


def main() -> int:
    archive = RawArchive(Path("data/raw"))

    html, status = fetch(INDEX)
    archive.save(
        source="statmod",
        label=f"file-{COURSE}-index-statistical-modelling",
        url=INDEX,
        payload=html.decode("utf-8", "replace"),
        kind="html",
        status=status,
    )

    links = sorted(
        {
            urljoin(INDEX, href)
            for href in re.findall(r'href="([^"]+)"', html.decode("utf-8", "replace"))
            if href.lower().endswith(".pdf")
        }
    )
    print(f"{len(links)} PDFs listed")

    ok = fail = 0
    for index, url in enumerate(links, start=1):
        name = url.rsplit("/", 1)[-1]
        label = f"file-{COURSE}-statmod-{re.sub(r'[^A-Za-z0-9]+', '-', name).strip('-')}"
        try:
            payload, status = fetch(url)
            archive.save(
                source="statmod",
                label=label,
                url=url,
                payload=payload,
                kind="pdf",
                status=status,
            )
            ok += 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            print(f"  FAIL {name}: {type(exc).__name__}")
        if index % 15 == 0:
            print(f"  {index}/{len(links)} ok={ok} fail={fail}")
        time.sleep(DELAY)

    print(f"DONE fetched={ok} failed={fail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
