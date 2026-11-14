"""Extract physical PDF pages, create chunks, and build the lexical index."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader

from .chunk import chunk_page
from .models import ChunkRecord, PageRecord
from .store import DocumentStore


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_pdf(
    path: Path, *, investigation_id: str | None, source_url: str | None
) -> list[PageRecord]:
    sha256 = _sha256(path)
    source_id = sha256[:16]
    reader = PdfReader(path)
    pages = []
    for physical_page, pdf_page in enumerate(reader.pages, start=1):
        text = pdf_page.extract_text() or ""
        warning = "sparse_or_image_only" if len(text.split()) < 20 else None
        pages.append(
            PageRecord(
                source_id=source_id,
                investigation_id=investigation_id,
                filename=path.name,
                source_url=source_url,
                sha256=sha256,
                physical_page=physical_page,
                text=text,
                extraction_warning=warning,
            )
        )
    return pages


def _write_jsonl(path: Path, values: list[PageRecord] | list[ChunkRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for value in values:
            stream.write(json.dumps(value.model_dump(mode="json"), ensure_ascii=False) + "\n")


def build_index(
    pdfs: list[Path],
    *,
    investigation_id: str | None,
    source_url: str | None,
    processed_dir: Path,
    database: Path,
) -> dict[str, object]:
    pages: list[PageRecord] = []
    seen_hashes: set[str] = set()
    for pdf in pdfs:
        extracted = extract_pdf(pdf, investigation_id=investigation_id, source_url=source_url)
        if extracted and extracted[0].sha256 not in seen_hashes:
            pages.extend(extracted)
            seen_hashes.add(extracted[0].sha256)
    chunks = [chunk for page in pages for chunk in chunk_page(page)]
    _write_jsonl(processed_dir / "pages.jsonl", pages)
    _write_jsonl(processed_dir / "chunks.jsonl", chunks)
    with DocumentStore(database) as store:
        store.replace(pages, chunks)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "distinct_documents": len(seen_hashes),
        "physical_pages": len(pages),
        "chunks": len(chunks),
        "sparse_pages": sum(page.extraction_warning is not None for page in pages),
        "database": str(database),
    }
    (processed_dir / "build-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report
