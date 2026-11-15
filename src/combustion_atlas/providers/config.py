"""Independent provider configuration with remote calls disabled by default."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass

from dotenv import load_dotenv


def _optional_positive_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    value = int(raw)
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class ProviderConfig:
    embedding_provider: str
    answer_provider: str
    embedding_model: str
    embedding_dimensions: int | None
    embedding_batch_size: int
    answer_model: str
    openai_api_key_present: bool
    # Optional backup answer model on another OpenAI-compatible endpoint (e.g. Azure
    # OpenAI v1), used only when the primary provider is unavailable after retries.
    fallback_model: str = ""
    fallback_base_url: str = ""
    fallback_api_key_present: bool = False
    fallback_reasoning_effort: str = "low"

    @property
    def fallback_enabled(self) -> bool:
        return bool(
            self.fallback_model and self.fallback_base_url and self.fallback_api_key_present
        )

    @classmethod
    def from_environment(cls) -> ProviderConfig:
        load_dotenv(override=False)
        api_key_present = bool(os.getenv("OPENAI_API_KEY", "").strip())
        embedding_provider = os.getenv(
            "COMBUSTION_ATLAS_EMBEDDING_PROVIDER", "openai" if api_key_present else ""
        ).strip()
        embedding_model = os.getenv("COMBUSTION_ATLAS_EMBEDDING_MODEL", "").strip()
        if embedding_provider == "openai" and not embedding_model:
            embedding_model = "text-embedding-3-small"
        return cls(
            embedding_provider=embedding_provider,
            answer_provider=os.getenv("COMBUSTION_ATLAS_ANSWER_PROVIDER", "").strip() or "disabled",
            embedding_model=embedding_model,
            embedding_dimensions=_optional_positive_int("COMBUSTION_ATLAS_EMBEDDING_DIMENSIONS"),
            embedding_batch_size=_optional_positive_int("COMBUSTION_ATLAS_EMBEDDING_BATCH_SIZE")
            or 64,
            answer_model=os.getenv("COMBUSTION_ATLAS_ANSWER_MODEL", "").strip(),
            openai_api_key_present=api_key_present,
            fallback_model=os.getenv("COMBUSTION_ATLAS_FALLBACK_MODEL", "").strip(),
            fallback_base_url=os.getenv("COMBUSTION_ATLAS_FALLBACK_BASE_URL", "").strip(),
            fallback_api_key_present=bool(
                os.getenv("COMBUSTION_ATLAS_FALLBACK_API_KEY", "").strip()
            ),
            fallback_reasoning_effort=os.getenv(
                "COMBUSTION_ATLAS_FALLBACK_REASONING_EFFORT", "low"
            ).strip(),
        )

    def public_status(self) -> dict[str, object]:
        status = asdict(self)
        status.pop("fallback_base_url")  # endpoint details stay server-side
        return status
