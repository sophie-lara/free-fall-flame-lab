"""Shared retrieval for the command line and local application."""

from __future__ import annotations

from typing import Literal

from combustion_atlas.providers import OpenAIEmbeddingProvider, ProviderConfig
from combustion_atlas.retrieval import reciprocal_rank_fusion

from .store import DocumentStore


def retrieve(
    store: DocumentStore,
    question: str,
    *,
    method: Literal["keyword", "dense", "hybrid"] = "keyword",
    investigation: str | None = None,
    top_k: int = 5,
) -> list[dict[str, object]]:
    if method == "keyword":
        return store.search(question, investigation, top_k)
    provider = OpenAIEmbeddingProvider(ProviderConfig.from_environment())
    # Check availability before paying to embed the question.
    if (
        store.connection.execute(
            "SELECT 1 FROM vectors WHERE model_key = ? LIMIT 1", (provider.model_key,)
        ).fetchone()
        is None
    ):
        raise ValueError("Generate document embeddings before using semantic or hybrid search")
    dense = store.dense_search(
        provider.embed([question])[0],
        model_key=provider.model_key,
        investigation_id=investigation,
        top_k=max(top_k * 3, 10),
    )
    if method == "dense":
        return dense[:top_k]
    keyword = store.search(question, investigation, max(top_k * 3, 10))
    ranked = reciprocal_rank_fusion(
        [
            [str(item["chunk_id"]) for item in keyword],
            [str(item["chunk_id"]) for item in dense],
        ]
    )
    by_id = {str(item["chunk_id"]): item for item in [*keyword, *dense]}
    return [{**by_id[key], "score": score} for key, score in ranked[:top_k]]
