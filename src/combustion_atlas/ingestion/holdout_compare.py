"""Build a local manual comparison packet for a complete holdout run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reference_bytes = args.reference.read_bytes()
    digest = hashlib.sha256(reference_bytes).hexdigest()
    references = json.loads(reference_bytes)["records"]
    refs = {(r["investigation_id"], r["test_id"]): r for r in references}
    if len(refs) != 4:
        raise ValueError("Expected four unique references")
    items = []
    seen = set()
    for path in sorted(args.results.glob("[0-9][0-9].json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        record = result["record"]
        key = (record["investigation_id"], record["test_id"])
        if key in seen or key not in refs:
            raise ValueError("Duplicate or unexpected holdout result")
        ref = refs[key]
        if (result.get("run_metadata", {}).get("reference_sha256") != digest or
                record["source_sha256"] != ref["source_sha256"] or
                record["record_number"] != ref["record_number"]):
            raise ValueError("Holdout result and reviewed reference do not match")
        seen.add(key)
        items.append({"result_file": path.name, "proposal": result["proposal"],
                      "validation_issues": result["validation_issues"],
                      "source_issues": result["source_issues"],
                      "review_reference": ref})
    if seen != set(refs):
        raise ValueError("Holdout result set is incomplete")
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump({"schema_version": "holdout-comparison-v1", "reference_sha256": digest,
                   "note": "Manual comparison; open research remains unresolved.",
                   "records": items}, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
