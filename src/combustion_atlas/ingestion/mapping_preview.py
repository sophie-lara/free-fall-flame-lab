"""Create source-only request previews from the saved regression examples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .llm_handoff import SourceBatch
from .mapping_contract import Profile, mapping_request

REGRESSION: dict[str, Profile] = {
    "B1": "bass_ii",
    "FLEX-T13-Ar": "flex_table_13",
    "SAFFIRE-II-2-2": "saffire_ii",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    previews = []
    seen: set[str] = set()
    for path in sorted(args.results.glob("[0-9][0-9].json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        test_id = result["record"]["test_id"]
        if test_id not in REGRESSION:
            continue
        if test_id in seen:
            raise ValueError("Duplicate regression identity")
        seen.add(test_id)
        source = SourceBatch.model_validate(result["source"])
        previews.append(
            {
                "test_id": test_id,
                "source_result": path.name,
                "request": mapping_request(REGRESSION[test_id], source),
            }
        )
    if seen != set(REGRESSION):
        raise ValueError("Missing regression input")
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump({"provider_calls": 0, "requests": previews}, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
