"""Bounded PSI source capture with a stable local manifest."""

from __future__ import annotations

import argparse
import hashlib
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from combustion_atlas.io import write_json


def download_file(url: str, output: Path, *, max_bytes: int) -> dict[str, object]:
    """Download one explicitly selected public file with a hard size limit."""
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing capture: {output}")
    request = urllib.request.Request(url, headers={"User-Agent": "combustion-atlas/0.1"})
    digest = hashlib.sha256()
    total = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.part")
    temporary.unlink(missing_ok=True)
    try:
        with (
            urllib.request.urlopen(request, timeout=60) as response,
            temporary.open("wb") as stream,
        ):
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > max_bytes:
                    raise ValueError(f"Download exceeds {max_bytes} bytes")
                digest.update(block)
                stream.write(block)
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "source_url": url,
        "local_path": str(output),
        "sha256": digest.hexdigest(),
        "size_bytes": total,
        "captured_at": datetime.now(UTC).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture an explicitly selected PSI file")
    parser.add_argument("url", help="Stable public file URL")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path("data/raw/psi-capture.json"))
    parser.add_argument("--max-file-mb", type=int, default=60)
    args = parser.parse_args(argv)
    manifest = download_file(args.url, args.output, max_bytes=args.max_file_mb * 1024 * 1024)
    write_json(args.manifest, manifest)
    print(f"Captured {args.output} ({manifest['sha256']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
