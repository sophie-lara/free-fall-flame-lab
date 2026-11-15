"""Corpus overview and PDF upload checks (offline)."""

import http.client
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter
from test_app import request, server, workspace  # noqa: F401  (pytest fixtures)

from combustion_atlas.app.server import ingest_upload
from combustion_atlas.rag.chunk import chunk_page
from combustion_atlas.rag.corpus import corpus_summary, page_sections
from combustion_atlas.rag.models import PageRecord
from combustion_atlas.rag.store import DocumentStore


def pages(texts: list[str], source: str = "a") -> list[PageRecord]:
    return [
        PageRecord(
            source_id=source * 16,
            investigation_id="PSI-25",
            filename="r.pdf",
            sha256=source * 64,
            physical_page=i,
            text=text,
        )
        for i, text in enumerate(texts, start=1)
    ]


def populated(path: Path) -> list[PageRecord]:
    records = pages(
        [
            "Contents\n2.0 First Report: A ....\n3.0 Second Report: B ....",
            "2.0 First Report: Ames\nOxygen flame spread over thin samples.",
            "Flame spread results continue here.",
            "3.0 Second Report: Brown\nRod extinction near the quenching limit.",
        ]
    )
    chunks = [c for p in records for c in chunk_page(p)]
    with DocumentStore(path) as store:
        store.replace(records, chunks)
        store.replace_vectors(
            model_key="m:3",
            provider="test",
            model="m",
            dimensions=3,
            vectors={
                c.chunk_id: [1.0, 0.1 * i, (-1.0) ** i] for i, c in enumerate(chunks, start=1)
            },
        )
    return records


def test_sections_skip_contents_pages_and_carry_forward(tmp_path: Path) -> None:
    populated(tmp_path / "rag.sqlite3")
    with DocumentStore(tmp_path / "rag.sqlite3") as store:
        sections = page_sections(store, "a" * 16)
        summary = corpus_summary(store)
    assert sections[1] == "Front matter"
    assert sections[2] == sections[3] == "2.0 First Report: Ames"
    assert sections[4] == "3.0 Second Report: Brown"
    doc = summary["documents"][0]
    assert summary["totals"]["documents"] == 1 and doc["pages"] == 4 and doc["embedded"] == 4
    assert [p["section"] for p in doc["page_strip"]][1:3] == ["2.0 First Report: Ames"] * 2


def pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    from io import BytesIO

    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_upload_saves_safely_and_adds_without_replacing(workspace) -> None:  # noqa: F811
    existing = populated(workspace.database)
    body = pdf_bytes()
    report = ingest_upload(
        workspace,
        body,
        filename="../../evil name.pdf",
        investigation="SAFFIRE-II",
        source_url=None,
        embed=False,
    )
    assert report["status"] == "added" and report["saved_as"] == "data/raw/uploads/evil-name.pdf"
    again = ingest_upload(
        workspace,
        body,
        filename="evil name.pdf",
        investigation="SAFFIRE-II",
        source_url=None,
        embed=False,
    )
    assert again["status"] == "unchanged"
    with DocumentStore(workspace.database) as store:
        assert store.connection.execute("SELECT count(*) FROM vectors").fetchone()[0] == len(
            existing
        )
    for bad in (
        {"body": b"not a pdf"},
        {"investigation": "<script>"},
        {"source_url": "javascript:alert(1)"},
    ):
        with pytest.raises(ValueError):
            ingest_upload(
                workspace,
                bad.get("body", body),
                filename="x.pdf",
                investigation=str(bad.get("investigation", "PSI-25")),
                source_url=bad.get("source_url"),  # type: ignore[arg-type]
                embed=False,
            )


def test_upload_endpoint_rejects_wrong_type_and_cross_origin(server) -> None:  # noqa: F811
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
    conn.request(
        "POST",
        "/api/upload?investigation=X",
        body=b"{}",
        headers={"Content-Type": "application/json"},
    )
    response = conn.getresponse()
    assert response.status == 400 and "PDF" in json.loads(response.read())["error"]
    conn.request(
        "POST",
        "/api/upload?investigation=X",
        body=pdf_bytes(),
        headers={"Content-Type": "application/pdf", "Origin": "http://evil.example"},
    )
    assert conn.getresponse().status == 403
    conn.close()


def test_corpus_endpoints(server, workspace) -> None:  # noqa: F811
    populated(workspace.database)
    status, body = request(server, "/api/corpus")
    assert status == 200 and body["totals"]["pages"] == 4
