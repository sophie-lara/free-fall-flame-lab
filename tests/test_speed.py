"""Speed features: local index snapshot, cached responses, vector cache, compression."""

import gzip
import http.client
import json
import time
from pathlib import Path

import serve

from combustion_atlas.app.core import Atlas
from combustion_atlas.rag.chunk import chunk_page
from combustion_atlas.rag.models import PageRecord
from combustion_atlas.rag.store import DocumentStore


def page(source: str, text: str) -> PageRecord:
    return PageRecord(
        source_id=source * 16,
        filename=f"{source}.pdf",
        sha256=source * 64,
        physical_page=1,
        text=text,
    )


def test_snapshot_is_used_for_reads_and_refreshes_after_writes(tmp_path: Path) -> None:
    atlas = Atlas(tmp_path, cache_dir=tmp_path / "local")
    with DocumentStore(atlas.database) as store:
        store.replace(
            [page("a", "Flame spread over PMMA.")], chunk_page(page("a", "Flame spread over PMMA."))
        )
    first = atlas.read_database
    assert first != atlas.database and first.parent == tmp_path / "local"
    with DocumentStore(first) as store:
        assert store.chunk_count() == 1
    time.sleep(0.01)
    new = page("b", "Droplet extinction in helium.")
    with DocumentStore(atlas.database) as store:  # a write to the shared index
        store.add_document([new], chunk_page(new))
    with DocumentStore(atlas.read_database) as store:
        assert store.chunk_count() == 2  # snapshot refreshed
    assert Atlas(tmp_path).read_database == Atlas(tmp_path).database  # no cache_dir: direct


def test_vector_cache_picks_up_new_vectors(tmp_path: Path) -> None:
    database = tmp_path / "rag.sqlite3"
    a, b = page("a", "alpha"), page("b", "beta")
    with DocumentStore(database) as store:
        store.replace([a, b], chunk_page(a) + chunk_page(b))
        ids = [c.chunk_id for c in store.list_chunks()]
        store.append_vectors(model_key="m:2", model="m", dimensions=2, vectors={ids[0]: [1.0, 0.0]})
        assert [r["chunk_id"] for r in store.dense_search([1.0, 0.0], model_key="m:2")] == [ids[0]]
    time.sleep(0.01)
    with DocumentStore(database) as store:
        store.append_vectors(model_key="m:2", model="m", dimensions=2, vectors={ids[1]: [0.0, 1.0]})
        top = store.dense_search([0.0, 1.0], model_key="m:2", top_k=2)
    assert [r["chunk_id"] for r in top] == [ids[1], ids[0]]  # new vector found and ranked first


def test_corpus_response_is_cached_until_the_index_changes(tmp_path: Path) -> None:
    with DocumentStore(tmp_path / "data/embeddings/rag.sqlite3") as store:
        store.replace([page("a", "one")], chunk_page(page("a", "one")))
    server = serve.start(workspace=tmp_path)

    def documents() -> int:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
        conn.request("GET", "/api/corpus", headers={"Host": f"127.0.0.1:{server.server_port}"})
        body = json.loads(conn.getresponse().read())
        conn.close()
        return int(body["totals"]["documents"])

    try:
        assert documents() == 1
        time.sleep(0.01)
        with DocumentStore(tmp_path / "data/embeddings/rag.sqlite3") as store:
            store.add_document([page("b", "two")], chunk_page(page("b", "two")))
        assert documents() == 2  # cache keyed by the index file signature
    finally:
        server.shutdown()


def test_large_json_is_gzipped_but_the_answer_stream_is_not(tmp_path: Path) -> None:
    landscape = tmp_path / "data/processed/rag/landscape.json"
    landscape.parent.mkdir(parents=True)
    landscape.write_text(
        json.dumps({"points": [{"id": f"p{i}"} for i in range(500)], "clusters": []})
    )
    server = serve.start(workspace=tmp_path)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
        host = f"127.0.0.1:{server.server_port}"
        conn.request("GET", "/api/landscape", headers={"Host": host, "Accept-Encoding": "gzip"})
        response = conn.getresponse()
        raw = response.read()
        assert response.getheader("Content-Encoding") == "gzip"
        assert len(json.loads(gzip.decompress(raw))["points"]) == 500
        conn.request(
            "POST",
            "/api/ask/stream",
            body=json.dumps({"question": "oxygen"}).encode(),
            headers={"Host": host, "Accept-Encoding": "gzip", "Content-Type": "application/json"},
        )
        response = conn.getresponse()
        response.read()
        assert response.getheader("Content-Encoding") is None
        conn.close()
    finally:
        server.shutdown()
