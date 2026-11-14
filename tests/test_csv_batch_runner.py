from pathlib import Path

import pytest

from combustion_atlas.ingestion.csv_batch_runner import prepare


def test_batch_selects_explicit_rows_and_rejects_non_run(tmp_path: Path) -> None:
    raw = tmp_path / "data/raw"
    raw.mkdir(parents=True)
    source = raw / "source.csv"
    source.write_text("Sample Number,Material\n2-6,\nF1C1,notes\n2-7,PMMA\n", encoding="utf-8")
    requests = prepare(tmp_path, source, "PSI-99", [2, 4])
    assert [record["test_id"] for record, _, _, _ in requests] == [
        "SAFFIRE-II-2-6", "SAFFIRE-II-2-7"]
    assert requests[0][1].cells[1].state == "blank"
    with pytest.raises(ValueError, match="not a supported experiment"):
        prepare(tmp_path, source, "PSI-99", [3])
    with pytest.raises(ValueError, match="distinct"):
        prepare(tmp_path, source, "PSI-99", [2, 2])
    with pytest.raises(ValueError, match="one to eleven"):
        prepare(tmp_path, source, "PSI-99", list(range(2, 14)))
