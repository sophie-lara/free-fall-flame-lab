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
    parser.add_argument(
        "--ui",
        choices=["workspace", "public"],
        default=env.get("COMBUSTION_ATLAS_UI", "workspace"),
        help="workspace = internal review UI at /; public = public UI at / (workspace at "
        "/workspace for administrators)",
    )
    parser.add_argument(
        "--admin",
        action="append",
        default=[a.strip() for a in env.get("COMBUSTION_ATLAS_ADMINS", "").split(",") if a.strip()],
        help="Sign-in name (email) allowed to administer a hosted deployment (repeatable)",
    )
    parser.add_argument(
        "--allowed-user",
        action="append",
        default=[
            u.strip() for u in env.get("COMBUSTION_ATLAS_ALLOWED_USERS", "").split(",") if u.strip()
        ],
        help="Hosted only: sign-in names allowed to use the app (repeatable); admins are "
        "always allowed. Unset means any signed-in user.",
    )
    parser.add_argument(
        "--paid-daily-limit",
        type=int,
        default=int(env.get("COMBUSTION_ATLAS_PAID_DAILY_LIMIT", "0")),
        help="Site-wide AI answers per UTC day for non-admins (0 = unlimited)",
    )
    parser.add_argument(
        "--paid-min-interval",
        type=int,
        default=int(env.get("COMBUSTION_ATLAS_PAID_MIN_INTERVAL_S", "0")),
        help="Minimum seconds between site-wide AI answers for non-admins (0 = none)",
    )
    args = parser.parse_args(argv)
    serve(
        workspace=args.workspace,
        port=args.port,
        host=args.host,
        allowed_hosts=frozenset(args.allowed_host),
        ui_mode=args.ui,
        admins=frozenset(args.admin),
        allowed_users=frozenset(args.allowed_user),
        paid_daily_limit=args.paid_daily_limit,
        paid_min_interval_s=args.paid_min_interval,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
