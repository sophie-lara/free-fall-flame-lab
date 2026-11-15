"""Corpus summaries: documents, pages, passages, figures and sections per page."""

from __future__ import annotations

import json
import re
from typing import Any

from .store import QUARANTINE, DocumentStore

HEADING = re.compile(
    r"^\s*(\d{1,2})\.0\s+([A-Z][^\n]{3,90})$|^\s*(Appendix [A-Z])\.?[—–-]\s*([^\n]{3,90})$",
    re.M,
)


def page_sections(store: DocumentStore, source_id: str) -> dict[int, str]:
    """Section per page from top-level headings ("2.0 ...", "Appendix A.—...").

    Pages with several headings (tables of contents) are ignored; pages before
    the first heading are front matter. Heuristic and for navigation only.
    """
    sections: dict[int, str] = {}
    current = "Front matter"
    for number, text in store.connection.execute(
        "SELECT physical_page, text FROM pages WHERE source_id=? ORDER BY physical_page",
        (source_id,),
    ):
        found = [m for m in HEADING.finditer(text) if "...." not in m.group(0)]
        if len(found) == 1:
            m = found[0]
            current = f"{m.group(1)}.0 {m.group(2)}" if m.group(1) else f"{m.group(3)}"
            current = " ".join(current.split())[:70]
        sections[number] = current
    return sections


def corpus_summary(store: DocumentStore) -> dict[str, Any]:
    """Per-document counts and a page strip: words, figures and tables per physical page."""
    connection = store.connection
    visuals: dict[tuple[str, int], dict[str, list[str]]] = {}
    for (payload,) in connection.execute("SELECT payload FROM visual_artifacts"):
        artifact = json.loads(payload)
        entry = visuals.setdefault(
            (artifact["source_id"], artifact["physical_page"]), {"figure": [], "table": []}
        )
        entry[artifact["kind"]].append(artifact["label"])
    embedded = {row[0] for row in connection.execute("SELECT DISTINCT chunk_id FROM vectors")}
    visual_chunks = {row[0] for row in connection.execute("SELECT chunk_id FROM visual_chunks")}
    documents = []
    for source_id, filename, url, sha in connection.execute(
        "SELECT DISTINCT source_id, filename, source_url, sha256 FROM pages "
        "WHERE investigation_id IS NULL OR investigation_id != ? ORDER BY filename",
        (QUARANTINE,),
    ).fetchall():
        investigations = sorted(
            {
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT investigation_id FROM pages "
                    "WHERE source_id=? AND investigation_id IS NOT NULL",
                    (source_id,),
                )
            }
        )
        pages = connection.execute(
            "SELECT physical_page, text, extraction_warning FROM pages "
            "WHERE source_id=? ORDER BY physical_page",
            (source_id,),
        ).fetchall()
        chunk_ids = [
            row[0]
            for row in connection.execute(
                "SELECT chunk_id FROM chunks WHERE source_id=?", (source_id,)
            )
        ]
        sections = page_sections(store, source_id)
        strip = [
            {
                "page": number,
                "section": sections.get(number),
                "words": len(text.split()),
                "sparse": warning is not None,
                "figures": visuals.get((source_id, number), {}).get("figure", []),
                "tables": visuals.get((source_id, number), {}).get("table", []),
            }
            for number, text, warning in pages
        ]
        documents.append(
            {
                "source_id": source_id,
                "filename": filename,
                "source_url": url,
                "sha256": sha,
                "investigation_ids": investigations,
                "pages": len(pages),
                "passages": sum(chunk not in visual_chunks for chunk in chunk_ids),
                "embedded": sum(chunk in embedded for chunk in chunk_ids),
                "figures": sum(len(p["figures"]) for p in strip),
                "tables": sum(len(p["tables"]) for p in strip),
                "page_strip": strip,
            }
        )
    totals = {
        key: sum(doc[key] for doc in documents)
        for key in ("pages", "passages", "embedded", "figures", "tables")
    }
    totals["documents"] = len(documents)
    totals["investigations"] = len({i for doc in documents for i in doc["investigation_ids"]})
    return {"documents": documents, "totals": totals}
