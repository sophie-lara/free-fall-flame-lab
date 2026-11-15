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

    pinned = _pinned_cards(store, question, investigation, say)
    if method == "keyword":
        say("keyword", "Searching the keyword index")
        results = store.search(question, investigation, top_k)
        say("retrieved", f"Found {len(results)} matching passages")
        return _merge_pinned(pinned, results, top_k)
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
        return _merge_pinned(pinned, dense, top_k)
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
    return _merge_pinned(pinned, fused, top_k)


def _pinned_cards(
    store: DocumentStore,
    question: str,
    investigation: str | None,
    say: Callable[[str, str], None],
) -> list[dict[str, object]]:
    """Exact test-ID matches to reviewed table records, looked up deterministically."""
    ids = store.cards_for_identifiers(question)
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    rows = store.connection.execute(
        f"SELECT * FROM chunks WHERE chunk_id IN ({placeholders})"
        " AND (? IS NULL OR lower(investigation_id) = lower(?))",
        (*ids, investigation, investigation),
    ).fetchall()
    cards = store._attach_visuals([{**dict(row), "score": 1.0} for row in rows])
    if cards:
        say("records", f"Found {len(cards)} table record(s) named in the question")
    return cards


def _merge_pinned(
    pinned: list[dict[str, object]], results: list[dict[str, object]], top_k: int
) -> list[dict[str, object]]:
    seen = {str(p["chunk_id"]) for p in pinned}
    rest = [r for r in results if str(r["chunk_id"]) not in seen]
    return [*pinned, *rest][: max(top_k, len(pinned))]
