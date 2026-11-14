"""Capture public PDFs from the NASA Technical Reports Server (NTRS) by citation ID.

    python -m combustion_atlas.ingestion.ntrs 20160000593 20150019858 --download

Plans by default. Downloads go to data/raw/ntrs/<id>.pdf with an append-only
manifest (title, date, document type, citation URL, SHA-256).
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from .psi_client import download_file

API = "https://ntrs.nasa.gov/api/citations/{}"
CITATION = "https://ntrs.nasa.gov/citations/{}"
USER_AGENT = "combustion-atlas/0.1 (research prototype)"


def citation(identifier: str) -> dict[str, Any]:
    if not identifier.isdigit():
        raise ValueError(f"NTRS IDs are numeric: {identifier}")
    request = urllib.request.Request(API.format(identifier), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        record: dict[str, Any] = json.loads(response.read())
    pdfs = [
        d["links"]["pdf"] for d in record.get("downloads", []) if (d.get("links") or {}).get("pdf")
    ]
    return {
        "ntrs_id": identifier,
        "title": record.get("title"),
        "sti_type": record.get("stiType"),
        "date": ((record.get("publications") or [{}])[0].get("publicationDate") or "")[:10],
        "citation_url": CITATION.format(identifier),
        "pdf_url": f"https://ntrs.nasa.gov{pdfs[0]}" if pdfs else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="+")
    parser.add_argument("--root", type=Path, default=Path("data/raw/ntrs"))
    parser.add_argument("--max-file-mb", type=int, default=80)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args(argv)
    results = []
    for identifier in args.ids:
        item = citation(identifier)
        target = args.root / f"{identifier}.pdf"
        if not item["pdf_url"]:
            item["status"] = "no_pdf"
        elif target.exists():
            item["status"] = "already_captured"
        elif args.download:
            record = download_file(
                item["pdf_url"], target, max_bytes=args.max_file_mb * 1024 * 1024
            )
            item.update(
                sha256=record["sha256"],
                size_bytes=record["size_bytes"],
                captured_at=record["captured_at"],
                local_path=str(target),
                status="captured",
            )
            with (args.root / "manifest.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(item, ensure_ascii=False) + "\n")
        else:
            item["status"] = "planned"
        results.append(item)
        time.sleep(0.3)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
