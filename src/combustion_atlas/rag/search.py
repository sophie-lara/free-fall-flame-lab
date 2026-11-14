"""Shared retrieval for the command line and local application."""

from __future__ import annotations

from collections.abc import Callable
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
    progress: Callable[[str, str], None] | None = None,
) -> list[dict[str, object]]:
    def say(stage: str, message: str) -> None:
        if progress is not None:
            progress(stage, message)

    if method == "keyword":
        say("keyword", "Searching the keyword index")
        results = store.search(question, investigation, top_k)
        say("retrieved", f"Found {len(results)} matching passages")
        return results
    provider = OpenAIEmbeddingProvider(ProviderConfig.from_environment())
    # Check availability before paying to embed the question.
    if (
        store.connection.execute(
            "SELECT 1 FROM vectors WHERE model_key = ? LIMIT 1", (provider.model_key,)
        ).fetchone()
        is None
    ):
        raise ValueError("Generate document embeddings before using semantic or hybrid search")
    say("embedding", "Embedding the question for semantic search")
    query_vector = provider.embed([question])[0]
    say("semantic", "Comparing against stored passage embeddings")
    dense = store.dense_search(
        query_vector,
        model_key=provider.model_key,
        investigation_id=investigation,
        top_k=max(top_k * 3, 10),
    )
    if method == "dense":
        say("retrieved", f"Selected the {min(top_k, len(dense))} closest passages")
        return dense[:top_k]
    say("keyword", "Searching the keyword index")
    keyword = store.search(question, investigation, max(top_k * 3, 10))
    say("ranking", f"Merging {len(keyword)} keyword and {len(dense)} semantic matches")
    ranked = reciprocal_rank_fusion(
        [
            [str(item["chunk_id"]) for item in keyword],
            [str(item["chunk_id"]) for item in dense],
        ]
    )
    by_id = {str(item["chunk_id"]): item for item in [*keyword, *dense]}
    fused = [{**by_id[key], "score": score} for key, score in ranked[:top_k]]
    say("retrieved", f"Selected {len(fused)} passages")
    return fused
