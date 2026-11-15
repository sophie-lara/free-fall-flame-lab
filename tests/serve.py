"""Run the FastAPI app on a real Uvicorn server in a thread, for HTTP-level tests."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import uvicorn

from combustion_atlas.app.api import Settings, create_app

# A stand-in for the built React app, so Python tests do not need a Node build.
FIXTURE_WEB = Path(__file__).parent / "fixtures/web"


class RunningServer:
    def __init__(self, server: uvicorn.Server, thread: threading.Thread, app: Any) -> None:
        self._server = server
        self._thread = thread
        self.app = app

    @property
    def server_port(self) -> int:
        return int(self._server.servers[0].sockets[0].getsockname()[1])

    def shutdown(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=10)

    def server_close(self) -> None:  # kept for symmetry with the old tests
        return None


SETTING_NAMES = {
    "workspace",
    "allowed_hosts",
    "admins",
    "allowed_users",
    "public_uploads",
    "upload_code",
    "uploads_per_day",
    "web_dir",
    "cache_dir",
}


def start(**attrs: Any) -> RunningServer:
    """Start the app with Settings fields; `limiter` replaces the paid-call limiter."""
    limiter = attrs.pop("limiter", None)
    unknown = set(attrs) - SETTING_NAMES
    if unknown:
        raise TypeError(f"Unknown settings: {sorted(unknown)}")
    attrs["workspace"] = Path(attrs["workspace"])
    attrs.setdefault("web_dir", FIXTURE_WEB)
    for name in ("admins", "allowed_users"):
        if name in attrs:
            attrs[name] = frozenset(str(a).casefold() for a in attrs[name])
    app = create_app(Settings(**attrs))
    if limiter is not None:
        app.state.service.limiter = limiter
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Test server did not start")
        time.sleep(0.01)
    return RunningServer(server, thread, app)
