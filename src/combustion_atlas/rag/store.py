"""SQLite FTS5 storage for page-bounded document chunks."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from urllib.parse import quote

from .models import ChunkRecord, PageRecord
from .vectors import cosine_similarity, decode_vector, encode_vector

# Question words carry no evidence; requiring them made natural-language queries
# match almost nothing. Domain terms (e.g. "flame", "oxygen") are never listed here.
STOPWORDS = frozenset(
    """a about an and any are as at be by can could did do does for from give gives
    had has have how i in is it its labelled labeled many much of on or report says
    tell that the their there these this those to was were what when where which who
    why with would""".split()
)


def keyword_query(question: str) -> str:
    """Build an FTS5 OR query; BM25 then ranks chunks matching more rare terms first."""
    tokens = [t for t in re.findall(r"[\w-]+", question, flags=re.UNICODE) if re.search(r"\w", t)]
    terms = [t for t in tokens if t.lower() not in STOPWORDS] or tokens
    unique = list(dict.fromkeys(term.lower() for term in terms))
    return " OR ".join(f'"{term}"' for term in unique)


# Visitor uploads are indexed under this investigation and stay out of shared results
# (search, corpus counts, topic map) unless a request names them in visible_sources.
QUARANTINE = "VISITOR-UPLOAD"


class DocumentStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        # Quarantined (visitor-upload) sources this request may see; empty = none.
        self.visible_sources: frozenset[str] = frozenset()
        self._initialize()

    def _visibility(self) -> tuple[str, tuple[object, ...]]:
        """SQL condition hiding quarantined sources not named in visible_sources."""
        import json as _json

        return (
            " AND (c.investigation_id IS NULL OR c.investigation_id != ?"
            " OR c.source_id IN (SELECT value FROM json_each(?)))",
            (QUARANTINE, _json.dumps(sorted(self.visible_sources))),
        )

    def __enter__(self) -> DocumentStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS pages (
                source_id TEXT NOT NULL,
                physical_page INTEGER NOT NULL,
                investigation_id TEXT,
                filename TEXT NOT NULL,
                source_url TEXT,
                sha256 TEXT NOT NULL,
                text TEXT NOT NULL,
                extraction_warning TEXT,
                PRIMARY KEY (source_id, physical_page)
            );
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                investigation_id TEXT,
                filename TEXT NOT NULL,
                source_url TEXT,
                sha256 TEXT NOT NULL,
                physical_page INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                char_start INTEGER NOT NULL,
                char_end INTEGER NOT NULL,
                text TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                chunk_id UNINDEXED,
                text,
                tokenize='porter unicode61'
            );
            CREATE TABLE IF NOT EXISTS vector_namespaces (
                model_key TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                revision TEXT,
                dimensions INTEGER NOT NULL,
                normalized INTEGER NOT NULL,
                max_tokens INTEGER
            );
            CREATE TABLE IF NOT EXISTS vectors (
                model_key TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                vector BLOB NOT NULL,
                PRIMARY KEY (model_key, chunk_id),
                FOREIGN KEY (model_key) REFERENCES vector_namespaces(model_key),
                FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
            );
            CREATE TABLE IF NOT EXISTS visual_artifacts (
                artifact_id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS visual_chunks (
                chunk_id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL
            );
            """
        )
        self._migrate_keyword_index()

    def _migrate_keyword_index(self) -> None:
        """Rebuild only the derived FTS index with stemming; chunks and vectors are untouched."""
        row = self.connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='chunks_fts'"
        ).fetchone()
        if row is None or "porter" in row[0]:
            return
        with self.connection:
            self.connection.execute("DROP TABLE chunks_fts")
            self.connection.execute(
                "CREATE VIRTUAL TABLE chunks_fts USING fts5("
                "chunk_id UNINDEXED, text, tokenize='porter unicode61')"
            )
            self.connection.execute(
                "INSERT INTO chunks_fts (chunk_id, text) SELECT chunk_id, text FROM chunks"
            )

    def replace(self, pages: list[PageRecord], chunks: list[ChunkRecord]) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM visual_chunks")
            self.connection.execute("DELETE FROM visual_artifacts")
            self.connection.execute("DELETE FROM chunks_fts")
            self.connection.execute("DELETE FROM vectors")
            self.connection.execute("DELETE FROM vector_namespaces")
            self.connection.execute("DELETE FROM chunks")
            self.connection.execute("DELETE FROM pages")
            self.connection.executemany(
                "INSERT INTO pages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        page.source_id,
                        page.physical_page,
                        page.investigation_id,
                        page.filename,
                        page.source_url,
                        page.sha256,
                        page.text,
                        page.extraction_warning,
                    )
                    for page in pages
                ],
            )
            self.connection.executemany(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        chunk.chunk_id,
                        chunk.source_id,
                        chunk.investigation_id,
                        chunk.filename,
                        chunk.source_url,
                        chunk.sha256,
                        chunk.physical_page,
                        chunk.chunk_index,
                        chunk.char_start,
                        chunk.char_end,
                        chunk.text,
                    )
                    for chunk in chunks
                ],
            )
            self.connection.executemany(
                "INSERT INTO chunks_fts (chunk_id, text) VALUES (?, ?)",
                [(chunk.chunk_id, chunk.text) for chunk in chunks],
            )

    def chunk_count(self) -> int:
        return int(self.connection.execute("SELECT count(*) FROM chunks").fetchone()[0])

    def add_document(self, pages: list[PageRecord], chunks: list[ChunkRecord]) -> str:
        """Insert one new source without touching other sources, vectors, or visuals.

        Returns "added" or "unchanged". A different file with the same source_id
        prefix is refused rather than merged.
        """
        sources = {page.source_id for page in pages} | {chunk.source_id for chunk in chunks}
        if len(sources) != 1:
            raise ValueError("add_document takes exactly one source document")
        source_id = sources.pop()
        existing = self.connection.execute(
            "SELECT DISTINCT sha256 FROM pages WHERE source_id=?", (source_id,)
        ).fetchall()
        if existing:
            if {row[0] for row in existing} == {pages[0].sha256}:
                return "unchanged"
            raise ValueError(f"Source {source_id} is indexed with different bytes")
        with self.connection:
            self.connection.executemany(
                "INSERT INTO pages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        page.source_id,
                        page.physical_page,
                        page.investigation_id,
                        page.filename,
                        page.source_url,
                        page.sha256,
                        page.text,
                        page.extraction_warning,
                    )
                    for page in pages
                ],
            )
            self.connection.executemany(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        chunk.chunk_id,
                        chunk.source_id,
                        chunk.investigation_id,
                        chunk.filename,
                        chunk.source_url,
                        chunk.sha256,
                        chunk.physical_page,
                        chunk.chunk_index,
                        chunk.char_start,
                        chunk.char_end,
                        chunk.text,
                    )
                    for chunk in chunks
                ],
            )
            self.connection.executemany(
                "INSERT INTO chunks_fts (chunk_id, text) VALUES (?, ?)",
                [(chunk.chunk_id, chunk.text) for chunk in chunks],
            )
        return "added"

    def remove_document(self, source_id: str) -> dict[str, int]:
        """Delete one source with its chunks, vectors and visual artifacts."""
        chunk_ids = [
            row[0]
            for row in self.connection.execute(
                "SELECT chunk_id FROM chunks WHERE source_id=?", (source_id,)
            )
        ]
        artifacts = [
            row[0]
            for row in self.connection.execute(
                "SELECT DISTINCT v.artifact_id FROM visual_chunks v "
                "JOIN chunks c ON c.chunk_id=v.chunk_id WHERE c.source_id=?",
                (source_id,),
            )
        ]
        with self.connection:
            for chunk_id in chunk_ids:
                for table in ("vectors", "chunks_fts", "visual_chunks"):
                    self.connection.execute(f"DELETE FROM {table} WHERE chunk_id=?", (chunk_id,))
            for artifact_id in artifacts:
                self.connection.execute(
                    "DELETE FROM visual_artifacts WHERE artifact_id=?", (artifact_id,)
                )
            self.connection.execute("DELETE FROM chunks WHERE source_id=?", (source_id,))
            pages = self.connection.execute(
                "DELETE FROM pages WHERE source_id=?", (source_id,)
            ).rowcount
        return {"pages": pages, "chunks": len(chunk_ids), "visual_artifacts": len(artifacts)}

    def cards_for_identifiers(self, question: str) -> list[str]:
        """Record-card chunk IDs whose test ID is named exactly in the question.

        Matches tokens with letters and digits ("O12", "B11", "M5") or dashed
        numbers ("2-8"); a dashed token also matches a prefixed ID
        ("SAFFIRE-II-2-8"). Plain numbers never match.
        """
        has_cards = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='record_cards'"
        ).fetchone()
        if not has_cards:
            return []
        tokens = {
            t.lower() for t in re.findall(r"\b[A-Za-z][A-Za-z-]*\d+[a-z]?\b|\b\d+-\d+\b", question)
        }
        if not tokens:
            return []
        import json

        matches = []
        for card_id, payload in self.connection.execute(
            "SELECT card_id, payload FROM record_cards"
        ):
            test_id = str(json.loads(payload).get("test_id") or "").lower()
            if test_id in tokens or any("-" in t and test_id.endswith("-" + t) for t in tokens):
                matches.append(card_id)
        return sorted(matches)

    def record_rows(self) -> list[dict[str, object]]:
        """Structured reviewed table rows (not part of the text index)."""
        import json

        has_rows = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name='record_rows'"
        ).fetchone()
        if not has_rows:
            return []
        return [
            json.loads(payload)
            for (payload,) in self.connection.execute(
                "SELECT payload FROM record_rows ORDER BY card_id, rowid"
            )
        ]

    def rows_for_identifiers(self, question: str) -> list[dict[str, object]]:
        """Rows whose test ID is named exactly in the question (same rules as cards,
        plus full FLEX IDs such as "FLEX-T8-61")."""
        tokens = {
            t.lower()
            for t in re.findall(
                r"\b[A-Za-z]+-T\d+-\d+\b|\b[A-Za-z][A-Za-z-]*\d+[a-z]?\b|\b\d+-\d+\b", question
            )
        }
        if not tokens:
            return []
        out = []
        for row in self.record_rows():
            test_id = str(row.get("test_id") or "").lower()
            if test_id in tokens or any("-" in t and test_id.endswith("-" + t) for t in tokens):
                out.append(row)
        return out

    def chunks_missing_vectors(self, model_key: str) -> list[ChunkRecord]:
        rows = self.connection.execute(
            "SELECT c.* FROM chunks c LEFT JOIN vectors v "
            "ON v.chunk_id=c.chunk_id AND v.model_key=? WHERE v.chunk_id IS NULL "
            "ORDER BY c.source_id, c.physical_page, c.chunk_index",
            (model_key,),
        ).fetchall()
        return [ChunkRecord.model_validate(dict(row)) for row in rows]

    def search(
        self, question: str, investigation_id: str | None = None, top_k: int = 5
    ) -> list[dict[str, object]]:
        query = keyword_query(question)
        if not query:
            return []
        rows = self.connection.execute(
            """
            SELECT c.*, bm25(chunks_fts) AS score
            FROM chunks_fts
            JOIN chunks AS c ON c.chunk_id = chunks_fts.chunk_id
            WHERE chunks_fts MATCH ?
              AND (? IS NULL OR lower(c.investigation_id) = lower(?))"""
            + self._visibility()[0]
            + """
            ORDER BY score
            LIMIT ?
            """,
            (query, investigation_id, investigation_id, *self._visibility()[1], top_k),
        ).fetchall()
        return self._attach_visuals([dict(row) for row in rows])

    def _attach_visuals(self, results: list[dict[str, object]]) -> list[dict[str, object]]:
        import json

        has_cards = (
            self.connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='record_cards'"
            ).fetchone()
            is not None
        )
        for item in results:
            if has_cards:
                card = self.connection.execute(
                    "SELECT payload FROM record_cards WHERE card_id=?", (item["chunk_id"],)
                ).fetchone()
                if card:
                    item["record_card"] = json.loads(card[0])
            row = self.connection.execute(
                "SELECT a.payload FROM visual_chunks v JOIN visual_artifacts a "
                "ON a.artifact_id=v.artifact_id WHERE v.chunk_id=?",
                (item["chunk_id"],),
            ).fetchone()
            if row:
                artifact = json.loads(row[0])
                item["visual"] = {
                    key: artifact[key]
                    for key in (
                        "artifact_id",
                        "kind",
                        "label",
                        "caption",
                        "method",
                        "review_status",
                        "model",
                    )
                }
                item["crop_url"] = "/api/visuals/" + quote(artifact["artifact_id"], safe=":")
        return results

    def upsert_visual(self, artifact: object) -> bool:
        from .chunk import chunk_page
        from .visual_models import VisualArtifact

        if not isinstance(artifact, VisualArtifact):
            raise TypeError("Expected a validated VisualArtifact")
        source = self.connection.execute(
            "SELECT sha256, filename FROM pages WHERE source_id=? AND physical_page=?",
            (artifact.source_id, artifact.physical_page),
        ).fetchone()
        if (
            source is None
            or source["sha256"] != artifact.source_sha256
            or (source["filename"] != artifact.filename)
        ):
            raise ValueError("Visual artifact does not match an indexed source page")
        if artifact.review_status == "rejected":
            raise ValueError("Rejected artifacts cannot be indexed")
        if artifact.kind == "table" and artifact.table is None:
            raise ValueError("Table imports require structured cells")
        fingerprint = artifact.fingerprint()
        existing = self.connection.execute(
            "SELECT fingerprint FROM visual_artifacts WHERE artifact_id=?",
            (artifact.artifact_id,),
        ).fetchone()
        if existing and existing[0] == fingerprint:
            return False
        page = PageRecord(
            source_id=artifact.source_id,
            investigation_id=artifact.investigation_id,
            filename=artifact.filename,
            source_url=artifact.source_url,
            sha256=artifact.source_sha256,
            physical_page=artifact.physical_page,
            text=artifact.retrieval_text(),
        )
        chunks = chunk_page(page)
        with self.connection:
            prior = [
                r[0]
                for r in self.connection.execute(
                    "SELECT chunk_id FROM visual_chunks WHERE artifact_id=?",
                    (artifact.artifact_id,),
                )
            ]
            for chunk_id in prior:
                for table in ("vectors", "chunks_fts", "chunks", "visual_chunks"):
                    self.connection.execute(f"DELETE FROM {table} WHERE chunk_id=?", (chunk_id,))
            self.connection.execute(
                "INSERT OR REPLACE INTO visual_artifacts VALUES (?, ?, ?)",
                (artifact.artifact_id, fingerprint, artifact.model_dump_json()),
            )
            for chunk in chunks:
                chunk.chunk_id = f"{artifact.artifact_id}:v{fingerprint[:12]}:c{chunk.chunk_index}"
                self.connection.execute(
                    "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        chunk.chunk_id,
                        chunk.source_id,
                        chunk.investigation_id,
                        chunk.filename,
                        chunk.source_url,
                        chunk.sha256,
                        chunk.physical_page,
                        chunk.chunk_index,
                        chunk.char_start,
                        chunk.char_end,
                        chunk.text,
                    ),
                )
                self.connection.execute(
                    "INSERT INTO chunks_fts VALUES (?, ?)", (chunk.chunk_id, chunk.text)
                )
                self.connection.execute(
                    "INSERT INTO visual_chunks VALUES (?, ?)",
                    (chunk.chunk_id, artifact.artifact_id),
                )
        return True

    def append_vectors(
        self, *, model_key: str, model: str, dimensions: int, vectors: dict[str, list[float]]
    ) -> None:
        """Add only new visual vectors; existing text vectors remain untouched."""
        ids = {r[0] for r in self.connection.execute("SELECT chunk_id FROM chunks")}
        if not set(vectors) <= ids or any(len(v) != dimensions for v in vectors.values()):
            raise ValueError("Vectors must match existing chunk IDs and namespace dimensions")
        with self.connection:
            self.connection.execute(
                "INSERT INTO vector_namespaces VALUES (?, 'openai', ?, NULL, ?, 1, NULL) "
                "ON CONFLICT(model_key) DO NOTHING",
                (model_key, model, dimensions),
            )
            found = self.connection.execute(
                "SELECT dimensions FROM vector_namespaces WHERE model_key=?",
                (model_key,),
            ).fetchone()
            if found[0] != dimensions:
                raise ValueError("Namespace dimensions differ")
            self.connection.executemany(
                "INSERT OR REPLACE INTO vectors VALUES (?, ?, ?)",
                [(model_key, key, encode_vector(value)) for key, value in vectors.items()],
            )

    def list_chunks(self) -> list[ChunkRecord]:
        rows = self.connection.execute(
            "SELECT * FROM chunks ORDER BY source_id, physical_page, chunk_index"
        ).fetchall()
        return [ChunkRecord.model_validate(dict(row)) for row in rows]

    def replace_vectors(
        self,
        *,
        model_key: str,
        provider: str,
        model: str,
        dimensions: int,
        vectors: dict[str, list[float]],
    ) -> None:
        chunk_ids = {
            row[0] for row in self.connection.execute("SELECT chunk_id FROM chunks").fetchall()
        }
        if set(vectors) != chunk_ids:
            missing = len(chunk_ids - set(vectors))
            unexpected = len(set(vectors) - chunk_ids)
            raise ValueError(
                f"Vector set must exactly match chunks: {missing} missing, {unexpected} unexpected"
            )
        if any(len(vector) != dimensions for vector in vectors.values()):
            raise ValueError("Vector dimensions do not match the namespace")
        with self.connection:
            self.connection.execute("DELETE FROM vectors WHERE model_key = ?", (model_key,))
            self.connection.execute(
                """
                INSERT INTO vector_namespaces
                    (model_key, provider, model, revision, dimensions, normalized, max_tokens)
                VALUES (?, ?, ?, NULL, ?, 1, NULL)
                ON CONFLICT(model_key) DO UPDATE SET
                    provider=excluded.provider,
                    model=excluded.model,
                    dimensions=excluded.dimensions,
                    normalized=excluded.normalized
                """,
                (model_key, provider, model, dimensions),
            )
            self.connection.executemany(
                "INSERT INTO vectors (model_key, chunk_id, vector) VALUES (?, ?, ?)",
                [
                    (model_key, chunk_id, encode_vector(vector))
                    for chunk_id, vector in vectors.items()
                ],
            )

    def figure_search(
        self,
        *,
        investigation_id: str | None = None,
        query_vector: list[float] | None = None,
        model_key: str | None = None,
        top_k: int = 8,
    ) -> list[dict[str, object]]:
        """Figure and table-image descriptions, ranked by similarity or in page order."""
        rows = self.connection.execute(
            """
            SELECT c.*, v.vector AS vector
            FROM visual_chunks AS vc
            JOIN chunks AS c ON c.chunk_id = vc.chunk_id
            LEFT JOIN vectors AS v ON v.chunk_id = c.chunk_id AND v.model_key = ?
            WHERE (? IS NULL OR lower(c.investigation_id) = lower(?))"""
            + self._visibility()[0]
            + """
            ORDER BY c.filename, c.physical_page, c.chunk_id
            """,
            (model_key, investigation_id, investigation_id, *self._visibility()[1]),
        ).fetchall()
        results = [dict(row) for row in rows]
        if query_vector is not None and model_key is not None:
            dimensions = len(query_vector)
            for result in results:
                blob = result.get("vector")
                result["score"] = (
                    cosine_similarity(query_vector, decode_vector(blob, dimensions))
                    if blob
                    else -1.0
                )
            results.sort(key=lambda item: -float(item["score"]))
        for result in results:
            result.pop("vector", None)
        return self._attach_visuals(results[:top_k])

    def dense_search(
        self,
        query_vector: list[float],
        *,
        model_key: str,
        investigation_id: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, object]]:
        namespace = self.connection.execute(
            "SELECT dimensions FROM vector_namespaces WHERE model_key = ?", (model_key,)
        ).fetchone()
        if namespace is None:
            raise ValueError(f"No stored vectors for {model_key}")
        dimensions = int(namespace["dimensions"])
        if len(query_vector) != dimensions:
            raise ValueError("Query vector dimensions do not match the stored namespace")
        rows = self.connection.execute(
            """
            SELECT c.*, v.vector
            FROM vectors AS v
            JOIN chunks AS c ON c.chunk_id = v.chunk_id
            WHERE v.model_key = ?
              AND (? IS NULL OR lower(c.investigation_id) = lower(?))"""
            + self._visibility()[0],
            (model_key, investigation_id, investigation_id, *self._visibility()[1]),
        ).fetchall()
        ranked = []
        for row in rows:
            result = dict(row)
            stored = decode_vector(result.pop("vector"), dimensions)
            result["score"] = cosine_similarity(query_vector, stored)
            ranked.append(result)
        ranked.sort(key=lambda item: (-float(item["score"]), str(item["chunk_id"])))
        return self._attach_visuals(ranked[:top_k])
