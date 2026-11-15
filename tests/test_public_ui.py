"""Public UI mode, administrator gating, /api/me and analysis fallbacks."""

import http.client
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import serve

PUBLIC = "atlas.example.net"
ADMIN = "Sophie@Example.org"


def start(
    tmp_path: Path, *, hosted: bool, admins: frozenset[str] = frozenset()
) -> serve.RunningServer:
    attrs = {
        "workspace": tmp_path,
        "allowed_hosts": frozenset({PUBLIC}) if hosted else frozenset(),
        "admins": frozenset(a.casefold() for a in admins),
    }
    return serve.start(**attrs)


@pytest.fixture
def servers(tmp_path: Path) -> Iterator[dict[str, serve.RunningServer]]:
    made = {
        "hosted": start(tmp_path, hosted=True, admins=frozenset({ADMIN})),
        "local": start(tmp_path, hosted=False),
    }
    yield made
    for server in made.values():
        server.shutdown()
        server.server_close()


def call(
    server: serve.RunningServer,
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    hosted: bool = False,
) -> tuple[int, Any, str]:
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
    base = {"Host": PUBLIC if hosted else f"127.0.0.1:{server.server_port}"}
    conn.request(method, path, body=body, headers={**base, **(headers or {})})
    response = conn.getresponse()
    raw = response.read()
    kind = response.getheader("Content-Type", "")
    conn.close()
    return response.status, json.loads(raw) if kind.startswith("application/json") else raw, kind


def test_public_ui_is_served_at_the_root_everywhere(servers) -> None:
    hosted = servers["hosted"]
    status, body, kind = call(hosted, "/", hosted=True)
    assert status == 200 and kind.startswith("text/html") and b"/assets/index-test.js" in body
    status, body, kind = call(hosted, "/assets/index-test.js", hosted=True)
    assert status == 200 and "javascript" in kind
    assert call(hosted, "/logo.svg", hosted=True)[2] == "image/svg+xml"
    admin = {"X-MS-CLIENT-PRINCIPAL-NAME": "sophie@example.org"}
    for gone in ("/workspace", "/public", "/p/app.js", "/assets/../index.html", "/api"):
        assert call(hosted, gone, hosted=True, headers=admin)[0] == 404
    status, body, _ = call(servers["local"], "/")
    assert status == 200 and b"/assets/index-test.js" in body


def test_cache_headers_and_compression(servers) -> None:
    hosted = servers["hosted"]

    def headers(path: str, extra: dict[str, str] | None = None) -> dict[str, str]:
        conn = http.client.HTTPConnection("127.0.0.1", hosted.server_port)
        conn.request("GET", path, headers={"Host": PUBLIC, **(extra or {})})
        response = conn.getresponse()
        response.read()
        conn.close()
        return {k.lower(): v for k, v in response.getheaders()}

    assert "immutable" in headers("/assets/index-test.js")["cache-control"]  # hashed asset
    assert headers("/")["cache-control"] == "no-cache"  # always revalidate the page
    assert headers("/api/health")["cache-control"] == "no-store"
    assert headers("/api/health")["x-content-type-options"] == "nosniff"


def test_identity_trusts_easy_auth_header_only_when_hosted(servers) -> None:
    spoof = {"X-MS-CLIENT-PRINCIPAL-NAME": "intruder@example.org"}
    # Loopback without allowed hosts: header ignored, local user is admin.
    identity = lambda me: {k: me[k] for k in ("name", "is_admin")}  # noqa: E731
    assert identity(call(servers["local"], "/api/me", headers=spoof)[1]) == {
        "name": None,
        "is_admin": True,
    }
    hosted = servers["hosted"]
    assert call(hosted, "/api/me", hosted=True, headers=spoof)[1]["is_admin"] is False
    assert identity(call(hosted, "/api/me", hosted=True)[1]) == {"name": None, "is_admin": False}
    me = call(hosted, "/api/me", hosted=True, headers={"X-MS-CLIENT-PRINCIPAL-NAME": ADMIN})[1]
    assert identity(me) == {"name": ADMIN, "is_admin": True}


def test_upload_requires_admin_when_visitor_uploads_are_off(servers) -> None:
    pdf = {"Content-Type": "application/pdf"}
    status, body, _ = call(
        servers["hosted"],
        "/api/upload?investigation=X",
        method="POST",
        headers=pdf,
        body=b"%PDF-1.4",
        hosted=True,
    )
    assert status == 403 and "Administrator" in body["error"]
    # Local loopback user is admin: request reaches validation (not a PDF -> 400).
    status, _, _ = call(
        servers["local"], "/api/upload?investigation=X", method="POST", headers=pdf, body=b"x"
    )
    assert status == 400


