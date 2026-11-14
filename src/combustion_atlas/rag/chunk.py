"""Deterministic page-bounded overlapping word chunks."""

from __future__ import annotations

import re

from .models import ChunkRecord, PageRecord


def chunk_page(
    page: PageRecord, *, max_words: int = 600, overlap_words: int = 60
) -> list[ChunkRecord]:
    if max_words < 1 or overlap_words < 0 or overlap_words >= max_words:
        raise ValueError("Require max_words >= 1 and 0 <= overlap_words < max_words")
    words = list(re.finditer(r"\S+", page.text))
    if not words:
        return []
    chunks = []
    start = 0
    chunk_index = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        char_start = words[start].start()
        char_end = words[end - 1].end()
        chunks.append(
            ChunkRecord(
                chunk_id=f"{page.source_id}:p{page.physical_page}:c{chunk_index}",
                source_id=page.source_id,
                investigation_id=page.investigation_id,
                filename=page.filename,
                source_url=page.source_url,
                sha256=page.sha256,
                physical_page=page.physical_page,
                chunk_index=chunk_index,
                char_start=char_start,
                char_end=char_end,
                text=page.text[char_start:char_end],
            )
        )
        if end == len(words):
            break
        start = end - overlap_words
        chunk_index += 1
    return chunks
