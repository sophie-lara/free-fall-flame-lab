"""Transient OpenAI failures are retried with backoff; failed answers are refunded."""

from pathlib import Path

import httpx
import openai
import pytest

from combustion_atlas.app.core import EvidenceRequest, ask_evidence
from combustion_atlas.app.usage import PaidCallLimiter
from combustion_atlas.providers.retry import call_with_retries, describe
from combustion_atlas.rag.chunk import chunk_page
from combustion_atlas.rag.models import PageRecord
from combustion_atlas.rag.store import DocumentStore

REQUEST = httpx.Request("POST", "https://api.openai.com/v1/responses")


def status_error(cls: type, code: int, retry_after: str | None = None) -> Exception:
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(code, request=REQUEST, headers=headers)
    return cls("message with sk-secret", response=response, body=None)  # type: ignore[call-arg]


def test_transient_errors_retry_with_growing_delays() -> None:
    failures = [status_error(openai.RateLimitError, 429), openai.APITimeoutError(request=REQUEST)]
    delays: list[float] = []

    def flaky() -> str:
        if failures:
            raise failures.pop(0)
        return "ok"

    assert call_with_retries(flaky, what="test", sleep=delays.append) == "ok"
    assert len(delays) == 2 and 0.3 <= delays[0] <= 0.7 and 0.7 <= delays[1] <= 1.3


def test_retry_after_is_honored_and_client_errors_are_not_retried() -> None:
    delays: list[float] = []
    errors = [status_error(openai.RateLimitError, 429, retry_after="3")]

    def limited() -> str:
        if errors:
            raise errors.pop(0)
        return "ok"

    assert call_with_retries(limited, what="test", sleep=delays.append) == "ok"
    assert delays == [3.0]
    calls = []

    def bad_request() -> None:
        calls.append(1)
        raise status_error(openai.BadRequestError, 400)

    with pytest.raises(openai.BadRequestError):
        call_with_retries(bad_request, what="test", sleep=lambda _: None)
    assert len(calls) == 1


def test_gives_up_after_attempts_and_logs_safely(caplog: pytest.LogCaptureFixture) -> None:
    calls = []

    def down() -> None:
        calls.append(1)
        raise status_error(openai.InternalServerError, 503)

    with pytest.raises(openai.InternalServerError):
        call_with_retries(down, what="answer", attempts=4, sleep=lambda _: None)
    assert len(calls) == 4
    assert "InternalServerError status=503" in caplog.text
    assert "sk-secret" not in caplog.text  # messages are never logged
    assert describe(status_error(openai.RateLimitError, 429)) == "RateLimitError status=429"


def test_failed_answer_is_refunded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page = PageRecord(
        source_id="a" * 16,
        filename="r.pdf",
        sha256="a" * 64,
        physical_page=1,
        text="Oxygen concentration affects flame spread.",
    )
    database = tmp_path / "data/embeddings/rag.sqlite3"
    with DocumentStore(database) as store:
        store.replace([page], chunk_page(page))
    workspace = type("W", (), {"database": database, "read_database": database})()
    limiter = PaidCallLimiter(tmp_path / "paid.json", daily_limit=3)

    class FailingProvider:
        def __init__(self, _config: object) -> None: ...

        def answered_by(self) -> dict[str, object]:
            return {"model": "m", "provider": "OpenAI", "backup": False}

        def answer(self, *_: object, **__: object) -> None:
            raise status_error(openai.InternalServerError, 503)

    monkeypatch.setattr("combustion_atlas.app.core.OpenAIAnswerProvider", FailingProvider)
    request = EvidenceRequest(
        question="oxygen flame spread",
        method="keyword",
        generate_answer=True,
        allow_provider_calls=True,
    )
    payload = ask_evidence(workspace, request, limiter=limiter)  # type: ignore[arg-type]
    assert "did not count" in str(payload["answer_unavailable"])
    assert limiter.status()["remaining_today"] == 3  # refunded

    class WorkingProvider(FailingProvider):
        def answer(self, *_: object, **__: object):  # type: ignore[override]
            from combustion_atlas.providers.openai_answers import GroundedAnswer

            return GroundedAnswer(status="insufficient_evidence", claims=[], limitations=[])

    monkeypatch.setattr("combustion_atlas.app.core.OpenAIAnswerProvider", WorkingProvider)
    ask_evidence(workspace, request, limiter=limiter)  # type: ignore[arg-type]
    assert limiter.status()["remaining_today"] == 2  # successful answers still count
