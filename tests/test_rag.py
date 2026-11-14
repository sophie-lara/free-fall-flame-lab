import tempfile
import unittest
from pathlib import Path

from combustion_atlas.rag import DocumentStore, PageRecord, chunk_page


class RagTests(unittest.TestCase):
    def page(self, text: str) -> PageRecord:
        return PageRecord(
            source_id="source",
            investigation_id="PSI-25",
            filename="report.pdf",
            sha256="a" * 64,
            physical_page=3,
            text=text,
        )

    def test_chunks_do_not_cross_physical_pages(self) -> None:
        chunks = chunk_page(self.page("one two three four five"), max_words=3, overlap_words=1)
        self.assertEqual([chunk.text for chunk in chunks], ["one two three", "three four five"])
        self.assertTrue(all(chunk.physical_page == 3 for chunk in chunks))

    def test_fts_returns_page_citation(self) -> None:
        page = self.page("oxygen concentration affects flame extinction")
        chunks = chunk_page(page)
        with tempfile.TemporaryDirectory() as directory:
            with DocumentStore(Path(directory) / "rag.sqlite3") as store:
                store.replace([page], chunks)
                results = store.search("oxygen extinction", "PSI-25", 3)
        self.assertEqual(results[0]["physical_page"], 3)
        self.assertEqual(results[0]["chunk_id"], "source:p3:c0")

    def test_dense_search_uses_a_model_namespace(self) -> None:
        page = self.page("oxygen concentration affects flame extinction")
        chunks = chunk_page(page)
        with tempfile.TemporaryDirectory() as directory:
            with DocumentStore(Path(directory) / "rag.sqlite3") as store:
                store.replace([page], chunks)
                store.replace_vectors(
                    model_key="openai:test:2",
                    provider="openai",
                    model="test",
                    dimensions=2,
                    vectors={chunks[0].chunk_id: [1.0, 0.0]},
                )
                results = store.dense_search(
                    [0.9, 0.1], model_key="openai:test:2", investigation_id="PSI-25"
                )
        self.assertEqual(results[0]["chunk_id"], "source:p3:c0")
        self.assertGreater(results[0]["score"], 0.9)
