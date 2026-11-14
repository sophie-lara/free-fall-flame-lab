"""Hosted mode keeps loopback protections and only adds explicitly named hosts."""

import http.client
import json
import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from combustion_atlas.app.__main__ import main
from combustion_atlas.app.server import AtlasHandler, serve

PUBLIC = "atlas.example.net"


@pytest.fixture
def hosted(tmp_path: Path) -> Iterator[ThreadingHTTPServer]:
    handler = type(
        "Hosted", (AtlasHandler,), {"workspace": tmp_path, "allowed_hosts": frozenset({PUBLIC})}
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def call(server: ThreadingHTTPServer, method: str, path: str, headers: dict[str, str]) -> int:
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
    body = json.dumps({"question": "x"}) if method == "POST" else None
    conn.request(method, path, body=body, headers={"Content-Type": "application/json", **headers})
    status = conn.getresponse().status
    conn.close()
    return status


def test_named_public_host_is_accepted_and_others_rejected(hosted: ThreadingHTTPServer) -> None:
    assert call(hosted, "GET", "/api/health", {"Host": PUBLIC}) == 200
    assert call(hosted, "GET", "/api/health", {"Host": "evil.example"}) == 403


def test_https_origin_only_for_named_hosts(hosted: ThreadingHTTPServer) -> None:
    local = f"127.0.0.1:{hosted.server_port}"
    ok = {"Host": PUBLIC, "Origin": f"https://{PUBLIC}"}
    assert call(hosted, "POST", "/api/ask", ok) != 403
    assert (
        call(hosted, "POST", "/api/ask", {"Host": PUBLIC, "Origin": "https://evil.example"}) == 403
    )
    assert call(hosted, "POST", "/api/ask", {"Host": local, "Origin": f"https://{local}"}) == 403


def test_public_listen_requires_named_hosts(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="allowed host"):
        serve(workspace=tmp_path, port=8000, host="0.0.0.0")
    with pytest.raises(ValueError, match="allowed host"):
        main(["--workspace", str(tmp_path), "--host", "0.0.0.0", "--port", "8000"])
