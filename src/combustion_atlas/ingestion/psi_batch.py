"""Plan and capture selected public files from PSI investigations.

Uses the same public endpoints as the PSI website: investigation metadata, then a
per-file time-limited download link. Plans by default; `--download` captures files
with size limits, SHA-256 and an append-only manifest. Existing identical files are
skipped. Raw-data and analyzed-data PDFs (mostly video contact sheets) are excluded.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .psi_client import download_file

API = "https://psi.nasa.gov/geode-py/ws"
PAGE = "https://psi.nasa.gov/physci/repo/data/investigations/{}"
TEXT_CATEGORIES = {
    "Reports",
    "Science Documents",
    "Presentations",
    "Engineering Documents",
    "Reference Data",
}
FIRST_BATCH = [
    "PSI-26",  # BASS
    "PSI-25",  # BASS-II
    "PSI-69",  # FLEX
    "PSI-68",  # FLEX-2
    "PSI-98",  # SAFFIRE-I
    "PSI-99",  # SAFFIRE-II
    "PSI-100",  # SAFFIRE-III
    "PSI-102",  # SAME
    "PSI-101",  # SAME-R
]
USER_AGENT = "combustion-atlas/0.1 (research prototype)"


def _get(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return bytes(response.read())


def investigation(accession: str, fetch: Callable[[str], bytes] = _get) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(fetch(f"{API}/repo/investigations/{accession}"))
    return payload


def category(file: dict[str, Any]) -> str:
    parts = str(file.get("remote_path", "")).split("/")
    return parts[4] if len(parts) > 5 else "Unknown"


def select_files(accession: str, meta: dict[str, Any]) -> list[dict[str, Any]]:
    """Experiment tables plus text-bearing PDFs; public, visible files only."""
    chosen = []
    for file in meta.get("experimentalTable", []):
        chosen.append({**file, "role": "experimental_table", "category": "Experimental table"})
    for file in meta.get("added", []):
        name = str(file.get("file_name", ""))
        if name.lower().endswith(".pdf") and category(file) in TEXT_CATEGORIES:
            chosen.append({**file, "role": "document", "category": category(file)})
    return [
        {
            "accession": accession,
            "acronym": meta.get("investigationAcronym"),
            "title": meta.get("title"),
            "file_name": f["file_name"],
            "version": f.get("version"),
            "size_bytes": int(float(f.get("file_size") or 0)),
            "role": f["role"],
            "category": f["category"],
            "source_url": PAGE.format(accession),
        }
        for f in chosen
        if not f.get("restricted") and f.get("visible", True)
    ]


def download_link(item: dict[str, Any], fetch: Callable[[str], bytes] = _get) -> str:
    query = {"file": item["file_name"], "redirect": "false"}
    if item.get("version"):
        query["version"] = str(item["version"])
    url = f"{API}/studies/{item['accession']}/download?{urllib.parse.urlencode(query)}"
    link = fetch(url).decode("utf-8").strip().strip('"')
    if not link.startswith("https://"):
        raise ValueError(f"No download link for {item['file_name']}: {link[:120]}")
    return link


def local_path(root: Path, item: dict[str, Any]) -> Path:
    safe = Path(item["file_name"]).name
    return root / str(item["accession"]) / str(item["category"]).replace(" ", "_") / safe


def capture(
    items: list[dict[str, Any]],
    root: Path,
    *,
    max_bytes: int,
    fetch: Callable[[str], bytes] = _get,
    download: Callable[..., dict[str, object]] = download_file,
    pause: float = 0.5,
) -> list[dict[str, Any]]:
    manifest = root / "manifest.jsonl"
    results = []
    for item in items:
        target = local_path(root, item)
        if target.exists() and target.stat().st_size == item["size_bytes"]:
            results.append({**item, "status": "already_captured", "local_path": str(target)})
            continue
        if item["size_bytes"] > max_bytes:
            results.append({**item, "status": "skipped_too_large"})
            continue
        try:
            record = download(download_link(item, fetch), target, max_bytes=max_bytes)
        except Exception as exc:  # keep going; failures are reported, never hidden
            results.append(
                {**item, "status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300]}
            )
            continue
        entry = {
            **item,
            **record,
            "status": "captured",
            # The signed link expires and carries temporary credentials; never store it.
            "source_url": item["source_url"],
            "local_path": str(target),
        }
        with manifest.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
        results.append(entry)
        time.sleep(pause)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accessions", nargs="*", default=FIRST_BATCH)
    parser.add_argument("--root", type=Path, default=Path("data/raw/psi"))
    parser.add_argument("--max-file-mb", type=int, default=80)
    parser.add_argument("--download", action="store_true", help="Capture files (default: plan)")
    args = parser.parse_args(argv)
    plan = []
    for accession in args.accessions:
        plan.extend(select_files(accession, investigation(accession)))
        time.sleep(0.3)
    summary: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "files": len(plan),
        "bytes": sum(i["size_bytes"] for i in plan),
        "by_investigation": {},
    }
    for item in plan:
        group = summary["by_investigation"].setdefault(
            f"{item['accession']} {item['acronym'] or ''}".strip(), {"tables": 0, "pdfs": 0}
        )
        group["tables" if item["role"] == "experimental_table" else "pdfs"] += 1
    if args.download:
        results = capture(plan, args.root, max_bytes=args.max_file_mb * 1024 * 1024)
        summary["results"] = {
            status: sum(r["status"] == status for r in results)
            for status in sorted({r["status"] for r in results})
        }
        summary["failures"] = [
            {"file": r["file_name"], "error": r.get("error")}
            for r in results
            if r["status"] == "failed"
        ]
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
