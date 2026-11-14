"""Build and query the page-preserving lexical document index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from combustion_atlas.io import write_json
from combustion_atlas.providers import OpenAIEmbeddingProvider, ProviderConfig
from combustion_atlas.retrieval import reciprocal_rank_fusion

from .build import build_index
from .store import DocumentStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Document RAG index")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("pdfs", nargs="+", type=Path)
    build.add_argument("--investigation")
    build.add_argument("--source-url")
    build.add_argument("--processed-dir", type=Path, default=Path("data/processed/rag"))
    build.add_argument("--database", type=Path, default=Path("data/embeddings/rag.sqlite3"))
    query = commands.add_parser("query")
    query.add_argument("question")
    query.add_argument("--investigation")
    query.add_argument("--top-k", type=int, default=5)
    query.add_argument("--method", choices=["keyword", "dense", "hybrid"], default="keyword")
    query.add_argument("--database", type=Path, default=Path("data/embeddings/rag.sqlite3"))
    query.add_argument("--output", type=Path)
    query.add_argument("--allow-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "build":
        report = build_index(
            args.pdfs,
            investigation_id=args.investigation,
            source_url=args.source_url,
            processed_dir=args.processed_dir,
            database=args.database,
        )
        print(json.dumps(report, indent=2))
        return 0
    with DocumentStore(args.database) as store:
        if args.method == "keyword":
            results = store.search(args.question, args.investigation, args.top_k)
        else:
            if not args.allow_provider_calls:
                parser.error(f"{args.method} query requires --allow-provider-calls")
            provider = OpenAIEmbeddingProvider(ProviderConfig.from_environment())
            query_vector = provider.embed([args.question])[0]
            dense = store.dense_search(
                query_vector,
                model_key=provider.model_key,
                investigation_id=args.investigation,
                top_k=max(args.top_k * 3, 10),
            )
            if args.method == "dense":
                results = dense[: args.top_k]
            else:
                keyword = store.search(args.question, args.investigation, max(args.top_k * 3, 10))
                fused = reciprocal_rank_fusion(
                    [
                        [str(item["chunk_id"]) for item in keyword],
                        [str(item["chunk_id"]) for item in dense],
                    ]
                )
                by_id = {str(item["chunk_id"]): item for item in [*keyword, *dense]}
                results = []
                for chunk_id, score in fused[: args.top_k]:
                    item = dict(by_id[chunk_id])
                    item["score"] = score
                    results.append(item)
    payload = {"question": args.question, "method": args.method, "results": results}
    if args.output:
        write_json(args.output, payload)
        print(f"Wrote {args.output}")
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
