"""Inspect explicit embedding and answer-provider configuration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from openai import OpenAIError

from combustion_atlas.rag.store import DocumentStore

from .config import ProviderConfig
from .openai_embeddings import OpenAIEmbeddingProvider


def embed_missing(database: Path, config: ProviderConfig, *, execute: bool) -> int:
    """Plan (default) or embed chunks lacking vectors in the configured namespace."""
    model = config.embedding_model or "text-embedding-3-small"
    dimensions = config.embedding_dimensions or OpenAIEmbeddingProvider._default_dimensions(model)
    model_key = f"openai:{model}:{dimensions}"
    with DocumentStore(database) as store:
        chunks = store.chunks_missing_vectors(model_key)
        plan = {"model_key": model_key, "missing_chunks": len(chunks), "dry_run": not execute}
        if execute and chunks:
            provider = OpenAIEmbeddingProvider(config)
            vectors = provider.embed([chunk.text for chunk in chunks])
            store.append_vectors(
                model_key=provider.model_key,
                model=provider.model,
                dimensions=provider.dimensions,
                vectors={c.chunk_id: v for c, v in zip(chunks, vectors, strict=True)},
            )
            plan["embedded_chunks"] = len(chunks)
    print(json.dumps(plan, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provider configuration")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    embed = commands.add_parser("embed", help="Embed every document chunk")
    embed.add_argument("--database", type=Path, default=Path("data/embeddings/rag.sqlite3"))
    embed.add_argument("--allow-provider-calls", action="store_true")
    embed.add_argument(
        "--missing-only",
        action="store_true",
        help="Embed only chunks without a vector; existing vectors are kept",
    )
    args = parser.parse_args(argv)
    config = ProviderConfig.from_environment()
    if args.command == "status":
        print(json.dumps(config.public_status(), indent=2))
        return 0
    if args.missing_only:
        return embed_missing(args.database, config, execute=args.allow_provider_calls)
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
