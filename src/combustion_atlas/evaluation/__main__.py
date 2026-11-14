"""Evaluate reviewed lexical retrieval questions."""

from __future__ import annotations

import argparse
from pathlib import Path

from combustion_atlas.io import read_json, write_json
from combustion_atlas.rag.store import DocumentStore

from .lexical import score_questions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate reviewed lexical questions")
    parser.add_argument("questions", type=Path)
    parser.add_argument("--database", type=Path, default=Path("data/embeddings/rag.sqlite3"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = read_json(args.questions)
    with DocumentStore(args.database) as store:
        result = score_questions(payload["questions"], store.search)
    write_json(args.output, result)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
