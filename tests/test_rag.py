import tempfile
import unittest
from pathlib import Path

from combustion_atlas.rag import DocumentStore, PageRecord, chunk_page
from combustion_atlas.rag.store import keyword_query


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

    def test_natural_language_question_matches_without_every_word(self) -> None:
        pages = [
            self.page("A total of 126 tests were conducted as part of BASS-II."),
            self.page("Oxygen sensors evaluated combustion completeness."),
        ]
        pages[1].physical_page = 4
        chunks = [chunk for page in pages for chunk in chunk_page(page)]
        with tempfile.TemporaryDirectory() as directory:
            with DocumentStore(Path(directory) / "rag.sqlite3") as store:
                store.replace(pages, chunks)
                results = store.search("How many tests were conducted in BASS-II?", None, 5)
                self.assertEqual(store.search("what is the", None, 5), [])
        self.assertEqual([r["physical_page"] for r in results], [3])

    def test_keyword_query_drops_question_words_and_punctuation(self) -> None:
        self.assertEqual(
            keyword_query("Which tests used BASS-II? - Tests"), '"tests" OR "used" OR "bass-ii"'
        )
        self.assertEqual(keyword_query("what is the"), '"what" OR "is" OR "the"')
        self.assertEqual(keyword_query("?? --"), "")

    def test_plural_query_matches_singular_text_and_old_indexes_migrate(self) -> None:
        import sqlite3

        page = self.page("Comparison of extinction velocity for thin samples")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rag.sqlite3"
            with DocumentStore(path) as store:
                store.replace([page], chunk_page(page))
            legacy = sqlite3.connect(path)
            legacy.executescript(
                "DROP TABLE chunks_fts; CREATE VIRTUAL TABLE chunks_fts USING fts5("
                "chunk_id UNINDEXED, text, tokenize='unicode61');"
                "INSERT INTO chunks_fts SELECT chunk_id, text FROM chunks;"
            )
            legacy.commit()
            legacy.close()
            with DocumentStore(path) as store:
                results = store.search("extinction velocities", None, 5)
                chunk_count = store.connection.execute("SELECT count(*) FROM chunks")
                self.assertEqual(chunk_count.fetchone()[0], 1)
        self.assertEqual(results[0]["chunk_id"], "source:p3:c0")
