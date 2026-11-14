"""Retrieval and answer evaluation bound to corpus, code, and model versions.

Retrieval (hit@k, MRR) and answer quality (status, required terms, numerical
grounding) are scored separately. Visual-description fidelity cannot be checked
automatically; it is recorded as a manual review field.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .lexical import reciprocal_rank

Method = Literal["keyword", "dense", "hybrid"]
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


class EvalQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    split: Literal["development", "heldout"] = "development"
    category: Literal["prose", "figure", "table", "numeric", "ambiguity", "missing"] = "prose"
    investigation: str | None = None
    reviewed: bool = False
    reviewer: str | None = None
    source_id: str | None = None
    expected_pages: list[int] = Field(default_factory=list)
    expected_elements: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    expected_status: Literal["answered", "insufficient_evidence"] = "answered"
    # Each inner list holds acceptable alternatives, e.g. [["1,300", "1300"]].
    required_terms: list[list[str]] = Field(default_factory=list)
    expected_limits: str = ""
    notes: str = ""

    @model_validator(mode="after")
    def reviewed_needs_reviewer(self) -> Self:
        if self.reviewed and not (self.reviewer and self.reviewer.strip()):
            raise ValueError(f"{self.id}: reviewed questions require a reviewer")
        return self

    @property
    def has_retrieval_target(self) -> bool:
        return bool(self.expected_pages or self.expected_elements or self.expected_chunk_ids)


def is_match(question: EvalQuestion, result: dict[str, Any]) -> bool:
    if str(result.get("chunk_id")) in question.expected_chunk_ids:
        return True
    visual = result.get("visual") or {}
    if visual.get("artifact_id") in question.expected_elements:
        return True
    same_source = question.source_id is None or result.get("source_id") == question.source_id
    return same_source and result.get("physical_page") in question.expected_pages


def is_element_match(question: EvalQuestion, result: dict[str, Any]) -> bool:
    return (result.get("visual") or {}).get("artifact_id") in question.expected_elements


def score_retrieval(
    questions: list[EvalQuestion],
    search: Callable[[str, str | None, int], list[dict[str, Any]]],
) -> dict[str, Any]:
    scored = []
    for question in questions:
        if not question.has_retrieval_target:
            continue
        results = search(question.question, question.investigation, 5)
        flags = [is_match(question, r) for r in results]
        ids = [str(r["chunk_id"]) for r in results]
        matched = {ids[i] for i, flag in enumerate(flags) if flag}
        item: dict[str, Any] = {
            "id": question.id,
            "category": question.category,
            "hit_at_3": any(flags[:3]),
            "hit_at_5": any(flags[:5]),
            "mrr_at_5": reciprocal_rank(ids, matched),
            "result_pages": [r.get("physical_page") for r in results],
            "result_ids": ids,
        }
        if question.expected_elements:
            item["element_hit_at_5"] = any(is_element_match(question, r) for r in results[:5])
        scored.append(item)
    count = len(scored)

    def mean(key: str) -> float | None:
        values = [float(s[key]) for s in scored if key in s]
        return sum(values) / len(values) if values else None

    return {
        "question_count": count,
        "hit_at_3": mean("hit_at_3"),
        "hit_at_5": mean("hit_at_5"),
        "mrr_at_5": mean("mrr_at_5"),
        "element_hit_at_5": mean("element_hit_at_5"),
        "questions": scored,
    }


def _normalize_number(value: str) -> str:
    return value.replace(",", "")


def ungrounded_numbers(answer: dict[str, Any]) -> list[str]:
    """Numbers in a claim that appear in none of that claim's supporting quotes."""
    missing: list[str] = []
    for claim in answer.get("claims", []):
        quoted = {
            _normalize_number(n)
            for support in claim.get("supports", [])
            for n in NUMBER.findall(support.get("quote", ""))
        }
        missing.extend(
            n for n in NUMBER.findall(claim.get("text", "")) if _normalize_number(n) not in quoted
        )
    return missing


