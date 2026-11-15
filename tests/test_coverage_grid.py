"""Coverage heatmap grids: bins, cell classes, planned layer and gaps (synthetic data)."""

from typing import Any

import pytest

from combustion_atlas.analysis import coverage_grid as cg


def run(rid: str, family: str, **fields: Any) -> dict[str, Any]:
    raw = fields.pop("raw", {})
    return {
        "id": rid,
        "family": family,
        "investigation_id": "T",
        "test_id": rid,
        "material": fields.pop("material", None),
        "oxygen_pct": fields.pop("oxygen_pct", None),
        "pressure_kpa": fields.pop("pressure_kpa", None),
        "flow_cm_s": fields.pop("flow_cm_s", None),
        "review_status": fields.pop("review_status", "unreviewed"),
        "outcomes": {},
        "raw": raw,
    }


def flex(
    rid: str,
    o2: float,
    atm: float,
    fuel: str = "Methanol",
    co2: str = "0",
    he: str = "0",
    end: str = "Extinction",
) -> dict[str, Any]:
    return run(
        rid,
        "FLEX",
        material=fuel,
        oxygen_pct=o2,
        pressure_kpa=atm * cg.ATM_KPA,
        raw={
            "CO initial ambient composition; mole fraction": co2,
            "He initial ambient composition; mole fraction": he,
            "Test end": end,
        },
    )


def planned(o2: float, atm: float, fuel: str = "CH3OH", suppressant: str | None = None) -> dict:
    return {
        "test_id": "P",
        "fields": {"oxygen_pct": o2, "pressure_kpa": atm * cg.ATM_KPA},
        "fuel": fuel,
        "suppressant": suppressant,
    }


def grid(key: str, records: list[dict], proposed: list[dict] | None = None) -> dict[str, Any]:
    spec = next(s for s in cg.grid_specs() if s.key == key)
    return cg.build_grid(spec, records, proposed or [])


def cell(g: dict[str, Any], view: str, x_label: str, y_label: str) -> dict[str, Any]:
    i = next(k for k, b in enumerate(g["x"]["bins"]) if b["label"] == x_label)
    j = next(k for k, b in enumerate(g["y"]["bins"]) if b["label"] == y_label)
    return next(
        (c for c in g["views"][view]["cells"] if c["x"] == i and c["y"] == j),
        {"observed": 0, "planned": 0, "class": "gap"},
    )


ALL_FLEX = "fuel=all|diluent=all"


@pytest.mark.parametrize(
    ("observed", "planned", "expected"),
    [
        (5, 0, "strong"),
        (12, 9, "strong"),
        (4, 0, "moderate"),
        (2, 0, "moderate"),
        (1, 3, "sparse"),
        (0, 3, "planned"),
        (0, 0, "gap"),
    ],
)
def test_cell_class_thresholds(observed: int, planned: int, expected: str) -> None:
    assert cg.classify(observed, planned) == expected


def test_bin_edges_are_lower_inclusive_and_last_bin_closes() -> None:
    spec = next(s for s in cg.grid_specs() if s.key == "flex")
    labels = [b.label for b in spec.x.bins]
    assert labels[spec.x.locate(20.0)] == "20–22.5"
    assert labels[spec.x.locate(22.4999)] == "20–22.5"
    assert labels[spec.x.locate(35.0)] == "32.5–35"
    assert spec.x.locate(9.9) is None and spec.x.locate(35.1) is None


def test_planned_tests_never_count_as_runs() -> None:
    records = [flex("a", 21, 1.0)]
    proposed = [planned(21, 1.0)] * 10 + [planned(26, 0.85)] * 3
    g = grid("flex", records, proposed)
    tested = cell(g, ALL_FLEX, "20–22.5", "0.95–1.1")
    assert tested["observed"] == 1 and tested["planned"] == 10 and tested["class"] == "sparse"
    only_planned = cell(g, ALL_FLEX, "25–27.5", "0.8–0.95")
    assert only_planned["observed"] == 0 and only_planned["class"] == "planned"
    assert g["views"][ALL_FLEX]["totals"] == {
        "observed": 1,
        "planned": 13,
        "cells_with_runs": 1,
        "cells": len(g["x"]["bins"]) * len(g["y"]["bins"]),
    }


def gap_labels(g: dict[str, Any], view: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"planned": [], "unplanned": []}
    for gap in g["views"][view]["gaps"]:
        out[gap["status"]].append(gap["label"] + (f" | {gap['detail']}" if gap["detail"] else ""))
    return out


def test_flex_gaps_are_whole_bands_split_by_planned_status() -> None:
    # Runs only at mid O₂ / mid pressure; planned tests at low O₂ and high pressure.
    records = [flex("a", 21, 1.0), flex("b", 26, 0.7), flex("c", 15, 0.7)]
    proposed = [planned(11, 2.0)] * 3
    labels = gap_labels(grid("flex", records, proposed), ALL_FLEX)
    assert labels["planned"] == ["Low O₂ (<17.5 %) at high pressure (>1.1 atm) | 3 planned tests"]
    assert labels["unplanned"] == [
        "Low O₂ (<17.5 %) at low pressure (<0.6 atm)",
        "Mid O₂ (17.5–25 %) at low pressure (<0.6 atm)",
        "Mid O₂ (17.5–25 %) at high pressure (>1.1 atm)",
        "High O₂ (≥25 %) at low pressure (<0.6 atm)",
        "High O₂ (≥25 %) at high pressure (>1.1 atm)",
    ]
    # Bands that contain any run are never gaps, even if most of their cells are empty.
    assert not any("mid pressure" in label for label in labels["unplanned"])


