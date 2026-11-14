"""Build and query the page-preserving lexical document index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from openai import OpenAIError

from combustion_atlas.io import write_json
from combustion_atlas.providers import ProviderConfig
from combustion_atlas.providers.openai_answers import OpenAIAnswerProvider

from .build import add_document, build_index
from .search import retrieve
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
    build.add_argument(
        "--replace-existing",
        action="store_true",
        help="Discard the populated index, vectors and visual artifacts",
    )
    add = commands.add_parser("add", help="Add one PDF without replacing the index")
    add.add_argument("pdf", type=Path)
    add.add_argument("--investigation", required=True)
    add.add_argument("--source-url", required=True)
    add.add_argument("--processed-dir", type=Path, default=Path("data/processed/rag"))
    add.add_argument("--database", type=Path, default=Path("data/embeddings/rag.sqlite3"))
    remove = commands.add_parser("remove", help="Remove one source and its vectors/visuals")
    remove.add_argument("source_id")
    remove.add_argument("--database", type=Path, default=Path("data/embeddings/rag.sqlite3"))
    query = commands.add_parser("query")
    query.add_argument("question")
    query.add_argument("--investigation")
    query.add_argument("--top-k", type=int, default=5)
    query.add_argument("--method", choices=["keyword", "dense", "hybrid"], default="keyword")
    query.add_argument("--database", type=Path, default=Path("data/embeddings/rag.sqlite3"))
    query.add_argument("--output", type=Path)
    query.add_argument("--allow-provider-calls", action="store_true")
    query.add_argument("--answer", action="store_true", help="Generate an excerpt-backed answer")
    args = parser.parse_args(argv)
    if args.command == "build":
        report = build_index(
            args.pdfs,
            investigation_id=args.investigation,
            source_url=args.source_url,
            processed_dir=args.processed_dir,
            database=args.database,
            replace_existing=args.replace_existing,
        )
        print(json.dumps(report, indent=2))
        return 0
    if args.command == "add":
        report = add_document(
            args.pdf,
            investigation_id=args.investigation,
            source_url=args.source_url,
            processed_dir=args.processed_dir,
            database=args.database,
        )
        print(json.dumps(report, indent=2))
        return 0
    if args.command == "remove":
        with DocumentStore(args.database) as store:
            print(json.dumps(store.remove_document(args.source_id), indent=2))
        return 0
    with DocumentStore(args.database) as store:
        if (args.method != "keyword" or args.answer) and not args.allow_provider_calls:
            parser.error("Semantic retrieval and answers require --allow-provider-calls")
        results = retrieve(
            store,
            args.question,
            method=args.method,
            investigation=args.investigation,
            top_k=args.top_k,
        )
    payload = {"question": args.question, "method": args.method, "results": results}
    if args.answer:
        provider = OpenAIAnswerProvider(ProviderConfig.from_environment())
        payload["answer"] = provider.answer(args.question, results).model_dump()
    if args.output:
        write_json(args.output, payload)
        print(f"Wrote {args.output}")
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OpenAIError as exc:
        raise SystemExit(
            f"OpenAI request failed ({type(exc).__name__}); "
            "check local configuration and account limits."
        ) from None
