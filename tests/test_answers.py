"""Grounding checks run offline; no secret or paid request is needed."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from combustion_atlas.providers.config import ProviderConfig
from combustion_atlas.providers.openai_answers import (
    GroundedAnswer,
    OpenAIAnswerProvider,
    validate_support,
)


def answer(
    chunk_id: str = "p1", quote: str = "Samples were tested at 22% oxygen."
) -> GroundedAnswer:
    return GroundedAnswer.model_validate(
        {
            "status": "answered",
            "claims": [
                {
                    "text": "The reported oxygen was 22%.",
                    "supports": [{"chunk_id": chunk_id, "quote": quote}],
                }
            ],
            "limitations": ["One source only."],
        }
    )


CONTEXT = [{"chunk_id": "p1", "text": "Samples were tested at 22% oxygen."}]


def test_citations_require_known_chunks_and_exact_excerpts() -> None:
    validate_support(answer(), CONTEXT)
    for invalid in (answer("invented"), answer(quote="Samples were tested at 99% oxygen.")):
        with pytest.raises(ValueError, match="invalid supporting excerpt"):
            validate_support(invalid, CONTEXT)
    with pytest.raises(ValueError, match="requires supported claims"):
        validate_support(GroundedAnswer(status="answered", claims=[], limitations=[]), CONTEXT)


def test_answer_provider_validates_output_and_abstains_without_calling() -> None:
    config = ProviderConfig(
        "openai", "openai", "text-embedding-3-small", 1536, 64, "test-model", False
    )
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(output_parsed=answer())
    provider = OpenAIAnswerProvider(config, client=client)
    assert provider.answer("What oxygen?", []).status == "insufficient_evidence"
    client.responses.parse.assert_not_called()
    assert provider.answer("What oxygen?", CONTEXT).status == "answered"
    assert client.responses.parse.call_args.kwargs["store"] is False
    client.responses.parse.return_value = SimpleNamespace(output_parsed=answer("invented"))
    with pytest.raises(ValueError):
        provider.answer("What oxygen?", CONTEXT)


def test_answer_repairs_invalid_citations_once_and_keeps_unicode_input() -> None:
    config = ProviderConfig(
        "openai", "openai", "text-embedding-3-small", 1536, 64, "test-model", False
    )
    client = Mock()
    context = [{"chunk_id": "p1", "text": "BASS–II tested samples."}]
    valid = answer(quote="BASS–II tested samples.")
    client.responses.parse.side_effect = [
        SimpleNamespace(output_parsed=answer("unknown")),
        SimpleNamespace(output_parsed=valid),
    ]
    provider = OpenAIAnswerProvider(config, client=client)
    assert provider.answer("Which experiment?", context) == valid
    assert client.responses.parse.call_count == 2
    assert "BASS–II" in client.responses.parse.call_args.kwargs["input"]