def test_flex_facets_filter_runs_and_planned_tests() -> None:
    records = [
        flex("m", 21, 1.0, fuel="Methanol"),
        flex("h", 21, 1.0, fuel="Heptane", co2="0.2"),
        flex("he", 21, 1.0, fuel="Heptane", he="0.3"),
    ]
    proposed = [planned(21, 1.0, fuel="C7H16", suppressant="CO2"), planned(21, 1.0)]
    g = grid("flex", records, proposed)
    assert cell(g, ALL_FLEX, "20–22.5", "0.95–1.1")["observed"] == 3
    heptane_co2 = cell(g, "fuel=heptane|diluent=co2", "20–22.5", "0.95–1.1")
    assert heptane_co2["observed"] == 1 and heptane_co2["planned"] == 1
    assert cell(g, "fuel=methanol|diluent=none", "20–22.5", "0.95–1.1")["planned"] == 1
    assert cell(g, "fuel=all|diluent=he", "20–22.5", "0.95–1.1")["observed"] == 1


def test_zero_pressure_is_not_a_value() -> None:
    g = grid("flex", [flex("z", 21, 0.0)])
    assert g["unplaced"] == ["z"]
    assert g["views"][ALL_FLEX]["totals"]["observed"] == 0


def test_bass_material_classes_and_not_recorded_column() -> None:
    records = [
        run("b1", "BASS-II", oxygen_pct=17.2, raw={"Fuel Sample Material": '1/4" clear rod'}),
        run("b2", "BASS-II", oxygen_pct=21.0, raw={"Fuel Sample Material": "2 cm SIBAL"}),
        run("b3", "BASS-II", oxygen_pct=16.0, raw={"Fuel Sample Material": "200 micron 2 cm wide"}),
        run("b4", "BASS", raw={"Fuel Sample Material": "PMMA sphere 2 cm"}),
        run("b5", "BASS", raw={"Fuel Sample Material": "paraffin wax slab"}),
        run("b6", "BASS", raw={"Fuel Sample Material": "SOOT Cleaning"}),
    ]
    g = grid("bass", records)
    rows = [b["label"] for b in g["y"]["bins"]]
    # Empty categorical rows are dropped; used ones stay in the declared order.
    assert rows == ["SIBAL fabric", "PMMA rod", "PMMA sphere", "PMMA film", "Wax / candle"]
    assert g["x"]["bins"][-1]["key"] == cg.NOT_RECORDED
    assert cell(g, "all", "Not recorded", "PMMA sphere")["observed"] == 1
    assert cell(g, "all", "15–17.5", "PMMA rod")["observed"] == 1
    assert g["views"]["all"]["totals"]["observed"] == 5  # soot cleaning is not a burn
    # Materials whose runs all lack oxygen (sphere, wax) are listed apart from the bands.
    labels = gap_labels(g, "all")
    assert labels["planned"] == []
    assert labels["unplanned"] == [
        "Low O₂ (<17.5 %) | SIBAL fabric",
        "Mid O₂ (17.5–22.5 %) | PMMA rod, PMMA film",
        "High O₂ (≥22.5 %) | every sample material",
        "No runs at a recorded initial oxygen | PMMA sphere, Wax / candle",
        "Only one initial oxygen range tested | SIBAL fabric, PMMA rod, PMMA film",
    ]
    # BASS folds everything above 25 % into one "25+" column.
    oxygen = [b["label"] for b in g["x"]["bins"]]
    assert oxygen[-3:] == ["22.5–25", "25+", "Not recorded"]
    spec = next(s for s in cg.grid_specs() if s.key == "bass")
    assert spec.x.bins[spec.x.locate(31.0)].label == "25+"


def test_saffire_gaps_list_untested_materials_per_flow() -> None:
    records = [
        run(
            "s1",
            "Saffire",
            material="SIBAL Fabric",
            flow_cm_s=20.0,
            raw={"Flow Direction ": "Concurrent"},
        ),
        run("s2", "Saffire", material="SIBAL Fabric", flow_cm_s=30.0, raw={"Direction": "Opposed"}),
        run(
            "s3", "Saffire", material="Silicone", flow_cm_s=20.0, raw={"Flow Direction": "Opposed"}
        ),
        run("f1", "Saffire", material="Pre-test flow visualization data", raw={}),
    ]
    g = grid("saffire", records)
    assert g["views"]["all"]["totals"]["observed"] == 3
    assert cell(g, "all", "20 cm/s opposed", "Silicone")["class"] == "sparse"
    assert gap_labels(g, "all")["unplanned"] == [
        "20 cm/s concurrent flow | Silicone",
        "20 cm/s opposed flow | SIBAL (cotton-fiberglass)",
        "Higher air flow (30 cm/s) | Silicone",
    ]
