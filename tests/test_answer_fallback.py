"""Backup answer model and identifier-aware number checks."""

import dataclasses
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from combustion_atlas.providers import ProviderConfig
from combustion_atlas.providers.openai_answers import (
    Claim,
    GroundedAnswer,
    OpenAIAnswerProvider,
    Support,
    ungrounded_numbers,
)

CONTEXT: list[dict[str, object]] = [
    {
        "chunk_id": "row:PSI-25:O12",
        "text": "Table row — BASS-II: PSI-25 O12\n- initial_co = OR ppm  [source: OR]",
    }
]
GOOD = GroundedAnswer(
    status="answered",
    claims=[
        Claim(
            text="For test O12 the initial CO reading is recorded as OR.",
            supports=[Support(chunk_id="row:PSI-25:O12", quote="initial_co = OR ppm")],
        )
    ],
    limitations=[],
)


def config(**changes: Any) -> ProviderConfig:
    base = ProviderConfig(
        embedding_provider="openai",
        answer_provider="openai",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=None,
        embedding_batch_size=64,
        answer_model="gpt-6-luna",
        openai_api_key_present=True,
    )
    return dataclasses.replace(base, **changes)


class Client:
    def __init__(self, result: Any) -> None:
        self.result, self.calls = result, []
        self.responses = self

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return SimpleNamespace(output_parsed=self.result)


def down() -> Exception:
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    return openai.InternalServerError(
        "down", response=httpx.Response(503, request=request), body=None
    )


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("combustion_atlas.providers.retry.time.sleep", lambda _: None)
    monkeypatch.setattr("time.sleep", lambda _: None)


def test_backup_answers_when_primary_is_down() -> None:
    primary, backup = Client(down()), Client(GOOD)
    provider = OpenAIAnswerProvider(
        config(fallback_model="gpt-5-mini"), client=primary, fallback_client=backup
    )
    stages: list[str] = []
    answer = provider.answer("O12 CO?", CONTEXT, progress=lambda s, _m: stages.append(s))
    assert answer.status == "answered"
    assert len(primary.calls) == 4  # retried first
    assert backup.calls[0]["model"] == "gpt-5-mini"
    assert backup.calls[0]["reasoning"] == {"effort": "low"}
    assert backup.calls[0]["max_output_tokens"] > 4000  # room for hidden reasoning
    assert "fallback" in stages
    assert provider.answered_by() == {
        "model": "gpt-5-mini",
        "provider": "backup provider",
        "backup": True,
    }


def test_primary_answers_normally_and_no_backup_means_error() -> None:
    primary, backup = Client(GOOD), Client(GOOD)
    provider = OpenAIAnswerProvider(
        config(fallback_model="gpt-5-mini"), client=primary, fallback_client=backup
    )
    provider.answer("O12 CO?", CONTEXT)
    assert not backup.calls and provider.answered_by()["backup"] is False
    assert primary.calls[0]["max_output_tokens"] == 4000
    assert "reasoning" not in primary.calls[0]

    alone = OpenAIAnswerProvider(config(), client=Client(down()))
    assert alone.fallback is None
    with pytest.raises(openai.InternalServerError):
        alone.answer("O12 CO?", CONTEXT)


def test_backup_needs_model_endpoint_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MODEL", "BASE_URL", "API_KEY"):
        monkeypatch.delenv(f"COMBUSTION_ATLAS_FALLBACK_{name}", raising=False)
    assert not ProviderConfig.from_environment().fallback_enabled
    monkeypatch.setenv("COMBUSTION_ATLAS_FALLBACK_MODEL", "gpt-5-mini")
    monkeypatch.setenv(
        "COMBUSTION_ATLAS_FALLBACK_BASE_URL", "https://x.openai.azure.com/openai/v1/"
    )
    assert not ProviderConfig.from_environment().fallback_enabled
    monkeypatch.setenv("COMBUSTION_ATLAS_FALLBACK_API_KEY", "k")
    status = ProviderConfig.from_environment()
    assert status.fallback_enabled
    assert "fallback_base_url" not in status.public_status()


def claim(text: str, quote: str) -> Claim:
    return Claim(text=text, supports=[Support(chunk_id="row:PSI-25:O12", quote=quote)])


def test_cited_identifiers_are_not_measurements() -> None:
    passages = {str(c["chunk_id"]): str(c["text"]) for c in CONTEXT}
    ok = claim("For BASS-II test O12 (PSI-25) initial CO was OR.", "initial_co = OR ppm")
    assert ungrounded_numbers(ok, passages) == []
    assert ungrounded_numbers(ok) == ["12", "25"]  # without passages: strict as before
    other_test = claim("Test O13 initial CO was OR.", "initial_co = OR ppm")
    assert ungrounded_numbers(other_test, passages) == ["13"]
    invented = claim("Test O12 initial CO was 40 ppm.", "initial_co = OR ppm")
    assert ungrounded_numbers(invented, passages) == ["40"]
