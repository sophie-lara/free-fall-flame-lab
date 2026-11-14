import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image
from pydantic import ValidationError

from combustion_atlas.rag.chunk import chunk_page
from combustion_atlas.rag.models import PageRecord
from combustion_atlas.rag.store import DocumentStore
from combustion_atlas.rag.visual_models import PageRegion, TableCell, TableContent, VisualArtifact
from combustion_atlas.rag.visuals import (
    FigureDescription,
    crop_file,
    describe_figure,
    extract_figures,
)


@pytest.fixture
def figure(tmp_path: Path) -> VisualArtifact:
    crop = tmp_path / "data/processed/visuals/figure.png"
    crop.parent.mkdir(parents=True)
    Image.new("RGB", (20, 20), "white").save(crop)
    return VisualArtifact(
        artifact_id="example:p1:figure:1",
        kind="figure",
        source_id="a" * 16,
        source_sha256="a" * 64,
        filename="example.pdf",
        physical_page=1,
        label="1",
        caption="Figure 1 — Test diagram",
        region=PageRegion(page_width=100, page_height=100, x0=0, top=0, x1=100, bottom=100),
        crop_path="data/processed/visuals/figure.png",
        crop_sha256=hashlib.sha256(crop.read_bytes()).hexdigest(),
    )


def test_contract_preserves_units_qualifiers_and_explicit_blanks(figure: VisualArtifact) -> None:
    table = TableContent(
        rows=2,
        columns=2,
        cells=[
            TableCell(row=0, column=0, role="header", text="Length (mm)", unit="mm", column_span=2),
            TableCell(row=1, column=0, text="<0.1", unit="mm"),
            TableCell(row=1, column=1, text="", state="blank"),
        ],
    )
    artifact = VisualArtifact.model_validate(
        {**figure.model_dump(), "kind": "table", "table": table}
    )
    assert "<0.1" in artifact.retrieval_text()
    for changes in (
        {"crop_path": "data/processed/visuals/../secret.png"},
        {"source_id": "wrong"},
        {"review_status": "reviewed"},
    ):
        with pytest.raises(ValidationError):
            VisualArtifact.model_validate({**figure.model_dump(), **changes})
    with pytest.raises(ValidationError):
        TableContent(rows=2, columns=2, cells=[TableCell(row=0, column=0, text="incomplete")])


def test_incremental_index_preserves_text_vectors_and_invalidates_visuals(
    tmp_path: Path, figure: VisualArtifact
) -> None:
    page = PageRecord(
        source_id=figure.source_id,
        filename=figure.filename,
        sha256=figure.source_sha256,
        physical_page=1,
        text="Original experiment text.",
    )
    chunk = chunk_page(page)[0]
    with DocumentStore(tmp_path / "rag.sqlite3") as store:
        store.replace([page], [chunk])
        store.replace_vectors(
            model_key="model:2",
            provider="test",
            model="test",
            dimensions=2,
            vectors={chunk.chunk_id: [1, 0]},
        )
        assert store.upsert_visual(figure)
        assert not store.upsert_visual(figure)
        visual_id = store.connection.execute("SELECT chunk_id FROM visual_chunks").fetchone()[0]
        store.append_vectors(
            model_key="model:2", model="test", dimensions=2, vectors={visual_id: [0, 1]}
        )
        assert store.connection.execute("SELECT count(*) FROM vectors").fetchone()[0] == 2
        hit = store.dense_search([0, 1], model_key="model:2", top_k=1)[0]
        assert hit["visual"]["kind"] == "figure"
        assert hit["crop_url"].startswith("/api/visuals/")
        assert store.upsert_visual(figure.model_copy(update={"caption": "Changed caption"}))
        remaining = store.connection.execute("SELECT chunk_id FROM vectors").fetchall()
        assert [r[0] for r in remaining] == [chunk.chunk_id]
        assert store.connection.execute("SELECT count(*) FROM chunks").fetchone()[0] == 2


def test_vision_output_stays_unreviewed_and_verifies_crop(
    tmp_path: Path, figure: VisualArtifact
) -> None:
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(
        output_parsed=FigureDescription(
            description="A test diagram.",
            visible_labels=["A"],
            uncertainties=["Small label is unreadable."],
        ),
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
    )
    described = describe_figure(figure, tmp_path, "test-model", client=client)
    assert described.review_status == "unreviewed" and described.input_tokens == 100
    assert client.responses.parse.call_args.kwargs["store"] is False
    assert described.method == "openai_vision"
    crop_file(tmp_path, figure).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        describe_figure(figure, tmp_path, "test-model", client=client)
    assert client.responses.parse.call_count == 1


def test_figure_capture_ignores_table_captions_and_keeps_page_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"test source bytes")
    page = Mock(width=100, height=100)
    page.extract_text_lines.return_value = [
        {"text": "Table 1 — Complex table", "top": 10, "bottom": 20},
        {"text": "Figure 2.1.—Diagram", "top": 40, "bottom": 50},
        {"text": "Figure 2.1.—Diagram", "top": 70, "bottom": 80},
    ]
    page.to_image.return_value.original = Image.new("RGB", (100, 100), "white")
    context = Mock()
    context.__enter__ = Mock(return_value=SimpleNamespace(pages=[page]))
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("combustion_atlas.rag.visuals.pdfplumber.open", lambda _: context)
    items = extract_figures(pdf, tmp_path)
    assert len(items) == 1 and items[0].label == "2.1"
    assert items[0].region.scope == "page_context"
    assert crop_file(tmp_path, items[0]).exists()


def test_control_characters_in_vision_output_are_flagged() -> None:
    from combustion_atlas.rag.visuals import FigureDescription, control_character_warnings

    clean = FigureDescription(
        description="Igniter", visible_labels=["1,300 \u00b0C"], uncertainties=[]
    )
    corrupt = clean.model_copy(update={"visible_labels": ["Igniter (1,300 \u00176C)"]})
    assert control_character_warnings(clean) == []
    assert "control characters" in control_character_warnings(corrupt)[0]


def test_wrapped_and_appendix_captions_and_shared_pages() -> None:
    from combustion_atlas.rag.visuals import CAPTION, caption_lines

    lines = [
        {"text": "Body paragraph ends here.", "top": 0, "bottom": 10},
        {"text": "Figure B.1.—Model verification of", "top": 30, "bottom": 40},
        {"text": "dilution with (a) data.", "top": 41, "bottom": 51},
        {"text": "Next body paragraph after a gap.", "top": 70, "bottom": 80},
        {"text": "Figure 2.10a—Second figure", "top": 81, "bottom": 91},
        {"text": "NASA/TM-2021 page footer", "top": 92, "bottom": 99},
    ]
    assert caption_lines(lines, 1) == [
        "Figure B.1.—Model verification of",
        "dilution with (a) data.",
    ]
    assert caption_lines(lines, 4) == ["Figure 2.10a—Second figure"]
    labels = [m.group(1) for line in lines if (m := CAPTION.match(line["text"]))]
    assert labels == ["B.1", "2.10a"]
    assert CAPTION.match("Figure 5.2 shows the position") is None
