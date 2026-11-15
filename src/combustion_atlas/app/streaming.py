"""Stream evidence-answer progress as newline-delimited JSON (NDJSON).

Each line is one event: {"type": "progress", "stage", "message", "elapsed_s"},
then exactly one {"type": "result", ...same payload as /api/ask...} or
{"type": "error", "error"}. Clients read the response body incrementally.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from collections.abc import Iterator
from typing import Any

from openai import OpenAIError
from pydantic import ValidationError

from combustion_atlas.providers.retry import describe

LOG = logging.getLogger("combustion_atlas.app")


def answer_unavailable(exc: Exception, refunded: bool = False) -> str:
    LOG.warning("AI answer unavailable: %s", describe(exc))
    detail = str(exc) if isinstance(exc, ValueError) else "the OpenAI request failed after retries"
    note = " It did not count toward today's AI answer limit." if refunded else ""
    return f"AI answer unavailable ({detail[:200]}). Showing search results instead.{note}"


def semantic_unavailable(exc: Exception) -> str:
    LOG.warning("Semantic search unavailable: %s", describe(exc))
    detail = str(exc) if isinstance(exc, ValueError) else "the OpenAI request failed after retries"
    return f"Semantic search unavailable ({detail[:200]}); used keyword search."


def charged_call(request: Any, limiter: Any, exempt: bool, limited: Any) -> bool:
    """Whether apply_paid_limit took one of the site's paid calls for this request."""
    paid = bool(request.generate_answer or request.method != "keyword")
    return paid and limiter is not None and not exempt and not limited


def ask_events(
    workspace: Any, raw: bytes, *, limiter: Any = None, exempt: bool = False
) -> Iterator[str]:
    """Run /api/ask in a worker thread and yield NDJSON lines as progress happens.

    The pipeline is synchronous (retrieval, provider calls); a queue hands each event
    to this generator, which the web framework streams to the client line by line.
    """
    events: queue.Queue[dict[str, Any] | None] = queue.Queue()
    started = time.monotonic()

    def progress(stage: str, message: str) -> None:
        events.put(
            {
                "type": "progress",
                "stage": stage,
                "message": message,
                "elapsed_s": round(time.monotonic() - started, 2),
            }
        )

    def work() -> None:
        try:
            events.put({"type": "result", **_answer(workspace, raw, limiter, exempt, progress)})
        except (ValueError, ValidationError) as exc:
            events.put({"type": "error", "error": str(exc)[:500]})
        except OpenAIError as exc:
            LOG.warning("Ask stream failed: %s", describe(exc))
            events.put(
                {"type": "error", "error": "OpenAI request failed. Check configuration and retry."}
            )
        except Exception:  # noqa: BLE001 - always end the stream with an error event
            LOG.exception("Ask stream failed")
            events.put({"type": "error", "error": "The request could not be completed."})
        finally:
            events.put(None)

    threading.Thread(target=work, name="ask-stream", daemon=True).start()
    while (event := events.get()) is not None:
        yield json.dumps(event, ensure_ascii=False) + "\n"


def _answer(
    workspace: Any, raw: bytes, limiter: Any, exempt: bool, progress: Any
) -> dict[str, Any]:
    from combustion_atlas.providers import ProviderConfig
    from combustion_atlas.providers.openai_answers import OpenAIAnswerProvider
    from combustion_atlas.rag.search import retrieve_conversation
    from combustion_atlas.rag.store import DocumentStore

    from .core import EvidenceRequest, apply_paid_limit, broad_queries

    request = EvidenceRequest.model_validate_json(raw)
    if not workspace.database.is_file():
        raise ValueError("Build the document index to search evidence")
    if (request.method != "keyword" or request.generate_answer) and not (
        request.allow_provider_calls
    ):
        raise ValueError("Enable OpenAI calls for semantic search or generated answers")
    original = request
    request, limited = apply_paid_limit(request, limiter, exempt)
    charged = charged_call(original, limiter, exempt, limited)
    if limited:
        progress("limited", str(limited["reason"]))
    progress("started", f"Searching the corpus ({request.method} retrieval)")
    fallback = None
    with DocumentStore(workspace.read_database) as store:
        try:
            results = retrieve_conversation(
                store,
                request.question,
                [turn.question for turn in request.history],
                extra_queries=broad_queries(request),
                method=request.method,
                investigation=request.investigation or None,
                visible_sources=frozenset(request.include_sources),
                progress=progress,
            )
        except (ValueError, OpenAIError) as exc:
            if request.method == "keyword":
                raise
            # Semantic search unavailable: keep going with keyword search.
            fallback = semantic_unavailable(exc)
            progress("fallback", fallback)
            results = retrieve_conversation(
                store,
                request.question,
                [turn.question for turn in request.history],
                method="keyword",
                investigation=request.investigation or None,
                visible_sources=frozenset(request.include_sources),
                progress=progress,
            )
    payload: dict[str, Any] = {
        "question": request.question,
        "method": "keyword" if fallback else request.method,
        "results": results,
    }
    if fallback:
        payload["retrieval_fallback"] = fallback
    if limited:
        payload["limited"] = limited
    if request.generate_answer:
        try:
            provider = OpenAIAnswerProvider(ProviderConfig.from_environment())
            payload["answer"] = provider.answer(
                request.question,
                results,
                progress=progress,
                history=[turn.model_dump() for turn in request.history],
            ).model_dump()
            payload["answered_by"] = provider.answered_by()
        except (ValueError, OpenAIError) as exc:
            # Never discard what was found: report the answer failure with the results,
            # and give back the daily answer when the provider failed.
            refund = charged and isinstance(exc, OpenAIError)
            if refund:
                limiter.refund()
            payload["answer_unavailable"] = answer_unavailable(exc, refunded=refund)
            progress("answer", payload["answer_unavailable"])
    elif charged and fallback:
        limiter.refund()  # semantic search failed and no answer was requested
    progress("done", "Done")
    return payload