def test_removed_endpoints_are_gone(servers) -> None:
    hosted = servers["hosted"]
    same_origin = {"Content-Type": "application/json", "Origin": f"https://{PUBLIC}"}
    for path in ("/api/reviews", "/api/review-notes", "/api/predict", "/api/directions"):
        status, _, _ = call(
            hosted, path, method="POST", hosted=True, headers=same_origin, body=b"{}"
        )
        assert status == 404
    for path in ("/api/predict/options", "/api/overview", "/api/corpus/map", "/api/search"):
        assert call(hosted, path, hosted=True)[0] == 404


def test_coverage_falls_back_when_module_missing(servers, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "combustion_atlas.analysis.coverage", None)
    status, body, _ = call(servers["hosted"], "/api/coverage", hosted=True)
    assert status == 503 and body["error"] == "Analysis not available yet"


def test_ask_rejects_cross_origin(servers) -> None:
    status, _, _ = call(
        servers["hosted"],
        "/api/ask",
        method="POST",
        hosted=True,
        headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
        body=b"{}",
    )
    assert status == 403


def ndjson(raw: bytes) -> list[dict[str, Any]]:
    return [json.loads(line) for line in raw.decode().splitlines() if line.strip()]


def test_ask_stream_emits_progress_then_result(tmp_path: Path, monkeypatch) -> None:
    from combustion_atlas.providers import openai_answers
    from combustion_atlas.rag.chunk import chunk_page
    from combustion_atlas.rag.models import PageRecord
    from combustion_atlas.rag.store import DocumentStore

    page = PageRecord(
        source_id="a" * 16,
        filename="r.pdf",
        sha256="a" * 64,
        physical_page=2,
        text="A total of 126 tests were conducted.",
    )
    (tmp_path / "data/embeddings").mkdir(parents=True)
    with DocumentStore(tmp_path / "data/embeddings/rag.sqlite3") as store:
        store.replace([page], chunk_page(page))

    class FakeProvider:
        def __init__(self, _config: object) -> None: ...

        def answered_by(self) -> dict[str, object]:
            return {"model": "m", "provider": "OpenAI", "backup": False}

        def answer(self, question: str, context: list, progress=None, history=None):  # type: ignore[no-untyped-def]
            if progress:
                progress("answering", "Drafting a cited answer")
            return openai_answers.GroundedAnswer(
                status="insufficient_evidence", claims=[], limitations=[]
            )

    monkeypatch.setattr(openai_answers, "OpenAIAnswerProvider", FakeProvider)
    server = start(tmp_path, hosted=False)
    try:
        headers = {"Content-Type": "application/json"}
        body = json.dumps(
            {
                "question": "How many tests?",
                "method": "keyword",
                "generate_answer": True,
                "allow_provider_calls": True,
            }
        ).encode()
        status, raw, kind = call(
            server, "/api/ask/stream", method="POST", headers=headers, body=body
        )
        events = ndjson(raw)
        assert status == 200 and kind.startswith("application/x-ndjson")
        assert [e["type"] for e in events][-1] == "result"
        progress = [e for e in events if e["type"] == "progress"]
        assert progress and all("message" in e and "elapsed_s" in e for e in progress)
        assert any(e["stage"] == "answering" for e in progress)
        assert events[-1]["results"][0]["physical_page"] == 2
        assert events[-1]["answer"]["status"] == "insufficient_evidence"

        status, raw, _ = call(
            server, "/api/ask/stream", method="POST", headers=headers, body=b"{bad"
        )
        assert status == 200 and ndjson(raw)[-1]["type"] == "error"
        wrong_type = {"Content-Type": "text/plain"}
        assert (
            call(server, "/api/ask/stream", method="POST", headers=wrong_type, body=b"x")[0] == 400
        )
        cross = {**headers, "Origin": "http://evil.example"}
        assert call(server, "/api/ask/stream", method="POST", headers=cross, body=body)[0] == 403
    finally:
        server.shutdown()
        server.server_close()


