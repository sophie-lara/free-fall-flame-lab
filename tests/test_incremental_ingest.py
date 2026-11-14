from pathlib import Path
from types import SimpleNamespace

import pytest

from combustion_atlas.providers.__main__ import embed_missing
from combustion_atlas.rag.build import add_document, build_index
from combustion_atlas.rag.chunk import chunk_page
from combustion_atlas.rag.models import PageRecord
from combustion_atlas.rag.store import DocumentStore


def page(source: str, text: str, investigation: str = "PSI-25") -> PageRecord:
    return PageRecord(
        source_id=source[:16],
        investigation_id=investigation,
        filename=f"{source[:4]}.pdf",
        source_url=f"https://example.invalid/{source[:4]}",
        sha256=source,
        physical_page=1,
        text=text,
    )


@pytest.fixture
def populated(tmp_path: Path) -> Path:
    database = tmp_path / "rag.sqlite3"
    original = page("a" * 64, "original oxygen evidence")
    with DocumentStore(database) as store:
        store.replace([original], chunk_page(original))
        chunk_id = store.list_chunks()[0].chunk_id
        store.replace_vectors(
            model_key="openai:m:2",
            provider="openai",
            model="m",
            dimensions=2,
            vectors={chunk_id: [1.0, 0.0]},
        )
    return database


def fake_pdf(monkeypatch: pytest.MonkeyPatch, records: list[PageRecord]) -> None:
    monkeypatch.setattr(
        "combustion_atlas.rag.build.extract_pdf",
        lambda *_, **kwargs: [
            r.model_copy(update={"investigation_id": kwargs["investigation_id"]}) for r in records
        ],
    )


def test_add_keeps_existing_vectors_and_records_per_document_metadata(
    populated: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_pdf(monkeypatch, [page("b" * 64, "saffire flame growth")])
    report = add_document(
        Path("saffire.pdf"),
        investigation_id="SAFFIRE-I",
        source_url="u",
        processed_dir=tmp_path / "processed",
        database=populated,
    )
    assert report["status"] == "added" and report["index_chunks_total"] == 2
    assert (tmp_path / "processed/sources/bbbbbbbbbbbbbbbb.chunks.jsonl").exists()
    with DocumentStore(populated) as store:
        assert store.connection.execute("SELECT count(*) FROM vectors").fetchone()[0] == 1
        assert store.search("saffire", "SAFFIRE-I", 5)[0]["source_id"] == "b" * 16
        assert store.search("saffire", "PSI-25", 5) == []
        assert [c.source_id for c in store.chunks_missing_vectors("openai:m:2")] == ["b" * 16]
    again = add_document(
        Path("saffire.pdf"),
        investigation_id="SAFFIRE-I",
        source_url="u",
        processed_dir=tmp_path / "processed",
        database=populated,
    )
    assert again["status"] == "unchanged" and again["chunks_added"] == 0


def test_conflicting_bytes_are_refused(populated: Path) -> None:
    conflict = page("a" * 16 + "f" * 48, "different bytes, same prefix")
    with DocumentStore(populated) as store, pytest.raises(ValueError, match="different bytes"):
        store.add_document([conflict], chunk_page(conflict))


def test_remove_deletes_only_one_source(populated: Path) -> None:
    other = page("c" * 64, "other source")
    with DocumentStore(populated) as store:
        store.add_document([other], chunk_page(other))
        assert store.remove_document("c" * 16) == {"pages": 1, "chunks": 1, "visual_artifacts": 0}
        assert store.chunk_count() == 1
        assert store.connection.execute("SELECT count(*) FROM vectors").fetchone()[0] == 1
        assert store.search("other", None, 5) == []


def test_build_refuses_to_replace_a_populated_index(populated: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="rag add"):
        build_index(
            [], investigation_id=None, source_url=None, processed_dir=tmp_path, database=populated
        )


def test_embed_missing_plans_without_calls_and_appends(
    populated: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    other = page("d" * 64, "new chunk")
    with DocumentStore(populated) as store:
        store.add_document([other], chunk_page(other))
    config = SimpleNamespace(embedding_model="m", embedding_dimensions=2)
    calls: list[list[str]] = []

    class Provider:
        model, dimensions, model_key = "m", 2, "openai:m:2"

        def __init__(self, _: object) -> None: ...

        def embed(self, texts: list[str]) -> list[list[float]]:
            calls.append(texts)
            return [[0.0, 1.0] for _ in texts]

    monkeypatch.setattr("combustion_atlas.providers.__main__.OpenAIEmbeddingProvider", Provider)
    embed_missing(populated, config, execute=False)  # type: ignore[arg-type]
    assert calls == [] and '"missing_chunks": 1' in capsys.readouterr().out
    embed_missing(populated, config, execute=True)  # type: ignore[arg-type]
    assert calls == [["new chunk"]]
    with DocumentStore(populated) as store:
        assert store.connection.execute("SELECT count(*) FROM vectors").fetchone()[0] == 2
