"""Evidence landscape: clustering, related-evidence links, caching and the read-only API."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import serve

from combustion_atlas.analysis import landscape
from combustion_atlas.analysis.landscape import (
    attach_strays,
    build,
    fingerprint,
    load_cached,
    reuse_labels,
    sentence_case,
)
from combustion_atlas.rag.chunk import chunk_page
from combustion_atlas.rag.models import PageRecord
from combustion_atlas.rag.store import DocumentStore

TOPICS = ["droplet extinction heptane", "flame spread opposed flow pmma", "hardware camera wiring"]


def synthetic_points(per_topic: int = 30, dims: int = 64) -> list[dict[str, Any]]:
    rng = np.random.default_rng(0)
    centres = np.eye(dims)[: len(TOPICS)] * 5
    points = []
    for t, words in enumerate(TOPICS):
        for i in range(per_topic):
            points.append(
                {
                    "id": f"c{t}-{i:02d}",
                    "source_id": "a" * 16,
                    "filename": f"topic{t}.pdf",
                    "page": i + 1,
                    "investigation": "PSI-69",
                    "source_url": None,
                    "kind": "figure" if i == 0 else "passage",
                    "label": None,
                    "text": f"{words} measurement {i}",
                    "snippet": f"{words} measurement {i}",
                    "vector": (centres[t] + rng.normal(0, 0.3, dims)).tolist(),
                }
            )
    return points


def test_build_recovers_topics_with_neighbours_and_keywords() -> None:
    points = synthetic_points()
    result = build(points, min_cluster_size=10, neighbors=5)
    assert len(result["clusters"]) == 3
    by_id = {p["id"]: p for p in result["points"]}
    for t in range(3):  # each synthetic topic lands in one cluster
        assert len({by_id[f"c{t}-{i:02d}"]["cluster"] for i in range(30)}) == 1
    for point in result["points"]:
        assert 0 <= point["x"] <= 1 and 0 <= point["y"] <= 1
        assert len(point["p3"]) == 3 and sum(v * v for v in point["p3"]) <= 1.0001  # unit ball
        assert len(point["neighbors"]) == 5 and point["id"] not in point["neighbors"]
        same = {n.split("-")[0] for n in point["neighbors"]}
        assert same == {point["id"].split("-")[0]}  # related evidence stays on topic
        assert "vector" not in point and "text" not in point  # only display fields served
    keywords = {kw for c in result["clusters"] for kw in c["keywords"]}
    assert {"droplet", "pmma", "hardware"} <= keywords
    assert all(c["kinds"]["figure"] == 1 for c in result["clusters"])


def test_3d_layout_keeps_topics_apart() -> None:
    from sklearn.neighbors import NearestNeighbors  # type: ignore[import-untyped]

    result = build(synthetic_points(), min_cluster_size=10)
    xyz = np.array([p["p3"] for p in result["points"]])
    topic = np.array([p["cluster"] for p in result["points"]])
    _, index = NearestNeighbors(n_neighbors=6).fit(xyz).kneighbors(xyz)
    # On screen, a point's nearest neighbours in 3-D mostly share its topic (chance is
    # about 1/3 for three topics; the real 1,460-item map scores 0.99).
    assert (topic[index[:, 1:]] == topic[:, None]).mean() > 0.8


def test_ai_names_are_reused_only_for_identical_topics() -> None:
    result = build(synthetic_points(), min_cluster_size=10)
    previous = json.loads(json.dumps(result))
    for c in previous["clusters"]:
        c.update(label=f"Name {c['id']}", description="d", ai_label=True)
    assert reuse_labels(result, previous) == 3
    assert {c["label"] for c in result["clusters"]} == {"Name 0", "Name 1", "Name 2"}
    fresh = build(synthetic_points(), min_cluster_size=10)
    moved = next(p for p in previous["points"] if p["cluster"] == 0)
    moved["cluster"] = 1  # cluster 0 and 1 memberships no longer match
    assert reuse_labels(fresh, previous) == 1
    assert reuse_labels(fresh, None) == 0


def test_strays_join_only_a_clear_majority() -> None:
    core = np.array([0, 0, 0, 1, -1, -1])
    index = np.array(
        [
            [0, 1, 2, 3],
            [1, 0, 2, 3],
            [2, 0, 1, 3],
            [3, 0, 1, 2],
            [4, 0, 1, 2],  # neighbours all in cluster 0 -> joins
            [5, 0, 3, 4],  # split vote -> stays unassigned
        ]
    )
    assert attach_strays(core, index, neighbors=3) == [0, 0, 0, 1, 0, -1]


def test_sentence_case_keeps_acronyms() -> None:
    assert sentence_case("Methanol Droplet Drift") == "Methanol droplet drift"
    assert sentence_case("BASS-II Oxygen Dilution") == "BASS-II oxygen dilution"
    assert sentence_case("SLICE/BASS Hardware") == "SLICE/BASS hardware"


def test_labels_use_parsed_names(monkeypatch: pytest.MonkeyPatch) -> None:
    points = synthetic_points()
    result = build(points, min_cluster_size=10)
    calls: list[dict[str, Any]] = []

    class FakeResponses:
        def parse(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            parsed = kwargs["text_format"](label="Droplet Extinction", description="About drops.")
            return SimpleNamespace(output_parsed=parsed)

    monkeypatch.setattr("openai.OpenAI", lambda **_: SimpleNamespace(responses=FakeResponses()))
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    landscape.label_clusters(result, points)
    assert len(calls) == 3 and all(c["store"] is False for c in calls)
    assert all(c["label"] == "Droplet extinction" and c["ai_label"] for c in result["clusters"])
    assert "untrusted" in calls[0]["instructions"]


def test_cache_reports_stale_when_index_changes(tmp_path: Path) -> None:
    database = tmp_path / "rag.sqlite3"
    page = PageRecord(
        source_id="b" * 16, filename="r.pdf", sha256="b" * 64, physical_page=1, text="Flame."
    )
    chunks = chunk_page(page)
    model_key = "openai:test:2"
    with DocumentStore(database) as store:
        store.replace([page], chunks)
        cache = tmp_path / "landscape.json"
        cache.write_text(
            json.dumps({"points": [], "model_key": model_key, "key": fingerprint([], model_key)})
        )
        assert load_cached(cache, store)["stale"] is False  # type: ignore[index]
        cache.write_text(json.dumps({"points": [], "model_key": model_key, "key": "old"}))
        assert load_cached(cache, store)["stale"] is True  # type: ignore[index]
    assert load_cached(tmp_path / "missing.json") is None


def test_api_serves_cached_landscape_read_only(tmp_path: Path) -> None:
    import http.client

    server = serve.start(**{"workspace": tmp_path, "allowed_hosts": frozenset()})

    def get() -> Any:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
        conn.request("GET", "/api/landscape", headers={"Host": f"127.0.0.1:{server.server_port}"})
        response = conn.getresponse()
        body = json.loads(response.read())
        conn.close()
        return response.status, body

    try:
        assert get() == (200, {"points": [], "clusters": [], "missing": True})
        path = tmp_path / "data/processed/rag/landscape.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"points": [{"id": "x"}], "clusters": []}))
        status, body = get()
        assert status == 200 and body["points"] == [{"id": "x"}]
    finally:
        server.shutdown()
        server.server_close()
