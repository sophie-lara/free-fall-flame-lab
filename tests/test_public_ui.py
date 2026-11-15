"""Public UI mode, administrator gating, /api/me and analysis fallbacks."""

import http.client
import json
import sys
import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from combustion_atlas.app.server import AtlasHandler

PUBLIC = "atlas.example.net"
ADMIN = "Sophie@Example.org"


def start(
    tmp_path: Path, *, mode: str, hosted: bool, admins: frozenset[str] = frozenset()
) -> ThreadingHTTPServer:
    attrs = {
        "workspace": tmp_path,
        "ui_mode": mode,
        "allowed_hosts": frozenset({PUBLIC}) if hosted else frozenset(),
        "admins": frozenset(a.casefold() for a in admins),
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), type("H", (AtlasHandler,), attrs))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def servers(tmp_path: Path) -> Iterator[dict[str, ThreadingHTTPServer]]:
    made = {
        "public_hosted": start(tmp_path, mode="public", hosted=True, admins=frozenset({ADMIN})),
        "public_local": start(tmp_path, mode="public", hosted=False),
        "workspace_local": start(tmp_path, mode="workspace", hosted=False),
        "workspace_hosted": start(tmp_path, mode="workspace", hosted=True),
    }
    yield made
    for server in made.values():
        server.shutdown()
        server.server_close()


