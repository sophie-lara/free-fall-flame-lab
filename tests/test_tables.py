"""Synthetic table fixtures only; none of these values are NASA measurements."""

import hashlib
import json
from pathlib import Path

from PIL import Image

from combustion_atlas.rag.chunk import chunk_page
from combustion_atlas.rag.models import PageRecord
from combustion_atlas.rag.store import DocumentStore
from combustion_atlas.rag.tables import find_cells, resolve_cells, validate_manifest
from combustion_atlas.rag.visual_models import PageRegion, TableCell, TableContent, VisualArtifact

SHA = "c" * 64


def hierarchical_table() -> TableContent:
    # | Sample | Flow (cm/s)     |
    # |        | low   | high    |
    # | A      | 3     | <20     |
    # | B      | blank | ?       |
    return TableContent(
        rows=4,
        columns=3,
        cells=[
            TableCell(row=0, column=0, row_span=2, role="header", text="Sample"),
            TableCell(
                row=0, column=1, column_span=2, role="header", text="Flow (cm/s)", unit="cm/s"
            ),
            TableCell(row=1, column=1, role="header", text="low"),
            TableCell(row=1, column=2, role="header", text="high"),
            TableCell(row=2, column=0, role="row_header", text="A"),
            TableCell(row=2, column=1, text="3"),
            TableCell(row=2, column=2, text="<20"),
            TableCell(row=3, column=0, role="row_header", text="B"),
            TableCell(row=3, column=1, text="", state="blank"),
            TableCell(row=3, column=2, text=None, state="unreadable", uncertainty="smudged"),
        ],
        footnotes=["Synthetic."],
    )


def artifact(workspace: Path, **changes: object) -> VisualArtifact:
    crop = workspace / "data/processed/visuals/table.png"
    crop.parent.mkdir(parents=True, exist_ok=True)
    if not crop.exists():
        Image.new("RGB", (10, 10), "white").save(crop)
    base = VisualArtifact(
        artifact_id=f"{SHA[:16]}:p2:table:1",
        kind="table",
        source_id=SHA[:16],
        source_sha256=SHA,
        filename="tables.pdf",
        physical_page=2,
        label="1",
        caption="Synthetic flow table",
        region=PageRegion(
            page_width=100, page_height=100, x0=10, top=10, x1=90, bottom=50, scope="isolated"
        ),
        crop_path="data/processed/visuals/table.png",
        crop_sha256=hashlib.sha256(crop.read_bytes()).hexdigest(),
        method="manual",
        table=hierarchical_table(),
    )
    return VisualArtifact.model_validate({**base.model_dump(), **changes})


def indexed_database(workspace: Path) -> Path:
    database = workspace / "rag.sqlite3"
    page = PageRecord(
        source_id=SHA[:16], filename="tables.pdf", sha256=SHA, physical_page=2, text="Page two."
    )
    with DocumentStore(database) as store:
        store.replace([page], chunk_page(page))
    return database


def test_merged_headers_resolve_to_every_covered_column() -> None:
    cells = {(c["row"], c["column"]): c for c in resolve_cells(hierarchical_table())}
    assert cells[(2, 2)]["column_headers"] == ["Flow (cm/s)", "high"]
    assert cells[(2, 2)]["row_headers"] == ["A"]
    assert cells[(2, 2)]["text"] == "<20"  # qualifier preserved, never coerced
    assert cells[(2, 1)]["unit"] == "cm/s"  # inherited from the spanning header
    assert cells[(3, 1)]["state"] == "blank" and cells[(3, 2)]["text"] is None


def test_find_cells_reads_exact_values_by_header_path() -> None:
    hits = find_cells(hierarchical_table(), column="high", row="a")
    assert [(h["text"], h["unit"]) for h in hits] == [("<20", "cm/s")]
    assert len(find_cells(hierarchical_table(), column="flow")) == 4


def test_validator_accepts_a_matching_sample(tmp_path: Path) -> None:
    manifest = tmp_path / "tables.jsonl"
    manifest.write_text(artifact(tmp_path).model_dump_json() + "\n", encoding="utf-8")
    report = validate_manifest(manifest, workspace=tmp_path, database=indexed_database(tmp_path))
    assert report["valid"], report
    assert report["records"][0]["errors"] == []


def test_validator_reports_every_problem_without_writing(tmp_path: Path) -> None:
    database = indexed_database(tmp_path)
    good = artifact(tmp_path)
    no_header = TableContent(rows=1, columns=1, cells=[TableCell(row=0, column=0, text="12")])
    lines = [
        good.model_dump_json(),
        good.model_dump_json(),  # duplicate
        json.dumps({**good.model_dump(mode="json"), "artifact_id": "x:p9", "physical_page": 9}),
        json.dumps(
            {**good.model_dump(mode="json"), "artifact_id": "x:bad", "crop_sha256": "0" * 64}
        ),
        json.dumps(
            {**good.model_dump(mode="json"), "artifact_id": "x:nofile", "filename": "o.pdf"}
        ),
        json.dumps({**good.model_dump(mode="json"), "table": {"rows": 1}}),
        "{not json",
        artifact(tmp_path, artifact_id="x:warn", table=no_header).model_dump_json(),
    ]
    manifest = tmp_path / "tables.jsonl"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    before = database.read_bytes()
    report = validate_manifest(manifest, workspace=tmp_path, database=database)
    errors = {r["line"]: " ".join(r["errors"]) for r in report["records"]}
    assert not report["valid"]
    assert errors[1] == ""
    assert "Duplicate" in errors[2]
    assert "not in the document index" in errors[3]
    assert "Crop" in errors[4]
    assert "filename" in errors[5]
    assert "table" in errors[6]
    assert "Invalid JSON" in errors[7]
    warnings = " ".join(report["records"][7]["warnings"])
    assert "No header cells" in warnings and "numeric value without a unit" in warnings
    assert database.read_bytes() == before


def test_validator_flags_unchecked_source_identity(tmp_path: Path) -> None:
    manifest = tmp_path / "tables.jsonl"
    manifest.write_text(artifact(tmp_path).model_dump_json() + "\n", encoding="utf-8")
    report = validate_manifest(manifest, workspace=tmp_path, database=tmp_path / "missing.db")
    assert not report["valid"]
    assert "source identity was not checked" in report["file_errors"][0]


def test_validator_rejects_non_utf8(tmp_path: Path) -> None:
    manifest = tmp_path / "tables.jsonl"
    manifest.write_bytes(b"\xff\xfe{}")
    assert (
        "Not UTF-8"
        in validate_manifest(manifest, workspace=tmp_path, database=None)["file_errors"][0]
    )


def test_page_context_tables_are_flagged(tmp_path: Path) -> None:
    region = PageRegion(page_width=100, page_height=100, x0=0, top=0, x1=100, bottom=100)
    manifest = tmp_path / "tables.jsonl"
    manifest.write_text(artifact(tmp_path, region=region).model_dump_json() + "\n")
    report = validate_manifest(manifest, workspace=tmp_path, database=indexed_database(tmp_path))
    assert report["valid"]
    assert any("full-page context" in w for w in report["records"][0]["warnings"])
