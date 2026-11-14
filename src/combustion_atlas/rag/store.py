"""SQLite FTS5 storage for page-bounded document chunks."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .models import ChunkRecord, PageRecord
from .vectors import cosine_similarity, decode_vector, encode_vector


class DocumentStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

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
                tokenize='unicode61'
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
            """
        )

    def replace(self, pages: list[PageRecord], chunks: list[ChunkRecord]) -> None:
        with self.connection:
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

    def search(
        self, question: str, investigation_id: str | None = None, top_k: int = 5
    ) -> list[dict[str, object]]:
        tokens = re.findall(r"[\w-]+", question, flags=re.UNICODE)
        if not tokens:
            return []
        query = " ".join(f'"{token}"' for token in tokens)
        rows = self.connection.execute(
            """
            SELECT c.*, bm25(chunks_fts) AS score
            FROM chunks_fts
            JOIN chunks AS c ON c.chunk_id = chunks_fts.chunk_id
            WHERE chunks_fts MATCH ?
              AND (? IS NULL OR lower(c.investigation_id) = lower(?))
            ORDER BY score
            LIMIT ?
            """,
            (query, investigation_id, investigation_id, top_k),
        ).fetchall()
        return [dict(row) for row in rows]

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
              AND (? IS NULL OR lower(c.investigation_id) = lower(?))
            """,
            (model_key, investigation_id, investigation_id),
        ).fetchall()
        ranked = []
        for row in rows:
            result = dict(row)
            stored = decode_vector(result.pop("vector"), dimensions)
            result["score"] = cosine_similarity(query_vector, stored)
            ranked.append(result)
        ranked.sort(key=lambda item: (-float(item["score"]), str(item["chunk_id"])))
        return ranked[:top_k]
