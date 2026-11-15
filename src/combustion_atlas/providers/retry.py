"""Retry transient OpenAI failures with exponential backoff and jitter.

Retries timeouts, connection errors, rate limits (429) and server errors (5xx, 408,
409); honors a Retry-After header. Never retries client errors such as 400/401/404.
Logs the exception type, HTTP status and request ID (never the message, which can
contain credential fragments).
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable

from openai import APIConnectionError, APIStatusError

LOG = logging.getLogger("combustion_atlas.openai")
RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


def describe(exc: BaseException) -> str:
    """Safe one-line description for logs: type, status and request ID only."""
    status = getattr(exc, "status_code", None)
    request_id = getattr(exc, "request_id", None)
    parts = [type(exc).__name__]
    if status is not None:
        parts.append(f"status={status}")
    if request_id:
        parts.append(f"request_id={request_id}")
    return " ".join(parts)


def _retry_after(exc: BaseException) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        return max(0.0, float(headers.get("retry-after", "")))
    except (TypeError, ValueError):
        return None


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, APIStatusError):  # includes RateLimitError and InternalServerError
        return exc.status_code in RETRYABLE_STATUS
    return isinstance(exc, APIConnectionError)  # includes APITimeoutError


def call_with_retries[T](
    fn: Callable[[], T],
    *,
    what: str,
    attempts: int = 4,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run fn, retrying transient OpenAI errors up to `attempts` times in total."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            if not is_retryable(exc) or attempt == attempts:
                LOG.warning(
                    "openai %s failed: %s (attempt %d/%d, giving up)",
                    what,
                    describe(exc),
                    attempt,
                    attempts,
                )
                raise
            delay = min(max_delay, base_delay * 2 ** (attempt - 1))
            delay = min(max_delay * 2, _retry_after(exc) or delay * random.uniform(0.75, 1.25))
            LOG.warning(
                "openai %s failed: %s (attempt %d/%d, retrying in %.1fs)",
                what,
                describe(exc),
                attempt,
                attempts,
                delay,
            )
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            sleep(delay)
    raise AssertionError("unreachable")
