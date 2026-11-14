"""Launch the browser interface (loopback by default; see docs/deploy_azure.md)."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .server import serve


def main(argv: list[str] | None = None) -> int:
    env = os.environ
    parser = argparse.ArgumentParser(description="Combustion Atlas interface")
    parser.add_argument(
        "--workspace", type=Path, default=Path(env.get("COMBUSTION_ATLAS_WORKSPACE", Path.cwd()))
    )
    parser.add_argument(
        "--host",
        default=env.get("COMBUSTION_ATLAS_HOST", "127.0.0.1"),
        help="Listen address; use 0.0.0.0 only behind an authenticating front end",
    )
    parser.add_argument("--port", type=int, default=int(env.get("PORT", "8765")))
    parser.add_argument(
        "--allowed-host",
        action="append",
        default=[
            h.strip() for h in env.get("COMBUSTION_ATLAS_ALLOWED_HOSTS", "").split(",") if h.strip()
        ],
        help="Public host name to accept (repeatable), e.g. atlas.azurewebsites.net",
    )
    args = parser.parse_args(argv)
    serve(
        workspace=args.workspace,
        port=args.port,
        host=args.host,
        allowed_hosts=frozenset(args.allowed_host),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
