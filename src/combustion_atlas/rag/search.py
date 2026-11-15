"""Shared retrieval for the command line and local application."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Literal

from combustion_atlas.providers import OpenAIEmbeddingProvider, ProviderConfig
from combustion_atlas.retrieval import reciprocal_rank_fusion

from .store import DocumentStore

# "Show me figures from BASS-II": a request to browse figures, not a question to answer.
_VISUAL_PLURAL = re.compile(
    r"\b(figures|figs|images|photos|photographs|pictures|plots|graphs|charts|diagrams|"
    r"schematics|visuals)\b",
    re.IGNORECASE,
)
_SPECIFIC_FIGURE = re.compile(r"\bfig(?:ure)?s?\.?\s*[A-Z]?\d", re.IGNORECASE)
# Investigation names visitors type, most specific first.
_INVESTIGATION_NAMES = [
    (re.compile(r"\bbass[\s-]*(?:ii|2)\b", re.IGNORECASE), "PSI-25"),
    (re.compile(r"\bbass\b", re.IGNORECASE), "PSI-26"),
    (re.compile(r"\bflex[\s-]*(?:ii|2)\b", re.IGNORECASE), "PSI-68"),
    (re.compile(r"\bflex\b", re.IGNORECASE), "PSI-69"),
]
FIGURE_BROWSE_LIMIT = 8


def wants_figures(question: str) -> bool:
    """True for figure-browsing requests ("figures from BASS-II"), not one specific figure."""
    return bool(_VISUAL_PLURAL.search(question)) and not _SPECIFIC_FIGURE.search(question)


def named_investigation(question: str) -> str | None:
    for pattern, investigation in _INVESTIGATION_NAMES:
        if pattern.search(question):
            return investigation
    return None


def retrieve(
    store: DocumentStore,
    question: str,
    *,
    method: Literal["keyword", "dense", "hybrid"] = "keyword",
    investigation: str | None = None,
    top_k: int = 5,
    progress: Callable[[str, str], None] | None = None,
    visible_sources: frozenset[str] = frozenset(),
) -> list[dict[str, object]]:
    # Quarantined visitor uploads are only searchable by the browser that uploaded them.
    store.visible_sources = frozenset(visible_sources)

    def say(stage: str, message: str) -> None:
        if progress is not None:
            progress(stage, message)

    if wants_figures(question):
        scope = investigation or named_investigation(question)
        top = max(top_k, FIGURE_BROWSE_LIMIT)
        say("figures", f"Looking for figures{f' from {scope}' if scope else ''}")
        vector, key = None, None
        if method != "keyword":
            provider = OpenAIEmbeddingProvider(ProviderConfig.from_environment())
            say("embedding", "Embedding the request to rank figures by relevance")
            vector, key = provider.embed([question])[0], provider.model_key
        figures = store.figure_search(
            investigation_id=scope, query_vector=vector, model_key=key, top_k=top
        )
        if figures:
            say("retrieved", f"Found {len(figures)} figures")
            return figures
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
    cards: list[dict[str, object]] = []
    if ids:
        placeholders = ",".join("?" * len(ids))
        rows = store.connection.execute(
            f"SELECT * FROM chunks WHERE chunk_id IN ({placeholders})"
            " AND (? IS NULL OR lower(investigation_id) = lower(?))",
            (*ids, investigation, investigation),
        ).fetchall()
        cards = store._attach_visuals([{**dict(row), "score": 1.0} for row in rows])
    if cards:
        say("records", f"Found {len(cards)} table record(s) named in the question")
    return cards + _pinned_rows(store, question, investigation, say)


def _pinned_rows(
    store: DocumentStore,
    question: str,
    investigation: str | None,
    say: Callable[[str, str], None],
) -> list[dict[str, object]]:
    """Reviewed table rows named by test ID, or by two or more of their exact values."""
    from .row_match import match_rows

    rows = [
        r
        for r in store.record_rows()
        if investigation is None or str(r["investigation_id"]).lower() == investigation.lower()
    ]
    if not rows:
        return []
    named = {str(r["row_id"]) for r in store.rows_for_identifiers(question)}
    found = [{**r, "match": []} for r in rows if str(r["row_id"]) in named]
    found += [r for r in match_rows(question, rows) if str(r["row_id"]) not in named]
    if found:
        say("records", f"Found {len(found)} table row(s) matching the question")
    return [row_chunk(r) for r in found]


def row_chunk(row: dict[str, object]) -> dict[str, object]:
    """A matched row in the shape of a retrieved chunk, with its structure attached."""
    source = row["source"]
    assert isinstance(source, dict)
    text = str(row["text"])
    return {
        "chunk_id": row["row_id"],
        "source_id": str(source["source_sha256"])[:16],
        "investigation_id": row["investigation_id"],
        "filename": source["file"],
        "source_url": source["source_url"],
        "sha256": source["source_sha256"],
        "physical_page": source["page"] or 0,
        "chunk_index": 0,
        "char_start": 0,
        "char_end": len(text),
        "text": text,
        "score": 1.0,
        "record_card": {
            "kind": "row",
            "test_id": row["test_id"],
            "table_title": row["table_title"],
            "card_id": row["card_id"],
            "evidence_kind": row["evidence_kind"],
            "review_action": row["review_action"],
            "locator": row["locator"],
            "provenance": row.get("provenance") or "",
            "values": row["values"],
            "caveats": row["caveats"],
            "open_questions": row["open_questions"],
            "match": row.get("match") or [],
        },
    }


def _merge_pinned(
    pinned: list[dict[str, object]], results: list[dict[str, object]], top_k: int
) -> list[dict[str, object]]:
    seen = {str(p["chunk_id"]) for p in pinned}
    rest = [r for r in results if str(r["chunk_id"]) not in seen]
    return [*pinned, *rest][: max(top_k, len(pinned))]


FOLLOW_UP_TURNS = 3


def retrieve_conversation(
    store: DocumentStore,
    question: str,
    history: list[str],
    *,
    method: Literal["keyword", "dense", "hybrid"] = "keyword",
    investigation: str | None = None,
    top_k: int = 5,
    progress: Callable[[str, str], None] | None = None,
    visible_sources: frozenset[str] = frozenset(),
) -> list[dict[str, object]]:
    """Retrieve for a follow-up: the question alone, and with the previous question.

    "What about FLEX?" needs the earlier question to find anything; a change of topic
    should not be dragged back to it. Both result lists are merged by rank fusion.
    """
    current = retrieve(
        store,
        question,
        method=method,
        investigation=investigation,
        top_k=top_k,
        progress=progress,
        visible_sources=visible_sources,
    )
    earlier = [q for q in history[-FOLLOW_UP_TURNS:] if q.strip()]
    if not earlier:
        return current
    if progress is not None:
        progress("context", "Adding the previous question as context for this follow-up")
    with_context = retrieve(
        store,
        f"{earlier[-1]} {question}",
        method=method,
        investigation=investigation,
        top_k=top_k,
        visible_sources=visible_sources,
    )
    ranked = reciprocal_rank_fusion(
        [[str(r["chunk_id"]) for r in current], [str(r["chunk_id"]) for r in with_context]]
    )
    by_id = {str(r["chunk_id"]): r for r in [*with_context, *current]}
    limit = max(top_k, len(current), len(with_context))
    merged = [by_id[key] for key, _score in ranked[:limit]]
    if progress is not None:
        progress("retrieved", f"Selected {len(merged)} passages using the conversation")
    return merged
