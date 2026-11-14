"""Coverage parsing, prediction gates and PSI batch selection (synthetic data only)."""

import json
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

from combustion_atlas.analysis import coverage, prediction
from combustion_atlas.analysis.coverage import Column, TableMap, find_gaps, load_records
from combustion_atlas.ingestion import psi_batch


def write_table(root: Path, accession: str, text: str, encoding: str = "utf-8") -> None:
    path = root / "raw/psi" / accession / "Experimental_table/table.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode(encoding))


@pytest.fixture
def synthetic_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    maps = [
        TableMap(
            "T-1",
            "Droplets",
            "Experimental_table/*.csv",
            geometry="droplet",
            encoding="cp1252",
            columns={
                "Id": Column("test_id"),
                "Fuel": Column("material"),
                "O2 fraction": Column("oxygen_pct", scale=100),
                "Pressure; mmHg": Column("pressure_kpa", scale=0.1333224),
                "Diameter": Column("droplet_diameter_mm"),
                "Burn time": Column("burn_time_s", suffix="s"),
            },
        )
    ]
    monkeypatch.setattr(coverage, "TABLE_MAPS", maps)
    monkeypatch.setattr(coverage, "ACTIVE_ACCESSIONS", {"T-1"})
    prediction._MODEL_CACHE.clear()


def test_only_plain_numbers_become_values_and_raw_text_is_kept(
    tmp_path: Path, synthetic_maps: None
) -> None:
    write_table(
        tmp_path,
        "T-1",
        "Id,Fuel,O2 fraction,Pressure; mmHg,Diameter,Burn time\n"
        "a,Heptane,0.21,760,2.0,4.5 s\n"
        "b,Heptane,~0.21,21–23,<1,n/a\n",
        encoding="cp1252",
    )
    first, second = load_records(tmp_path / "raw/psi")
    assert first["oxygen_pct"] == pytest.approx(21.0)
    assert first["pressure_kpa"] == pytest.approx(101.325, abs=0.01)
    assert first["outcomes"]["burn_time_s"] == {"value": 4.5, "raw": "4.5 s", "unit": "s"}
    assert first["geometry"] == "droplet" and first["review_status"] == "unreviewed"
    assert second["oxygen_pct"] is None and second["pressure_kpa"] is None  # ~, range kept
    assert second["droplet_diameter_mm"] is None
    assert second["raw"]["Pressure; mmHg"] == "21–23"
    assert second["outcomes"]["burn_time_s"]["value"] is None


def test_gaps_are_interior_holes_described_as_collection_gaps() -> None:
    records = [
        {"oxygen_pct": x, "pressure_kpa": y} for x in range(6) for y in range(6) if (x, y) != (2, 2)
    ]
    gaps = find_gaps(records, "oxygen_pct", "pressure_kpa")
    assert len(gaps) == 1 and "No runs in this collection" in gaps[0]["note"]
    assert find_gaps(records[:5], "oxygen_pct", "pressure_kpa") == []


def rows(n: int, *, signal: bool) -> str:
    generator = random.Random(1)
    lines = ["Id,Fuel,O2 fraction,Pressure; mmHg,Diameter,Burn time"]
    for i in range(n):
        o2 = generator.uniform(0.15, 0.4)
        d = generator.uniform(1.0, 4.0)
        burn = 2.0 * d * d + 3 * o2 + generator.gauss(0, 0.1) if signal else generator.uniform(1, 9)
        lines.append(f"r{i},Heptane,{o2:.3f},760,{d:.3f},{burn:.3f}")
    return "\n".join(lines) + "\n"


def test_model_answers_in_domain_and_refuses_outside(tmp_path: Path, synthetic_maps: None) -> None:
    write_table(tmp_path, "T-1", rows(80, signal=True))
    workspace = SimpleNamespace(data=tmp_path)
    body = {"target": "burn_time_s", "inputs": {"oxygen_pct": 25, "droplet_diameter_mm": 2.5}}
    result = prediction.predict_payload(workspace, body)
    model = result["model"]
    assert model["status"] == "ok" and model["in_domain"] and model["n_train"] == 80
    assert model["interval"][0] <= model["prediction"] <= model["interval"][1]
    assert model["cv_mae"] is not None and len(result["nearest"]) == 5
    assert result["nearest"][0]["distance"] <= result["nearest"][-1]["distance"]
    outside = prediction.predict_payload(
        workspace, {"target": "burn_time_s", "inputs": {"oxygen_pct": 25, "droplet_diameter_mm": 9}}
    )
    assert outside["model"]["status"] == "insufficient_data"
    assert "Outside" in outside["model"]["reason"]


def test_model_refuses_noise_and_small_samples(tmp_path: Path, synthetic_maps: None) -> None:
    workspace = SimpleNamespace(data=tmp_path)
    body = {"target": "burn_time_s", "inputs": {"oxygen_pct": 25, "droplet_diameter_mm": 2.5}}
    write_table(tmp_path, "T-1", rows(80, signal=False))
    noisy = prediction.predict_payload(workspace, body)["model"]
    assert noisy["status"] == "insufficient_data" and "baseline" in noisy["reason"]
    prediction._MODEL_CACHE.clear()
    write_table(tmp_path, "T-1", rows(12, signal=True))
    small = prediction.predict_payload(workspace, body)["model"]
    assert small["status"] == "insufficient_data" and "at least 30" in small["reason"]
    with pytest.raises(ValueError):
        prediction.predict_payload(workspace, {"target": "nope", "inputs": {"oxygen_pct": 1}})
    with pytest.raises(ValueError):
        prediction.predict_payload(workspace, {"target": "burn_time_s", "inputs": {}})


def test_psi_selection_and_capture_never_store_signed_links(tmp_path: Path) -> None:
    meta = {
        "investigationAcronym": "X",
        "title": "Test",
        "experimentalTable": [
            {
                "file_name": "t.csv",
                "file_size": 3,
                "version": 1,
                "remote_path": "/Home/psi-data/X/Experimental table/t.csv",
            }
        ],
        "added": [
            {"file_name": "r.pdf", "file_size": 4, "remote_path": "/Home/psi-data/X/Reports/r.pdf"},
            {
                "file_name": "raw.pdf",
                "file_size": 4,
                "remote_path": "/Home/psi-data/X/Raw Data/raw.pdf",
            },
            {
                "file_name": "secret.pdf",
                "file_size": 4,
                "restricted": True,
                "remote_path": "/Home/psi-data/X/Reports/secret.pdf",
            },
        ],
    }
    items = psi_batch.select_files("PSI-X", meta)
    assert [i["file_name"] for i in items] == ["t.csv", "r.pdf"]

    def fetch(url: str) -> bytes:
        assert "/studies/PSI-X/download?" in url
        return b"https://bucket.example/file?Signature=SECRET"

    def download(link: str, target: Path, *, max_bytes: int) -> dict[str, object]:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"data")
        return {"source_url": link, "sha256": "0" * 64, "size_bytes": 4}

    results = psi_batch.capture(
        items, tmp_path, max_bytes=10, fetch=fetch, download=download, pause=0
    )
    assert [r["status"] for r in results] == ["captured", "captured"]
    manifest = (tmp_path / "manifest.jsonl").read_text()
    assert "SECRET" not in manifest
    assert all(
        json.loads(line)["source_url"].startswith("https://psi.nasa.gov")
        for line in manifest.splitlines()
    )
    again = psi_batch.capture(
        items[1:], tmp_path, max_bytes=10, fetch=fetch, download=download, pause=0
    )
    assert again[0]["status"] == "already_captured"
