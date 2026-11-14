"""Reviewed-question metrics for lexical retrieval."""

from __future__ import annotations

from typing import Any


def reciprocal_rank(result_ids: list[str], expected_ids: set[str], cutoff: int = 5) -> float:
    for rank, result_id in enumerate(result_ids[:cutoff], start=1):
        if result_id in expected_ids:
            return 1.0 / rank
    return 0.0


def score_questions(questions: list[dict[str, Any]], search: Any) -> dict[str, Any]:
    scored = []
    for question in questions:
        if not question.get("reviewed"):
            continue
        results = search(question["question"], question.get("investigation"), 5)
        result_ids = [str(result["chunk_id"]) for result in results]
        expected = set(question.get("expected_chunk_ids", []))
        scored.append(
            {
                "id": question["id"],
                "hit_at_3": bool(expected.intersection(result_ids[:3])),
                "hit_at_5": bool(expected.intersection(result_ids[:5])),
                "mrr_at_5": reciprocal_rank(result_ids, expected),
                "result_ids": result_ids,
            }
        )
    count = len(scored)
    return {
        "question_count": count,
        "hit_at_3": sum(item["hit_at_3"] for item in scored) / count if count else None,
        "hit_at_5": sum(item["hit_at_5"] for item in scored) / count if count else None,
        "mrr_at_5": sum(item["mrr_at_5"] for item in scored) / count if count else None,
        "questions": scored,
    }
