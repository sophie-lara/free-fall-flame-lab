"""Inspect explicit embedding and answer-provider configuration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from openai import OpenAIError

from combustion_atlas.rag.store import DocumentStore

from .config import ProviderConfig
from .openai_embeddings import OpenAIEmbeddingProvider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provider configuration")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    embed = commands.add_parser("embed", help="Embed every document chunk")
    embed.add_argument("--database", type=Path, default=Path("data/embeddings/rag.sqlite3"))
    embed.add_argument("--allow-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    config = ProviderConfig.from_environment()
    if args.command == "status":
        print(json.dumps(config.public_status(), indent=2))
        return 0
    if not args.allow_provider_calls:
        parser.error("embed requires --allow-provider-calls")
    provider = OpenAIEmbeddingProvider(config)
    with DocumentStore(args.database) as store:
        chunks = store.list_chunks()
        if not chunks:
            raise ValueError("The document index has no chunks to embed")
        vectors = provider.embed([chunk.text for chunk in chunks])
        store.replace_vectors(
            model_key=provider.model_key,
            provider="openai",
            model=provider.model,
            dimensions=provider.dimensions,
            vectors={chunk.chunk_id: vector for chunk, vector in zip(chunks, vectors, strict=True)},
        )
    print(
        json.dumps(
            {
                "embedded_chunks": len(chunks),
                "model": provider.model,
                "dimensions": provider.dimensions,
                "model_key": provider.model_key,
                "database": str(args.database),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OpenAIError as exc:
        # Provider error messages may contain credential fragments. Never print them.
        raise SystemExit(
            f"OpenAI request failed ({type(exc).__name__}); check local credentials, "
            "network access and account limits."
        ) from None
