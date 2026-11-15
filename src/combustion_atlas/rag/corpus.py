"""Corpus summaries and a 2-D topic map of stored embeddings (no extra dependencies)."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from operator import mul
from pathlib import Path
from typing import Any

from .store import QUARANTINE, DocumentStore
from .vectors import decode_vector

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


def _components(rows: list[list[float]], count: int, iterations: int = 60) -> list[list[float]]:
    """Top principal directions by power iteration with Gram-Schmidt deflation."""
    columns = [list(column) for column in zip(*rows, strict=True)]
    generator = random.Random(0)  # deterministic layout between runs
    found: list[list[float]] = []
    for _ in range(count):
        vector = [generator.gauss(0, 1) for _ in columns]
        for _ in range(iterations):
            projected = [sum(map(mul, row, vector)) for row in rows]
            vector = [sum(map(mul, column, projected)) for column in columns]
            for prior in found:
                dot = sum(map(mul, vector, prior))
                vector = [v - dot * p for v, p in zip(vector, prior, strict=True)]
            norm = math.sqrt(sum(v * v for v in vector)) or 1.0
            vector = [v / norm for v in vector]
        found.append(vector)
    return found


def topic_map(store: DocumentStore, *, model_key: str, cache_dir: Path) -> dict[str, Any]:
    """Project every embedded passage onto its first two principal components.

    Nearby points have similar embeddings (similar topics). Axes have no units or
    scientific meaning; the map is for navigation, not analysis.
    """
    namespace = store.connection.execute(
        "SELECT dimensions FROM vector_namespaces WHERE model_key=?", (model_key,)
    ).fetchone()
    if namespace is None:
        return {"points": [], "model_key": model_key}
    dimensions = int(namespace[0])
    rows = store.connection.execute(
        "SELECT c.chunk_id, c.source_id, c.filename, c.physical_page, c.text, v.vector "
        "FROM vectors v JOIN chunks c ON c.chunk_id=v.chunk_id WHERE v.model_key=? "
        f"AND (c.investigation_id IS NULL OR c.investigation_id != '{QUARANTINE}') "
        "ORDER BY c.chunk_id",
        (model_key,),
    ).fetchall()
    key = hashlib.sha256(
        ("topic-map-v2|" + model_key + "|" + "|".join(row[0] for row in rows)).encode()
    ).hexdigest()
    cache = cache_dir / "topic-map.json"
    if cache.is_file():
        cached: dict[str, Any] = json.loads(cache.read_text(encoding="utf-8"))
        if cached.get("key") == key:
            return cached
    visual = {
        chunk_id: json.loads(payload)
        for chunk_id, payload in store.connection.execute(
            "SELECT v.chunk_id, a.payload FROM visual_chunks v "
            "JOIN visual_artifacts a ON a.artifact_id=v.artifact_id"
        )
    }
    sections = {source: page_sections(store, source) for source in {row[1] for row in rows}}
    vectors = [decode_vector(row[5], dimensions) for row in rows]
    points: list[dict[str, Any]] = []
    if len(vectors) >= 3:
        mean = [sum(column) / len(vectors) for column in zip(*vectors, strict=True)]
        centered = [[v - m for v, m in zip(vector, mean, strict=True)] for vector in vectors]
        first, second = _components(centered, 2)
        for row, vector in zip(rows, centered, strict=True):
            artifact = visual.get(row[0])
            points.append(
                {
                    "chunk_id": row[0],
                    "source_id": row[1],
                    "filename": row[2],
                    "page": row[3],
                    "section": sections[row[1]].get(row[3]),
                    "kind": artifact["kind"] if artifact else "text",
                    "label": f"{artifact['kind'].title()} {artifact['label']}"
                    if artifact
                    else None,
                    "snippet": " ".join((artifact["caption"] if artifact else row[4]).split())[
                        :220
                    ],
                    "x": round(sum(map(mul, vector, first)), 5),
                    "y": round(sum(map(mul, vector, second)), 5),
                }
            )
    result = {"key": key, "model_key": model_key, "points": points}
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result
