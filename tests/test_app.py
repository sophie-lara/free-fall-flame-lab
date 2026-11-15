import hashlib
import http.client
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import serve

from combustion_atlas.app.core import Atlas
from combustion_atlas.artifacts import CandidateBatch, SourceIdentity
from combustion_atlas.normalization.schema import (
    Conditions,
    ExperimentRecord,
    Measurement,
    Provenance,
)
from combustion_atlas.rag.chunk import chunk_page
from combustion_atlas.rag.models import PageRecord
from combustion_atlas.rag.store import DocumentStore
from combustion_atlas.review.candidates import CandidateStore, ReviewNote


@pytest.fixture
def workspace(tmp_path: Path) -> Atlas:
    raw = tmp_path / "data/raw/fixture.csv"
    raw.parent.mkdir(parents=True)
    raw.write_text("Test #,Oxygen\nT1,22.2\n", encoding="utf-8")
    sha = hashlib.sha256(raw.read_bytes()).hexdigest()
    p = Provenance(
        source_url="https://example.org/fixture",
        source_sha256=sha,
        record_number=2,
        column_name="Oxygen",
    )
    batch = CandidateBatch(
        generated_at=datetime.now(UTC),
        source=SourceIdentity(
            investigation_id="FIXTURE",
            source_url="https://example.org/fixture",
            sha256=sha,
            local_path=str(raw),
        ),
        records=[
            ExperimentRecord(
                investigation_id="FIXTURE",
                test_id="T1",
                provenance=[p],
                conditions=Conditions(
                    material="Test material",
                    oxygen_pct=Measurement(
                        value=22.2, unit="%", original_value="22.2", provenance=p
                    ),
                ),
                raw_cells={"Test #": "T1", "Oxygen": "22.2"},
            )
        ],
    )
    dest = tmp_path / "data/review/fixture-b1-b5.json"
    dest.parent.mkdir(parents=True)
    dest.write_text(batch.model_dump_json(), encoding="utf-8")
    return Atlas(tmp_path)


@pytest.fixture
def server(workspace: Atlas) -> Iterator[serve.RunningServer]:
    instance = serve.start(workspace=workspace.root)
    yield instance
    instance.shutdown()


