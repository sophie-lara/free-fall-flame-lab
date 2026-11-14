"""Build a local review packet for held-out proposals and reviewed evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    references = json.loads(args.evidence.read_text(encoding="utf-8"))["records"]
    packet = []
    for path in sorted(args.results.glob("[0-9][0-9].json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        identity = result["record"]
        if identity["split"] != "holdout":
            continue
        matches = [
            r
            for r in references
            if r["investigation_id"] == identity["investigation_id"]
            and r["test_id"] == identity["test_id"]
            and r["source_sha256"] == identity["source_sha256"]
        ]
        if len(matches) != 1:
            raise ValueError("Held-out reference is missing or source does not match")
        reference = matches[0]
        packet.append(
            {
                "result_file": path.name,
                "proposal": result["proposal"],
                "issues": result["issues"],
                "review_action": reference["review_action"],
                "reviewed_candidate": reference["reviewed_candidate"],
                "unresolved_questions": reference["unresolved_questions"],
                "review_history": reference["review_history"],
            }
        )
    if len(packet) != 3:
        raise ValueError("Expected three held-out results; pilot may be incomplete")
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "note": "Manual comparison; unresolved questions remain unresolved.",
                "holdouts": packet,
            },
            stream,
            ensure_ascii=False,
            indent=2,
        )
        stream.write("\n")


if __name__ == "____main__":
    main()
