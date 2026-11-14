"""Provider protocols keep embedding and answer configuration independent."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class EmbeddingProvider(Protocol):
    model_key: str
    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class AnswerProvider(Protocol):
    def answer(
        self, question: str, cited_context: Sequence[dict[str, str]]
    ) -> dict[str, object]: ...
