"""Launch the local browser interface."""

from __future__ import annotations

import argparse
from pathlib import Path

from .server import serve


def main() -> int:
    parser = argparse.ArgumentParser(description="Combustion Atlas local interface")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(workspace=args.workspace, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
