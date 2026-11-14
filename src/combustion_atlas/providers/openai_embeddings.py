"""OpenAI embeddings provider with bounded batches and explicit model identity."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from openai import OpenAI

from .config import ProviderConfig


class OpenAIEmbeddingProvider:
    def __init__(self, config: ProviderConfig, *, client: Any | None = None):
        if config.embedding_provider != "openai":
            raise ValueError("OpenAIEmbeddingProvider requires embedding_provider=openai")
        if not config.embedding_model:
            raise ValueError("An OpenAI embedding model is required")
        if client is None and not config.openai_api_key_present:
            raise ValueError("OPENAI_API_KEY is missing")
        self.model = config.embedding_model
        self.dimensions = config.embedding_dimensions or self._default_dimensions(self.model)
        self.batch_size = config.embedding_batch_size
        self.model_key = f"openai:{self.model}:{self.dimensions}"
        self._client = client or OpenAI()

    @staticmethod
    def _default_dimensions(model: str) -> int:
        if model == "text-embedding-3-small":
            return 1536
        if model == "text-embedding-3-large":
            return 3072
        raise ValueError("Set COMBUSTION_ATLAS_EMBEDDING_DIMENSIONS for this model")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if any(not text.strip() for text in texts):
            raise ValueError("Embedding inputs cannot be empty")
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start : start + self.batch_size])
            response = self._client.embeddings.create(
                model=self.model,
                input=batch,
                encoding_format="float",
                dimensions=self.dimensions,
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            if len(ordered) != len(batch):
                raise RuntimeError("OpenAI returned an unexpected number of embeddings")
            for item in ordered:
                vector = [float(value) for value in item.embedding]
                if len(vector) != self.dimensions:
                    raise RuntimeError("OpenAI returned an unexpected embedding dimension")
                vectors.append(vector)
        return vectors