def call(
    server: ThreadingHTTPServer,
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


def test_public_mode_serves_public_ui_and_hides_workspace(servers) -> None:
    hosted = servers["public_hosted"]
    status, body, kind = call(hosted, "/", hosted=True)
    assert status == 200 and kind.startswith("text/html") and b"/p/app.js" in body
    assert call(hosted, "/p/app.js", hosted=True)[0] == 200
    assert call(hosted, "/p/styles.css", hosted=True)[0] == 200
    assert call(hosted, "/p/logo.svg", hosted=True)[2] == "image/svg+xml"
    assert call(hosted, "/p/flame-story.js", hosted=True)[2].startswith("text/javascript")
    assert call(hosted, "/p/flame-story.css", hosted=True)[2].startswith("text/css")
    assert call(hosted, "/workspace", hosted=True)[0] == 403  # not signed in as admin
    admin = {"X-MS-CLIENT-PRINCIPAL-NAME": "sophie@example.org"}
    status, body, _ = call(hosted, "/workspace", hosted=True, headers=admin)
    assert status == 200 and b"/app.js" in body and b"/p/app.js" not in body


def test_workspace_mode_unchanged_with_public_preview(servers) -> None:
    local = servers["workspace_local"]
    status, body, _ = call(local, "/")
    assert status == 200 and b"/p/app.js" not in body  # internal review UI
    status, body, _ = call(local, "/public")
    assert status == 200 and b"/p/app.js" in body


def test_identity_trusts_easy_auth_header_only_when_hosted(servers) -> None:
    spoof = {"X-MS-CLIENT-PRINCIPAL-NAME": "intruder@example.org"}
    # Loopback without allowed hosts: header ignored, local user is admin.
    identity = lambda me: {k: me[k] for k in ("name", "is_admin", "mode")}  # noqa: E731
    assert identity(call(servers["public_local"], "/api/me", headers=spoof)[1]) == {
        "name": None,
        "is_admin": True,
        "mode": "public",
    }
    hosted = servers["public_hosted"]
    assert call(hosted, "/api/me", hosted=True, headers=spoof)[1]["is_admin"] is False
    assert identity(call(hosted, "/api/me", hosted=True)[1]) == {
        "name": None,
        "is_admin": False,
        "mode": "public",
    }
    me = call(hosted, "/api/me", hosted=True, headers={"X-MS-CLIENT-PRINCIPAL-NAME": ADMIN})[1]
    assert identity(me) == {"name": ADMIN, "is_admin": True, "mode": "public"}
    # Hosted workspace mode with no admins configured: nobody is admin.
    assert call(servers["workspace_hosted"], "/api/me", hosted=True)[1]["is_admin"] is False


def test_upload_requires_admin_in_every_mode(servers) -> None:
    pdf = {"Content-Type": "application/pdf"}
    for name in ("public_hosted", "workspace_hosted"):
        status, body, _ = call(
            servers[name],
            "/api/upload?investigation=X",
            method="POST",
            headers=pdf,
            body=b"%PDF-1.4",
            hosted=True,
        )
        assert status == 403 and "Administrator" in body["error"]
    # Local loopback user is admin: request reaches validation (not a PDF -> 400).
    status, _, _ = call(
        servers["workspace_local"],
        "/api/upload?investigation=X",
        method="POST",
        headers=pdf,
        body=b"not a pdf",
    )
    assert status == 400


def test_review_posts_admin_only_in_public_mode(servers) -> None:
    note = json.dumps({"investigation_id": "X"}).encode()
    headers = {"Content-Type": "application/json"}
    status, _, _ = call(
        servers["public_hosted"],
        "/api/review-notes",
        method="POST",
        headers=headers,
        body=note,
        hosted=True,
    )
    assert status == 403
    # Workspace mode keeps prior behavior: validation error, not a permission error.
    status, _, _ = call(
        servers["workspace_hosted"],
        "/api/review-notes",
        method="POST",
        headers=headers,
        body=note,
        hosted=True,
    )
    assert status == 400


def test_analysis_endpoints_fall_back_when_module_missing(servers, monkeypatch) -> None:
    for name in ("combustion_atlas.analysis.coverage", "combustion_atlas.analysis.prediction"):
        monkeypatch.setitem(sys.modules, name, None)  # import raises ModuleNotFoundError
    hosted = servers["public_hosted"]
    for path in ("/api/coverage", "/api/predict/options"):
        status, body, _ = call(hosted, path, hosted=True)
        assert status == 503 and body["error"] == "Analysis not available yet"
    status, body, _ = call(
        hosted,
        "/api/predict",
        method="POST",
        hosted=True,
        headers={"Content-Type": "application/json", "Origin": f"https://{PUBLIC}"},
        body=json.dumps({"target": "x", "inputs": {}}).encode(),
    )
    assert status == 503


def test_predict_rejects_cross_origin(servers) -> None:
    status, _, _ = call(
        servers["public_hosted"],
        "/api/predict",
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
    server = start(tmp_path, mode="public", hosted=False)
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


def test_both_interfaces_carry_the_ui_switch() -> None:
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "src/combustion_atlas/app"
    for ui in ("static", "public"):
        assert 'id="ui-switch-slot"' in (app / ui / "index.html").read_text(encoding="utf-8")
        script = (app / ui / "app.js").read_text(encoding="utf-8")
        assert "function uiSwitchHTML" in script and 'role="switch"' in script


def test_admin_identity_falls_back_to_email_claim_when_hosted(tmp_path) -> None:
    import base64
    import http.client
    import json as _json
    import threading
    from http.server import ThreadingHTTPServer

    from combustion_atlas.app.server import AtlasHandler

    claims = {"claims": [{"typ": "email", "val": "Admin@Example.edu"}]}
    principal = base64.b64encode(_json.dumps(claims).encode()).decode().rstrip("=")
    for hosted, expected in ((frozenset({"atlas.example.net"}), True), (frozenset(), None)):
        handler = type(
            "H",
            (AtlasHandler,),
            {
                "workspace": tmp_path,
                "allowed_hosts": hosted,
                "ui_mode": "public",
                "admins": frozenset({"admin@example.edu"}),
            },
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
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
    import threading
    from http.server import ThreadingHTTPServer

    from combustion_atlas.app.server import AtlasHandler

    handler = type(
        "H",
        (AtlasHandler,),
        {
            "workspace": tmp_path,
            "allowed_hosts": frozenset({"atlas.example.net"}),
            "ui_mode": "public",
            "admins": frozenset({"owner-gh"}),
            "allowed_users": frozenset({"friend-gh"}),
        },
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

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
    server = start(tmp_path, mode="public", hosted=False)
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


def test_public_nav_has_explore_and_no_prediction() -> None:
    public = Path(__file__).parents[1] / "src/combustion_atlas/app/public"
    html = (public / "index.html").read_text(encoding="utf-8")
    js = (public / "app.js").read_text(encoding="utf-8")
    assert 'href="#/coverage"' in html and 'href="#/landscape"' in html  # Explore menu
    assert 'aria-controls="explore-menu"' in html
    assert "#/predict" not in html and "#/predict" not in js
    # Old links keep working: coverage and landscape both open the Explore page.
    assert "coverage: renderExplore, landscape: renderExplore" in js
