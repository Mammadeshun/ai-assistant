"""Timestamped archive of every raw response.

Everything fetched — HTML, JSON, PDF — lands in ``data/raw/<source>/`` under a
UTC-timestamped filename, and is appended to a JSONL manifest. Parsing always
reads from the archive, never from the network, so parsers can be iterated on
without touching the university servers again.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import RAW_DIR

MANIFEST_NAME = "manifest.jsonl"

_EXT_BY_KIND = {
    "html": "html",
    "json": "json",
    "pdf": "pdf",
    "text": "txt",
}


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slugify(value: str, max_len: int = 60) -> str:
    slug = re.sub(r"^https?://", "", value)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", slug).strip("-").lower()
    return (slug[:max_len] or "response").rstrip("-")


@dataclass
class ArchivedResponse:
    """A single stored response and the metadata needed to find it again."""

    path: Path
    url: str
    source: str
    label: str
    kind: str
    fetched_at: str
    sha256: str
    status: int | None = None

    def read_text(self) -> str:
        return self.path.read_text(encoding="utf-8", errors="replace")

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()

    def read_json(self) -> Any:
        return json.loads(self.read_text())

    def to_json(self) -> dict[str, Any]:
        return {
            "path": str(self.path.relative_to(RAW_DIR.parent.parent))
            if RAW_DIR.parent.parent in self.path.parents
            else str(self.path),
            "url": self.url,
            "source": self.source,
            "label": self.label,
            "kind": self.kind,
            "fetched_at": self.fetched_at,
            "sha256": self.sha256,
            "status": self.status,
        }


class RawArchive:
    """Writes raw payloads to disk and indexes them in a manifest."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or RAW_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def manifest_path(self) -> Path:
        return self.root / MANIFEST_NAME

    def save(
        self,
        *,
        source: str,
        label: str,
        url: str,
        payload: str | bytes,
        kind: str = "html",
        status: int | None = None,
    ) -> ArchivedResponse:
        """Persist one response. ``source`` is a subdirectory, e.g. ``esse3``."""
        data = payload.encode("utf-8") if isinstance(payload, str) else payload
        directory = self.root / source
        directory.mkdir(parents=True, exist_ok=True)

        ext = _EXT_BY_KIND.get(kind, "bin")
        filename = f"{_utc_stamp()}__{_slugify(label)}.{ext}"
        path = directory / filename
        path.write_bytes(data)

        record = ArchivedResponse(
            path=path,
            url=url,
            source=source,
            label=label,
            kind=kind,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            sha256=hashlib.sha256(data).hexdigest(),
            status=status,
        )
        with self.manifest_path.open("a", encoding="utf-8") as handle:
            entry = record.to_json()
            entry["path"] = str(path.relative_to(self.root))
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return record

    # -- reading back -------------------------------------------------------
    def entries(self) -> Iterator[dict[str, Any]]:
        if not self.manifest_path.exists():
            return iter(())
        with self.manifest_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def latest(self, source: str, label: str) -> ArchivedResponse | None:
        """Most recent archived response for a ``(source, label)`` pair."""
        best: dict[str, Any] | None = None
        for entry in self.entries():
            if entry["source"] == source and entry["label"] == label:
                if best is None or entry["fetched_at"] >= best["fetched_at"]:
                    best = entry
        if best is None:
            return self._latest_from_disk(source, label)
        path = self.root / best["path"]
        if not path.exists():
            return self._latest_from_disk(source, label)
        return ArchivedResponse(
            path=path,
            url=best["url"],
            source=best["source"],
            label=best["label"],
            kind=best["kind"],
            fetched_at=best["fetched_at"],
            sha256=best["sha256"],
            status=best.get("status"),
        )

    def _latest_from_disk(self, source: str, label: str) -> ArchivedResponse | None:
        """Fallback when the manifest is missing or out of sync with the files."""
        directory = self.root / source
        if not directory.is_dir():
            return None
        slug = _slugify(label)
        candidates = sorted(directory.glob(f"*__{slug}.*"))
        if not candidates:
            return None
        path = candidates[-1]
        data = path.read_bytes()
        return ArchivedResponse(
            path=path,
            url="",
            source=source,
            label=label,
            kind=path.suffix.lstrip("."),
            fetched_at=path.stat().st_mtime.__str__(),
            sha256=hashlib.sha256(data).hexdigest(),
        )