def score_answer(
    question: EvalQuestion, answer: dict[str, Any], results: list[dict[str, Any]]
) -> dict[str, Any]:
    text = " ".join(c.get("text", "") for c in answer.get("claims", [])).lower()
    status = answer.get("status")
    terms = [
        any(alt.lower() in text for alt in group)
        for group in question.required_terms
        if question.expected_status == "answered"
    ]
    by_id = {str(r["chunk_id"]): r for r in results}
    visual_supports = sorted(
        {
            (by_id.get(s["chunk_id"]) or {}).get("visual", {}).get("artifact_id", "")
            for c in answer.get("claims", [])
            for s in c.get("supports", [])
            if (by_id.get(s["chunk_id"]) or {}).get("visual")
        }
    )
    return {
        "id": question.id,
        "category": question.category,
        "expected_status": question.expected_status,
        "status": status,
        "status_correct": status == question.expected_status,
        "required_terms_present": all(terms) if terms else None,
        "ungrounded_numbers": ungrounded_numbers(answer),
        "claims_when_abstaining": status == "insufficient_evidence" and bool(answer.get("claims")),
        "cites_visual_artifacts": visual_supports,
        # Requires a person to compare the description against the crop.
        "visual_fidelity_review": "manual_required" if visual_supports else None,
        "expected_limits": question.expected_limits,
        "answer": answer,
    }


def summarize_answers(items: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [i for i in items if "error" not in i]
    answered_expected = [i for i in scored if i["expected_status"] == "answered"]
    abstain_expected = [i for i in scored if i["expected_status"] == "insufficient_evidence"]
    with_terms = [i for i in scored if i["required_terms_present"] is not None]

    def rate(values: list[bool]) -> float | None:
        return sum(values) / len(values) if values else None

    return {
        "question_count": len(items),
        "errors": len(items) - len(scored),
        "status_accuracy": rate([i["status_correct"] for i in scored]),
        "answered_when_expected": rate([i["status"] == "answered" for i in answered_expected]),
        "abstained_when_expected": rate(
            [i["status"] == "insufficient_evidence" for i in abstain_expected]
        ),
        "required_terms_rate": rate([bool(i["required_terms_present"]) for i in with_terms]),
        "answers_with_ungrounded_numbers": sum(bool(i["ungrounded_numbers"]) for i in scored),
        "manual_visual_reviews_needed": sum(bool(i["visual_fidelity_review"]) for i in scored),
        "questions": items,
    }


def _git_state(root: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args], cwd=root, capture_output=True, text=True, check=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    return {"commit": run("rev-parse", "HEAD") or None, "dirty": bool(run("status", "--porcelain"))}


def corpus_binding(store: Any) -> dict[str, Any]:
    digest = hashlib.sha256()
    for chunk_id, text in store.connection.execute(
        "SELECT chunk_id, text FROM chunks ORDER BY chunk_id"
    ):
        digest.update(chunk_id.encode() + b"\0" + text.encode() + b"\0")
    documents = [
        {"source_id": r[0], "sha256": r[1], "filename": r[2]}
        for r in store.connection.execute(
            "SELECT DISTINCT source_id, sha256, filename FROM pages ORDER BY source_id"
        )
    ]
    namespaces = [
        {"model_key": r[0], "vectors": r[1]}
        for r in store.connection.execute(
            "SELECT model_key, count(*) FROM vectors GROUP BY model_key ORDER BY model_key"
        )
    ]
    visuals = [
        {"artifact_id": r[0], "fingerprint": r[1]}
        for r in store.connection.execute(
            "SELECT artifact_id, fingerprint FROM visual_artifacts ORDER BY artifact_id"
        )
    ]
    return {
        "chunk_fingerprint": digest.hexdigest(),
        "chunks": store.connection.execute("SELECT count(*) FROM chunks").fetchone()[0],
        "documents": documents,
        "vector_namespaces": namespaces,
        "visual_artifacts": visuals,
    }


def run_binding(
    *, root: Path, questions_path: Path, store: Any, config: Any, options: dict[str, Any]
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "questions_file": str(questions_path),
        "questions_sha256": hashlib.sha256(questions_path.read_bytes()).hexdigest(),
        "code": _git_state(root),
        "corpus": corpus_binding(store),
        "embedding_model": config.embedding_model or None,
        "answer_model": config.answer_model or None,
        "options": options,
    }
