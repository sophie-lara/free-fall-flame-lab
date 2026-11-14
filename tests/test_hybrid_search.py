from pathlib import Path
from unittest.mock import Mock

import pytest

from combustion_atlas.rag.chunk import chunk_page
from combustion_atlas.rag.models import PageRecord
from combustion_atlas.rag.search import retrieve
from combustion_atlas.rag.store import DocumentStore


def test_hybrid_combines_rankings_and_keeps_investigation_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = Mock(model_key="test:2")
    provider.embed.return_value = [[1.0, 0.0]]
    monkeypatch.setattr("combustion_atlas.rag.search.OpenAIEmbeddingProvider", lambda _: provider)
    pages = [
        PageRecord(
            source_id=str(i),
            investigation_id=investigation,
            filename=f"{i}.pdf",
            physical_page=1,
            sha256=str(i) * 64,
            text=text,
        )
        for i, investigation, text in [
            (1, "A", "material dimensions"),
            (2, "A", "sample width"),
            (3, "B", "material dimensions"),
        ]
    ]
    chunks = [c for p in pages for c in chunk_page(p)]
    with DocumentStore(tmp_path / "rag.sqlite3") as store:
        store.replace(pages, chunks)
        with pytest.raises(ValueError, match="Generate document embeddings"):
            retrieve(store, "material", method="hybrid")
        provider.embed.assert_not_called()
        store.replace_vectors(
            model_key="test:2",
            provider="test",
            model="test",
            dimensions=2,
            vectors={c.chunk_id: [1.0, 0.0] for c in chunks},
        )
        hits = retrieve(store, "material", method="hybrid", investigation="A")
        assert hits[0]["source_id"] == "1"
        assert {c["source_id"] for c in hits} == {"1", "2"}
        assert all(c["physical_page"] == 1 for c in hits)
