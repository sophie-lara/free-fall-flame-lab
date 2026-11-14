import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from combustion_atlas.evaluation.__main__ import main
from combustion_atlas.evaluation.retrieval import (
    EvalQuestion,
    corpus_binding,
    score_answer,
    score_retrieval,
    summarize_answers,
    ungrounded_numbers,
)
from combustion_atlas.rag.chunk import chunk_page
from combustion_atlas.rag.models import PageRecord
from combustion_atlas.rag.store import DocumentStore


def question(**changes: object) -> EvalQuestion:
    base = {"id": "q", "question": "How many tests?", "source_id": "s", "expected_pages": [3]}
    return EvalQuestion.model_validate({**base, **changes})


def result(page: int, chunk: str, source: str = "s", artifact: str | None = None) -> dict:
    item: dict = {"chunk_id": chunk, "physical_page": page, "source_id": source}
    if artifact:
        item["visual"] = {"artifact_id": artifact}
    return item


def test_page_element_and_source_matching() -> None:
    results = [result(3, "other:p3", source="other"), result(9, "s:p9"), result(3, "s:p3")]
    scored = score_retrieval([question()], lambda *_: results)
    assert scored["questions"][0]["hit_at_3"] and scored["mrr_at_5"] == pytest.approx(1 / 3)
    figure = question(expected_pages=[], expected_elements=["fig:1"])
    hits = score_retrieval([figure], lambda *_: [result(1, "a"), result(1, "v", artifact="fig:1")])
    assert hits["element_hit_at_5"] == 1.0 and hits["mrr_at_5"] == 0.5


def test_missing_evidence_questions_are_excluded_from_retrieval_metrics() -> None:
    missing = question(expected_pages=[], expected_status="insufficient_evidence")
    assert score_retrieval([missing], lambda *_: [])["question_count"] == 0


def test_reviewed_requires_reviewer() -> None:
    with pytest.raises(ValidationError):
        question(reviewed=True)


def test_numbers_must_appear_in_the_claims_own_quotes() -> None:
    answer = {
        "claims": [
            {"text": "1,300 tests ran at 9 cm/s", "supports": [{"quote": "1300 tests at 8 cm/s"}]}
        ]
    }
    assert ungrounded_numbers(answer) == ["9"]


def test_answer_scoring_separates_status_terms_and_visual_review() -> None:
    q = question(required_terms=[["126"], ["tests", "runs"]])
    answer = {
        "status": "answered",
        "claims": [{"text": "126 tests.", "supports": [{"chunk_id": "v", "quote": "126 tests"}]}],
    }
    item = score_answer(q, answer, [result(3, "v", artifact="fig:1")])
    assert item["status_correct"] and item["required_terms_present"]
    assert item["visual_fidelity_review"] == "manual_required"
    abstain = score_answer(
        question(expected_status="insufficient_evidence"),
        {"status": "answered", "claims": []},
        [],
    )
    summary = summarize_answers([item, abstain, {"id": "x", "error": "ValueError"}])
    assert summary["errors"] == 1
    assert summary["status_accuracy"] == 0.5
    assert summary["abstained_when_expected"] == 0.0


def test_cli_scores_reviewed_split_and_binds_corpus(tmp_path: Path) -> None:
    page = PageRecord(
        source_id="s", filename="r.pdf", sha256="a" * 64, physical_page=3, text="126 tests ran."
    )
    database = tmp_path / "rag.sqlite3"
    with DocumentStore(database) as store:
        store.replace([page], chunk_page(page))
        binding = corpus_binding(store)
    questions = tmp_path / "questions.json"
    rows = [
        {
            "id": "a",
            "question": "How many tests ran?",
            "expected_pages": [3],
            "reviewed": True,
            "reviewer": "R",
        },
        {"id": "b", "question": "unreviewed", "expected_pages": [3]},
        {
            "id": "c",
            "question": "held out",
            "split": "heldout",
            "expected_pages": [3],
            "reviewed": True,
            "reviewer": "R",
        },
    ]
    questions.write_text(json.dumps({"questions": rows}), encoding="utf-8")
    output = tmp_path / "report.json"
    assert main([str(questions), "--database", str(database), "--output", str(output)]) == 0
    report = json.loads(output.read_text())
    assert report["status"] == "reviewed_questions"
    assert report["binding"]["options"]["question_ids"] == ["a"]
    assert report["binding"]["corpus"]["chunk_fingerprint"] == binding["chunk_fingerprint"]
    assert report["retrieval"]["keyword"]["hit_at_3"] == 1.0
    with pytest.raises(SystemExit):
        main([str(questions), "--output", str(output), "--methods", "dense"])
