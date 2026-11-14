"""Evaluate retrieval methods and, optionally, generated answers.

Only reviewed questions are scored unless --include-unreviewed is given; such runs
are labelled as drafts. Development and held-out splits are evaluated separately.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from openai import OpenAIError

from combustion_atlas.io import read_json, write_json
from combustion_atlas.providers import ProviderConfig
from combustion_atlas.rag.search import retrieve
from combustion_atlas.rag.store import DocumentStore

from .retrieval import (
    EvalQuestion,
    Method,
    run_binding,
    score_answer,
    score_retrieval,
    summarize_answers,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions", type=Path)
    parser.add_argument("--database", type=Path, default=Path("data/embeddings/rag.sqlite3"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=["development", "heldout"], default="development")
    parser.add_argument(
        "--methods", nargs="+", choices=["keyword", "dense", "hybrid"], default=["keyword"]
    )
    parser.add_argument("--include-unreviewed", action="store_true")
    parser.add_argument("--answers", action="store_true", help="Also generate and score answers")
    parser.add_argument("--allow-provider-calls", action="store_true")
    args = parser.parse_args(argv)
    needs_provider = args.answers or any(m != "keyword" for m in args.methods)
    if needs_provider and not args.allow_provider_calls:
        parser.error("Dense/hybrid retrieval and answers require --allow-provider-calls")
    all_questions = [EvalQuestion.model_validate(q) for q in read_json(args.questions)["questions"]]
    if len({q.id for q in all_questions}) != len(all_questions):
        parser.error("Question IDs must be unique")
    questions = [
        q
        for q in all_questions
        if q.split == args.split and (q.reviewed or args.include_unreviewed)
    ]
    config = ProviderConfig.from_environment()
    with DocumentStore(args.database) as store:
        options = {
            "split": args.split,
            "methods": args.methods,
            "answers": args.answers,
            "include_unreviewed": args.include_unreviewed,
            "question_ids": [q.id for q in questions],
        }
        report: dict[str, Any] = {
            "status": "draft_unreviewed_questions"
            if any(not q.reviewed for q in questions)
            else "reviewed_questions",
            "binding": run_binding(
                root=Path.cwd(),
                questions_path=args.questions,
                store=store,
                config=config,
                options=options,
            ),
            "retrieval": {},
        }

        def searcher(method: Method) -> Any:
            return lambda text, investigation, k: retrieve(
                store, text, method=method, investigation=investigation, top_k=k
            )

        for method in cast(list[Method], args.methods):
            report["retrieval"][method] = score_retrieval(questions, searcher(method))
        if args.answers:
            from combustion_atlas.providers.openai_answers import OpenAIAnswerProvider

            provider = OpenAIAnswerProvider(config)
            items = []
            for question in questions:
                results = retrieve(
                    store, question.question, method="hybrid", investigation=question.investigation
                )
                try:
                    answer = provider.answer(question.question, results).model_dump()
                    items.append(score_answer(question, answer, results))
                except (ValueError, OpenAIError) as exc:
                    items.append({"id": question.id, "error": f"{type(exc).__name__}: {exc}"[:300]})
            report["answers"] = summarize_answers(items)
    write_json(args.output, report)
    summary = {
        method: {k: v for k, v in result.items() if k != "questions"}
        for method, result in report["retrieval"].items()
    }
    if "answers" in report:
        summary["answers"] = {k: v for k, v in report["answers"].items() if k != "questions"}
    print(json.dumps({"status": report["status"], "summary": summary}, indent=2))
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
