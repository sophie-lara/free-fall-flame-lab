"""Prepare review templates and apply completed decisions."""

from __future__ import annotations

import argparse
from pathlib import Path

from .workflow import apply_decisions, prepare_decisions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review and adjudication workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--candidates", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    apply = subparsers.add_parser("apply")
    apply.add_argument("--candidates", type=Path, required=True)
    apply.add_argument("--decisions", type=Path, required=True)
    apply.add_argument("--output", type=Path, required=True)
    apply.add_argument("--gold-dir", type=Path)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare_decisions(args.candidates, args.output)
    else:
        apply_decisions(args.candidates, args.decisions, args.output, args.gold_dir)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