def test_admin_identity_falls_back_to_email_claim_when_hosted(tmp_path) -> None:
    import base64
    import http.client
    import json as _json

    import serve

    claims = {"claims": [{"typ": "email", "val": "Admin@Example.edu"}]}
    principal = base64.b64encode(_json.dumps(claims).encode()).decode().rstrip("=")
    for hosted, expected in ((frozenset({"atlas.example.net"}), True), (frozenset(), None)):
        server = serve.start(
            **{
                "workspace": tmp_path,
                "allowed_hosts": hosted,
                "admins": frozenset({"admin@example.edu"}),
            }
        )
        host = "atlas.example.net" if hosted else f"127.0.0.1:{server.server_port}"
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
        conn.request("GET", "/api/me", headers={"Host": host, "X-MS-CLIENT-PRINCIPAL": principal})
        me = _json.loads(conn.getresponse().read())
        conn.close()
        server.shutdown()
        server.server_close()
        if expected:
            assert me["is_admin"] is True and me["name"] == "Admin@Example.edu"
        else:  # loopback ignores the header (local user is admin, but no hosted identity)
            assert me["name"] is None


def test_hosted_allowlist_blocks_other_signed_in_accounts(tmp_path) -> None:
    import http.client

    import serve

    server = serve.start(
        **{
            "workspace": tmp_path,
            "allowed_hosts": frozenset({"atlas.example.net"}),
            "admins": frozenset({"owner-gh"}),
            "allowed_users": frozenset({"friend-gh"}),
        }
    )

    def status(path: str, user: str | None) -> int:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
        headers = {"Host": "atlas.example.net"}
        if user:
            headers["X-MS-CLIENT-PRINCIPAL-NAME"] = user
        conn.request("GET", path, headers=headers)
        code = conn.getresponse().status
        conn.close()
        return code

    try:
        assert status("/api/me", "Owner-GH") == 200  # admin, case-insensitive
        assert status("/api/me", "friend-gh") == 200  # allow-listed
        assert status("/api/me", "stranger-gh") == 403
        assert status("/api/me", None) == 403
        assert status("/api/health", None) == 200  # health check stays open
    finally:
        server.shutdown()
        server.server_close()


def test_ask_stream_keeps_results_when_the_answer_fails(tmp_path: Path, monkeypatch) -> None:
    from combustion_atlas.providers import openai_answers
    from combustion_atlas.rag.chunk import chunk_page
    from combustion_atlas.rag.models import PageRecord
    from combustion_atlas.rag.store import DocumentStore

    page = PageRecord(
        source_id="a" * 16,
        filename="r.pdf",
        sha256="a" * 64,
        physical_page=2,
        text="A total of 126 tests were conducted.",
    )
    (tmp_path / "data/embeddings").mkdir(parents=True)
    with DocumentStore(tmp_path / "data/embeddings/rag.sqlite3") as store:
        store.replace([page], chunk_page(page))

    class Unconfigured:
        def __init__(self, _config: object) -> None:
            raise ValueError("Configure an OpenAI answer provider and answer model locally")

    monkeypatch.setattr(openai_answers, "OpenAIAnswerProvider", Unconfigured)
    server = start(tmp_path, hosted=False)
    try:
        headers = {"Content-Type": "application/json"}
        with_ai = {
            "question": "How many tests?",
            "method": "keyword",
            "generate_answer": True,
            "allow_provider_calls": True,
        }
        events = ndjson(
            call(
                server,
                "/api/ask/stream",
                method="POST",
                headers=headers,
                body=json.dumps(with_ai).encode(),
            )[1]
        )
        result = events[-1]
        assert result["type"] == "result" and result["results"][0]["physical_page"] == 2
        assert "answer" not in result and "AI answer unavailable" in result["answer_unavailable"]

        ai_off = {
            "question": "How many tests?",
            "method": "keyword",
            "generate_answer": False,
            "allow_provider_calls": False,
        }
        events = ndjson(
            call(
                server,
                "/api/ask/stream",
                method="POST",
                headers=headers,
                body=json.dumps(ai_off).encode(),
            )[1]
        )
        assert events[-1]["type"] == "result" and events[-1]["results"]
        assert "answer_unavailable" not in events[-1]
    finally:
        server.shutdown()
        server.server_close()


def test_react_nav_has_explore_menu_and_no_prediction() -> None:
    src = Path(__file__).parents[1] / "frontend/src"
    header = (src / "components/Header.tsx").read_text(encoding="utf-8")
    routes = (src / "lib/routes.ts").read_text(encoding="utf-8")
    assert 'href="#/coverage"' in header and 'href="#/landscape"' in header  # Explore menu
    assert 'aria-controls="explore-menu"' in header
    assert "predict" not in header
    # Old links keep working: coverage and landscape both belong to Explore.
    assert "p === 'coverage' || p === 'landscape'" in routes
