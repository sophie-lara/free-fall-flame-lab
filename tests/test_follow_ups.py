"""Follow-up questions: history validation, two-pass retrieval and answer context."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from combustion_atlas.app.server import EvidenceRequest
from combustion_atlas.providers import ProviderConfig
from combustion_atlas.providers.openai_answers import GroundedAnswer, OpenAIAnswerProvider
from combustion_atlas.rag.chunk import chunk_page
from combustion_atlas.rag.models import PageRecord
from combustion_atlas.rag.search import retrieve_conversation
from combustion_atlas.rag.store import DocumentStore


def store_with(tmp_path: Path) -> DocumentStore:
    texts = {
        "a": "Helium dilution changed FLEX droplet flame extinction diameters.",
        "b": "Carbon dioxide dilution of methanol droplets ranged up to 70 percent.",
        "c": "Opposed flow flame spread over thin PMMA sheets in BASS-II.",
    }
    pages = [
        PageRecord(source_id=k * 16, filename=f"{k}.pdf", sha256=k * 64, physical_page=1, text=t)
        for k, t in texts.items()
    ]
    store = DocumentStore(tmp_path / "rag.sqlite3")
    store.replace(pages, [c for p in pages for c in chunk_page(p)])
    return store


def test_history_is_optional_bounded_and_strict() -> None:
    assert EvidenceRequest(question="q").history == []
    ok = EvidenceRequest(question="q", history=[{"question": "earlier", "answer": "a"}])
    assert ok.history[0].question == "earlier"
    with pytest.raises(ValidationError):
        EvidenceRequest(question="q", history=[{"question": "x"}] * 7)
    with pytest.raises(ValidationError):
        EvidenceRequest(question="q", history=[{"question": "x", "role": "system"}])


def test_follow_up_retrieval_uses_the_previous_question(tmp_path: Path) -> None:
    with store_with(tmp_path) as store:
        alone = retrieve_conversation(store, "What about FLEX droplets?", [])
        steps: list[str] = []
        followed = retrieve_conversation(
            store,
            "What about carbon dioxide?",
            ["How does dilution affect methanol droplets?"],
            progress=lambda stage, _m: steps.append(stage),
        )
    assert alone and alone[0]["filename"] == "a.pdf"
    assert followed[0]["filename"] == "b.pdf"
    assert "context" in steps


def test_earlier_turns_reach_the_model_only_as_context() -> None:
    calls: list[dict[str, Any]] = []

    class Client:
        responses = None

        def __init__(self) -> None:
            self.responses = self

        def parse(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return SimpleNamespace(
                output_parsed=GroundedAnswer(
                    status="insufficient_evidence", claims=[], limitations=[]
                )
            )

    config = ProviderConfig(
        embedding_provider="openai",
        answer_provider="openai",
        embedding_model="m",
        embedding_dimensions=None,
        embedding_batch_size=64,
        answer_model="gpt-6-luna",
        openai_api_key_present=True,
    )
    provider = OpenAIAnswerProvider(config, client=Client())
    history = [{"question": f"q{i}", "answer": "x" * 3000} for i in range(5)]
    provider.answer("What about CO2?", [{"chunk_id": "c", "text": "t"}], history=history)
    import json

    sent = json.loads(calls[0]["input"])
    assert [t["question"] for t in sent["earlier_turns"]] == ["q2", "q3", "q4"]  # last three
    assert all(len(t["answer"]) <= 1500 for t in sent["earlier_turns"])
    assert "Never cite them or take facts from them" in calls[0]["instructions"]
