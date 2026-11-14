import hashlib
import http.client
import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from combustion_atlas.app.server import AtlasHandler, Workspace
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


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
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
    return Workspace(tmp_path)


@pytest.fixture
def server(workspace: Workspace) -> Iterator[ThreadingHTTPServer]:
    handler = type("TestHandler", (AtlasHandler,), {"workspace": workspace.root})
    instance = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance
    instance.shutdown()
    instance.server_close()
    thread.join()


def request(
    server: ThreadingHTTPServer,
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


def test_workspace_endpoints_and_candidate_schema(server: ThreadingHTTPServer) -> None:
    assert request(server, "/api/overview")[1]["experiments"] == 1
    data = request(server, "/api/experiments")[1]
    assert data["records"][0]["test_id"] == "T1"
    assert data["records"][0]["conditions"]["oxygen_pct"]["original_value"] == "22.2"
    assert data["record_sources"]["FIXTURE/T1"]["file_name"] == "fixture.csv"
    assert "local_path" not in data["record_sources"]["FIXTURE/T1"]
    assert request(server, "/api/structured-search?material=Test%20material")[1]["total"] == 1
    assert request(server, "/api/structured-search?oxygen_min_pct=23")[1]["total"] == 0
    assert request(server, "/api/structured-search?oxygen_min_pct=nan")[0] == 400
    assert request(server, "/api/structured-search?oxygen_min_pct=30&oxygen_max_pct=20")[0] == 400
    assert request(server, "/api/structured-search?unknown=1")[0] == 400
    assert request(server, "/api/search?q=oxygen")[0] == 503
    assert request(server, "/")[0] == 200
    assert request(server, "/../pyproject.toml")[0] == 404


def test_review_notes_are_bound_and_drafts_only(
    server: ThreadingHTTPServer, workspace: Workspace
) -> None:
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
    status, saved = request(server, "/api/reviews", note)
    assert status == 201 and saved["status"] == "draft"
    assert request(server, "/api/experiments")[1]["notes"][0]["note"] == "Fixture checked"
    assert request(server, "/api/experiments")[1]["notes"][0]["binding_status"] == "matched"
    assert candidate.read_bytes() == before
    assert request(server, "/api/reviews", {**note, "test_id": "unknown"})[0] == 400
    assert request(server, "/api/reviews", {**note, "reviewer": "   "})[0] == 400
    assert request(server, "/api/reviews", {**note, "approved": True})[0] == 400
    assert (
        request(server, "/api/reviews", note, headers={"Origin": "https://example.org"})[0] == 403
    )
    assert request(server, "/api/overview", headers={"Host": "example.org"})[0] == 403
    changed = json.loads(candidate.read_text(encoding="utf-8"))
    changed["records"][0]["raw_cells"]["Oxygen"] = "changed"
    candidate.write_text(json.dumps(changed), encoding="utf-8")
    assert request(server, "/api/experiments")[1]["notes"][0]["binding_status"] == "stale"


def test_captured_sources_require_matching_local_bytes(
    server: ThreadingHTTPServer, workspace: Workspace
) -> None:
    source = request(server, "/api/sources")[1]["sources"][0]
    assert source["available_locally"]
    path = "/api/documents/" + source["source_id"]
    assert request(server, path)[1] == (workspace.data / "raw/fixture.csv").read_bytes()
    (workspace.data / "raw/fixture.csv").write_text("changed")
    assert request(server, path)[0] == 404
    assert request(server, "/api/documents/unknown")[0] == 404


def test_search_preserves_native_chunk_citations(
    server: ThreadingHTTPServer, workspace: Workspace
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
    result = request(server, "/api/search?q=seed%20storage&investigation=FIXTURE&k=1")[1]
    assert result["results"][0]["physical_page"] == 3
    assert result["results"][0]["sha256"] == "a" * 64
    assert request(server, "/api/overview")[1]["documents"] == 1


def test_empty_workspace_has_no_invented_records(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    assert workspace.overview()["experiments"] == 0
    assert workspace.source_rows() == [] and workspace.notes() == []


def test_preserved_candidates_and_notes_remain_exact(workspace: Workspace) -> None:
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
    assert workspace.preserved() == [candidate]
    assert workspace.notes() == [{**note, "binding_status": "unbound"}]
    assert note_path.read_bytes() == before
