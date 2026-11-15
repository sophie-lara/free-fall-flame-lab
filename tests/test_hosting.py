"""Hosted mode keeps loopback protections and only adds explicitly named hosts."""

import http.client
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
import serve

from combustion_atlas.app.__main__ import main

PUBLIC = "atlas.example.net"


@pytest.fixture
def hosted(tmp_path: Path) -> Iterator[serve.RunningServer]:
    server = serve.start(**{"workspace": tmp_path, "allowed_hosts": frozenset({PUBLIC})})
    yield server
    server.shutdown()
    server.server_close()


def call(server: serve.RunningServer, method: str, path: str, headers: dict[str, str]) -> int:
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
    body = json.dumps({"question": "x"}) if method == "POST" else None
    conn.request(method, path, body=body, headers={"Content-Type": "application/json", **headers})
    status = conn.getresponse().status
    conn.close()
    return status


def test_named_public_host_is_accepted_and_others_rejected(hosted: serve.RunningServer) -> None:
    assert call(hosted, "GET", "/api/health", {"Host": PUBLIC}) == 200
    assert call(hosted, "GET", "/api/health", {"Host": "evil.example"}) == 403


def test_https_origin_only_for_named_hosts(hosted: serve.RunningServer) -> None:
    local = f"127.0.0.1:{hosted.server_port}"
    ok = {"Host": PUBLIC, "Origin": f"https://{PUBLIC}"}
    assert call(hosted, "POST", "/api/ask", ok) != 403
    assert (
        call(hosted, "POST", "/api/ask", {"Host": PUBLIC, "Origin": "https://evil.example"}) == 403
    )
    assert call(hosted, "POST", "/api/ask", {"Host": local, "Origin": f"https://{local}"}) == 403


def test_public_listen_requires_named_hosts(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="allowed host"):
        main(["--workspace", str(tmp_path), "--host", "0.0.0.0", "--port", "8000"])