def request(
    server: serve.RunningServer,
    path: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
    conn.request(
        "POST" if payload is not None else "GET",
        path,
        body=json.dumps(payload) if payload is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    response = conn.getresponse()
    body = response.read()
    result = (
        json.loads(body) if "application/json" in response.getheader("Content-Type", "") else body
    )
    conn.close()
    return response.status, result


def test_status_endpoints_and_static_paths(server: serve.RunningServer) -> None:
    readiness = request(server, "/api/rag-status")[1]
    assert readiness["indexed_chunks"] == 0 and readiness["embedded_chunks"] == 0
    assert not readiness["semantic_ready"]
    assert request(server, "/")[0] == 200
    assert request(server, "/../pyproject.toml")[0] == 404
    assert request(server, "/api/corpus", headers={"Host": "example.org"})[0] == 403
    for removed in ("/api/overview", "/api/experiments", "/api/sources", "/workspace"):
        assert request(server, removed)[0] == 404


def test_review_notes_are_bound_and_drafts_only(workspace: Atlas) -> None:
    store = CandidateStore(workspace.root)
    candidate = workspace.data / "review/fixture-b1-b5.json"
    before = candidate.read_bytes()
    note = {
        "investigation_id": "FIXTURE",
        "test_id": "T1",
        "reviewer": "Test reviewer",
        "decision": "accept_extraction",
        "note": "Fixture checked",
        "evidence": "Fixture record 2",
    }
    saved = store.save_note(ReviewNote(**note))
    assert saved["status"] == "draft"
    assert store.notes()[0]["binding_status"] == "matched"
    assert candidate.read_bytes() == before
    with pytest.raises(ValueError, match="Unknown candidate"):
        store.save_note(ReviewNote(**{**note, "test_id": "unknown"}))
    with pytest.raises(ValueError):
        ReviewNote(**{**note, "reviewer": "   "})
    changed = json.loads(candidate.read_text(encoding="utf-8"))
    changed["records"][0]["raw_cells"]["Oxygen"] = "changed"
    candidate.write_text(json.dumps(changed), encoding="utf-8")
    assert store.notes()[0]["binding_status"] == "stale"


def test_documents_require_matching_local_bytes(
    server: serve.RunningServer, workspace: Atlas
) -> None:
    raw = workspace.data / "raw/fixture.csv"
    sha = hashlib.sha256(raw.read_bytes()).hexdigest()
    page = PageRecord(
        source_id=sha[:16], filename="fixture.csv", sha256=sha, physical_page=1, text="T1 22.2"
    )
    with DocumentStore(workspace.database) as store:
        store.replace([page], chunk_page(page))
    path = "/api/documents/" + sha[:16]
    assert request(server, path)[1] == raw.read_bytes()
    raw.write_text("changed")
    assert request(server, path)[0] == 404
    assert request(server, "/api/documents/unknown")[0] == 404


def test_ask_preserves_native_chunk_citations(
    server: serve.RunningServer, workspace: Atlas
) -> None:
    page = PageRecord(
        source_id="toy",
        investigation_id="FIXTURE",
        filename="toy.pdf",
        sha256="a" * 64,
        physical_page=3,
        text="Seed storage preserves viability.",
    )
    with DocumentStore(workspace.database) as store:
        store.replace([page], chunk_page(page))
    status, payload = request(server, "/api/ask", {"question": "seed storage"})
    assert status == 200 and payload["results"][0]["physical_page"] == 3
    assert payload["results"][0]["sha256"] == "a" * 64
    assert request(server, "/api/ask", {"question": "   "})[0] == 400
    assert request(server, "/api/ask", {"question": "seed", "method": "hybrid"})[0] == 400
    assert request(server, "/api/ask", {"question": "seed", "generate_answer": True})[0] == 400
    assert (
        request(
            server, "/api/ask", {"question": "seed"}, headers={"Origin": "https://example.org"}
        )[0]
        == 403
    )


def test_empty_root_has_no_invented_records(tmp_path: Path) -> None:
    assert Atlas(tmp_path).source_rows() == []
    store = CandidateStore(tmp_path)
    assert store.records() == [] and store.notes() == [] and store.preserved() == []


def test_visual_crop_endpoint_is_hash_bound(server: serve.RunningServer, workspace: Atlas) -> None:
    from PIL import Image

    from combustion_atlas.rag.visual_models import (
        PageRegion,
        TableCell,
        TableContent,
        VisualArtifact,
    )

    crop = workspace.data / "processed/visuals/test.png"
    crop.parent.mkdir(parents=True)
    Image.new("RGB", (10, 10), "white").save(crop)
    page = PageRecord(
        source_id="b" * 16,
        filename="visual.pdf",
        sha256="b" * 64,
        physical_page=1,
        text="Test source page.",
    )
    artifact = VisualArtifact(
        artifact_id="test:p1:figure:1",
        kind="figure",
        source_id=page.source_id,
        source_sha256=page.sha256,
        filename=page.filename,
        physical_page=1,
        label="1",
        caption="Test diagram",
        crop_path="data/processed/visuals/test.png",
        crop_sha256=hashlib.sha256(crop.read_bytes()).hexdigest(),
        region=PageRegion(page_width=100, page_height=100, x0=0, top=0, x1=100, bottom=100),
    )
    with DocumentStore(workspace.database) as store:
        store.replace([page], chunk_page(page))
        store.upsert_visual(artifact)
    endpoint = "/api/visuals/" + artifact.artifact_id
    assert request(server, endpoint)[1] == crop.read_bytes()
    encoded = "/api/visuals/" + artifact.artifact_id.replace(":", "%3A")
    assert request(server, encoded)[1] == crop.read_bytes()
    assert request(server, "/api/visuals/unknown")[0] == 404
    assert request(server, endpoint + "/cells")[0] == 404  # figures have no cells
    table = TableContent(
        rows=2,
        columns=1,
        cells=[
            TableCell(row=0, column=0, role="header", text="Width (cm)", unit="cm"),
            TableCell(row=1, column=0, text="2"),
        ],
    )
    with DocumentStore(workspace.database) as store:
        store.upsert_visual(
            artifact.model_copy(
                update={"artifact_id": "test:p1:table:1", "kind": "table", "table": table}
            )
        )
    status, body = request(server, "/api/visuals/test%3Ap1%3Atable%3A1/cells")
    cells = body["resolved_cells"]
    assert status == 200
    assert cells == [
        {
            "row": 1,
            "column": 0,
            "text": "2",
            "state": "present",
            "unit": "cm",
            "uncertainty": None,
            "column_headers": ["Width (cm)"],
            "row_headers": [],
        }
    ]
    crop.write_bytes(b"tampered")
    assert request(server, endpoint)[0] == 400


def test_preserved_candidates_and_notes_remain_exact(workspace: Atlas) -> None:
    store = CandidateStore(workspace.root)
    root = workspace.data / "review/preserved-review"
    root.mkdir(parents=True)
    candidate = {
        "identity": {"investigation_id": "EXAMPLE", "test_id": "X1"},
        "conditions": {"material": {"value": "example"}},
        "raw_cells": [],
        "outcomes": [],
        "instrument_settings": {},
        "extra_metadata": {},
        "issues": [],
    }
    (root / "psi-25-b1-b5.json").write_text(json.dumps({"records": [candidate]}), encoding="utf-8")
    note = {
        "investigation_id": "EXAMPLE",
        "test_id": "X1",
        "reviewer": "Reviewer",
        "decision": "correction_proposed",
        "note": "Exact source comment.",
        "evidence": "Source row 2",
        "saved_at_utc": "2026-11-14T12:00:00Z",
        "status": "draft",
    }
    note_path = root / "human-notes.jsonl"
    note_path.write_text(json.dumps(note) + "\n", encoding="utf-8")
    before = note_path.read_bytes()
    assert store.preserved() == [candidate]
    assert store.notes() == [{**note, "binding_status": "unbound"}]
    assert note_path.read_bytes() == before
