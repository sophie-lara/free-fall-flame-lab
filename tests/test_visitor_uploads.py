"""Public visitor uploads: quarantine, caps, code, per-visitor quota, approve/delete."""

import http.client
import json
import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from combustion_atlas.app.server import AtlasHandler, Workspace
from combustion_atlas.app.usage import PaidCallLimiter
from combustion_atlas.rag.chunk import chunk_page
from combustion_atlas.rag.corpus import corpus_summary
from combustion_atlas.rag.models import PageRecord
from combustion_atlas.rag.store import QUARANTINE, DocumentStore

HOST = "atlas.example.net"
ADMIN = "owner-gh"


def pdf(pages: int = 1, text: bytes = b"") -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    writer.add_metadata({"/Title": text.decode() or "t"})
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


class FakeEmbeddings:
    model, dimensions, model_key = "fake", 2, "openai:fake:2"

    def __init__(self, _config: object) -> None: ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


@pytest.fixture
def hosted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ThreadingHTTPServer]:
    monkeypatch.setattr("combustion_atlas.providers.OpenAIEmbeddingProvider", FakeEmbeddings)
    page = PageRecord(
        source_id="a" * 16,
        investigation_id="PSI-25",
        filename="r.pdf",
        sha256="a" * 64,
        physical_page=1,
        text="Shared report about oxygen.",
    )
    with DocumentStore(tmp_path / "data/embeddings/rag.sqlite3") as store:
        store.replace([page], chunk_page(page))
    handler = type(
        "H",
        (AtlasHandler,),
        {
            "workspace": tmp_path,
            "allowed_hosts": frozenset({HOST}),
            "ui_mode": "public",
            "admins": frozenset({ADMIN}),
            "public_uploads": True,
            "uploads_per_day": 3,
            "limiter": PaidCallLimiter(tmp_path / "data/usage/paid.json", daily_limit=100),
        },
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def post(
    server: ThreadingHTTPServer,
    path: str,
    body: bytes,
    *,
    ip: str = "1.1.1.1",
    ctype: str = "application/pdf",
    user: str | None = None,
    extra: dict[str, str] | None = None,
) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
    headers = {
        "Host": HOST,
        "Origin": f"https://{HOST}",
        "Content-Type": ctype,
        "X-Client-IP": ip,
        **(extra or {}),
    }
    if user:
        headers["X-MS-CLIENT-PRINCIPAL-NAME"] = user
    conn.request("POST", path, body=body, headers=headers)
    response = conn.getresponse()
    result = response.status, json.loads(response.read() or b"{}")
    conn.close()
    return result


def get(server: ThreadingHTTPServer, path: str, user: str | None = None) -> dict:
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
    headers = {"Host": HOST}
    if user:
        headers["X-MS-CLIENT-PRINCIPAL-NAME"] = user
    conn.request("GET", path, headers=headers)
    data = json.loads(conn.getresponse().read())
    conn.close()
    return data


def test_quarantined_source_is_hidden_unless_named(tmp_path: Path) -> None:
    pages = [
        PageRecord(
            source_id=s * 16,
            investigation_id=inv,
            filename=f"{s}.pdf",
            sha256=s * 64,
            physical_page=1,
            text="flame spread oxygen evidence",
        )
        for s, inv in (("a", "PSI-25"), ("b", QUARANTINE))
    ]
    with DocumentStore(tmp_path / "rag.sqlite3") as store:
        store.replace(pages, [c for p in pages for c in chunk_page(p)])
        assert {h["source_id"] for h in store.search("flame", None, 5)} == {"a" * 16}
        store.visible_sources = frozenset({"b" * 16})
        assert {h["source_id"] for h in store.search("flame", None, 5)} == {"a" * 16, "b" * 16}
        assert corpus_summary(store)["totals"]["documents"] == 1


def test_visitor_upload_rules_and_admin_review(hosted: ThreadingHTTPServer) -> None:
    me = get(hosted, "/api/me")
    assert me["can_upload"] and me["visitor_upload"]
    assert me["upload_limits"]["max_mb"] == 15 and me["upload_limits"]["max_pages"] == 60
    assert me["upload_limits"]["remaining_today"] == 3

    assert post(hosted, "/api/upload?filename=a.pdf", b"not a pdf", ctype="text/plain")[0] == 400
    too_long = post(hosted, "/api/upload?filename=long.pdf", pdf(pages=61))
    assert too_long[0] == 400 and "60 pages" in too_long[1]["error"]

    status, report = post(hosted, "/api/upload?filename=mine.pdf", pdf(text=b"one"))
    assert status == 201 and report["quarantined"] and report["uploads_left_today"] == 2
    source = report["source_id"]
    assert post(hosted, "/api/upload?filename=b.pdf", pdf(text=b"two"))[0] == 201
    assert post(hosted, "/api/upload?filename=c.pdf", pdf(text=b"three"))[0] == 201
    fourth = post(hosted, "/api/upload?filename=d.pdf", pdf(text=b"four"))
    assert fourth[0] == 429 and "3 uploads" in fourth[1]["error"]
    assert post(hosted, "/api/upload?filename=e.pdf", pdf(text=b"five"), ip="2.2.2.2")[0] == 201

    # Visitors cannot review; the admin sees the pending list and approves or deletes.
    assert (
        post(
            hosted,
            "/api/uploads/approve",
            json.dumps({"source_id": source}).encode(),
            ctype="application/json",
        )[0]
        == 403
    )
    pending = get(hosted, "/api/uploads/pending", user=ADMIN)["pending"]
    assert source in {p["source_id"] for p in pending} and len(pending) == 4
    bad = post(
        hosted,
        "/api/uploads/approve",
        json.dumps({"source_id": source, "investigation": QUARANTINE}).encode(),
        ctype="application/json",
        user=ADMIN,
    )
    assert bad[0] == 400
    ok = post(
        hosted,
        "/api/uploads/approve",
        json.dumps({"source_id": source, "investigation": "PSI-26"}).encode(),
        ctype="application/json",
        user=ADMIN,
    )
    assert ok[0] == 200 and ok[1]["approved"] == source
    other = pending[-1]["source_id"]
    gone = post(
        hosted,
        "/api/uploads/delete",
        json.dumps({"source_id": other}).encode(),
        ctype="application/json",
        user=ADMIN,
    )
    assert gone[0] == 200
    remaining = {p["source_id"] for p in get(hosted, "/api/uploads/pending", user=ADMIN)["pending"]}
    assert source not in remaining and other not in remaining


def test_upload_code_and_site_limit(hosted: ThreadingHTTPServer) -> None:
    hosted.RequestHandlerClass.upload_code = "judges-2026"  # type: ignore[attr-defined]
    assert post(hosted, "/api/upload?filename=a.pdf", pdf())[0] == 403
    assert (
        post(hosted, "/api/upload?filename=a.pdf", pdf(), extra={"X-Upload-Code": "judges-2026"})[0]
        == 201
    )
    hosted.RequestHandlerClass.upload_code = ""  # type: ignore[attr-defined]
    hosted.RequestHandlerClass.limiter = PaidCallLimiter(  # type: ignore[attr-defined]
        Path(hosted.RequestHandlerClass.workspace) / "data/usage/tight.json",  # type: ignore[attr-defined]
        daily_limit=1,
    )
    assert post(hosted, "/api/upload?filename=x.pdf", pdf(text=b"x"), ip="9.9.9.9")[0] == 201
    limited = post(hosted, "/api/upload?filename=y.pdf", pdf(text=b"y"), ip="8.8.8.8")
    assert limited[0] == 429 and "uploads" in limited[1]["error"]
    _ = Workspace  # imported for type context
