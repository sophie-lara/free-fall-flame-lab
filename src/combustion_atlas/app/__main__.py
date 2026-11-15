"""Launch the web app with Uvicorn (loopback by default; see docs/deploy_azure.md)."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path


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
    parser.add_argument(
        "--public-uploads",
        action="store_true",
        default=env.get("COMBUSTION_ATLAS_PUBLIC_UPLOADS", "") in {"1", "true", "yes"},
        help="Public mode: let visitors upload PDFs into quarantine (admin approves)",
    )
    parser.add_argument(
        "--upload-code",
        default=env.get("COMBUSTION_ATLAS_UPLOAD_CODE", ""),
        help="Optional code visitors must enter to upload",
    )
    parser.add_argument(
        "--uploads-per-day",
        type=int,
        default=int(env.get("COMBUSTION_ATLAS_UPLOADS_PER_USER_DAY", "3")),
        help="Uploads per visitor per UTC day",
    )
    args = parser.parse_args(argv)
    # App Service streams stdout/stderr to Log stream; keep provider failures visible there.
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    if not 1 <= args.port <= 65535:
        raise SystemExit("Port must be between 1 and 65535")
    if args.host not in {"127.0.0.1", "localhost"} and not args.allowed_host:
        raise SystemExit("Listening beyond loopback requires at least one allowed host name")
    import uvicorn

    from .api import Settings, create_app

    # App Service keeps /home on a network share; a local snapshot makes reads fast.
    cache = env.get("COMBUSTION_ATLAS_CACHE_DIR") or (
        "/tmp/combustion-atlas" if env.get("WEBSITE_INSTANCE_ID") else ""
    )
    settings = Settings(
        workspace=args.workspace.resolve(),
        allowed_hosts=frozenset(args.allowed_host),
        admins=frozenset(a.casefold() for a in args.admin),
        allowed_users=frozenset(u.casefold() for u in args.allowed_user),
        paid_daily_limit=args.paid_daily_limit,
        paid_min_interval_s=args.paid_min_interval,
        public_uploads=args.public_uploads,
        upload_code=args.upload_code,
        uploads_per_day=args.uploads_per_day,
        cache_dir=Path(cache) if cache else None,
        warm_caches=True,
    )
    print(f"Combustion Atlas: http://{args.host}:{args.port}", flush=True)
    uvicorn.run(create_app(settings), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
