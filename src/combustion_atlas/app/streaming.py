"""Stream evidence-answer progress as newline-delimited JSON (NDJSON).

Each line is one event: {"type": "progress", "stage", "message", "elapsed_s"},
then exactly one {"type": "result", ...same payload as /api/ask...} or
{"type": "error", "error"}. Clients read the response body incrementally.
"""

from __future__ import annotations

import json
import time
from typing import Any

from openai import OpenAIError
from pydantic import ValidationError


def stream_ask(
    handler: Any, workspace: Any, raw: bytes, *, limiter: Any = None, exempt: bool = False
) -> None:
    """Run /api/ask with live progress events written to the handler's socket."""
    from combustion_atlas.providers import ProviderConfig
    from combustion_atlas.providers.openai_answers import OpenAIAnswerProvider
    from combustion_atlas.rag.search import retrieve
    from combustion_atlas.rag.store import DocumentStore

    from .server import EvidenceRequest, apply_paid_limit

    started = time.monotonic()
    handler.send_response(200)
    handler.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("X-Accel-Buffering", "no")  # disable proxy buffering
    handler.send_header("Connection", "close")
    handler.end_headers()
    handler.close_connection = True

    def emit(event: dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False) + "\n"
        handler.wfile.write(line.encode("utf-8"))
        handler.wfile.flush()

    def progress(stage: str, message: str) -> None:
        emit(
            {
                "type": "progress",
                "stage": stage,
                "message": message,
                "elapsed_s": round(time.monotonic() - started, 2),
            }
        )

    try:
        request = EvidenceRequest.model_validate_json(raw)
        if not workspace.database.is_file():
            raise ValueError("Build the document index to search evidence")
        if (request.method != "keyword" or request.generate_answer) and not (
            request.allow_provider_calls
        ):
            raise ValueError("Enable OpenAI calls for semantic search or generated answers")
        request, limited = apply_paid_limit(request, limiter, exempt)
        if limited:
            progress("limited", str(limited["reason"]))
        progress("started", f"Searching the corpus ({request.method} retrieval)")
        with DocumentStore(workspace.database) as store:
            results = retrieve(
                store,
                request.question,
                method=request.method,
                investigation=request.investigation or None,
                progress=progress,
            )
        payload: dict[str, Any] = {
            "question": request.question,
            "method": request.method,
            "results": results,
        }
        if limited:
            payload["limited"] = limited
        if request.generate_answer:
            provider = OpenAIAnswerProvider(ProviderConfig.from_environment())
            payload["answer"] = provider.answer(
                request.question, results, progress=progress
            ).model_dump()
        progress("done", "Done")
        emit({"type": "result", **payload})
    except (ValueError, ValidationError) as exc:
        emit({"type": "error", "error": str(exc)[:500]})
    except OpenAIError:
        emit({"type": "error", "error": "OpenAI request failed. Check configuration and retry."})
    except (BrokenPipeError, ConnectionResetError):
        return  # the client went away; nothing left to report
