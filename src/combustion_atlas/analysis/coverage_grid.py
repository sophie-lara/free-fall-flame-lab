"""Binned coverage grids (heatmaps) built from structured experiment records.

Bins, material classes and cell classes are defined here, never in the browser, so every
cell can be explained exactly: which runs fall in it, which planned tests fall in it, and
why it has its class. Nothing is predicted.

Cell classes (observed runs only; planned tests never count as runs):

    strong    5+ observed runs
    moderate  2-4 observed runs
    sparse    1 observed run
    planned   no observed runs, but planned tests (FLEX EIRD test matrices)
    gap       no observed runs and no planned tests

Possible experimental gaps are reported per condition band (e.g. "high O2 at high
pressure"), not per cell: a band is a gap only when no run falls anywhere in it. "Gap"
always means "no runs in this collection", not that a condition was never studied.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from itertools import product
from typing import Any

from combustion_atlas.normalization.extractor import _number

ATM_KPA = 101.325
STRONG, MODERATE = 5, 2
NOT_RECORDED = "Not recorded"
ALL = "all"


@dataclass
class Bin:
    key: str
    label: str
    lo: float | None = None
    hi: float | None = None
    band: str | None = None  # condition band used to group gaps ("low", "high", ...)


@dataclass
class Axis:
    key: str
    label: str
    unit: str | None
    bins: list[Bin]
    ordered: bool  # neighbours along this axis are physically "nearby"
    # Value of a record (or planned test) on this axis: a number for numeric axes, a bin
    # key for categorical axes, or None when the record has no value.
    value: Callable[[dict[str, Any]], Any]
    planned_value: Callable[[dict[str, Any]], Any] | None = None
    missing_bin: bool = False  # add a "Not recorded" bin instead of dropping the record
    # Band key -> label, in display order. Without bands, each bin is its own block and
    # gaps list the bins by name (e.g. materials).
    bands: dict[str, str] = field(default_factory=dict)

    def locate(self, value: Any) -> int | None:
        if value is None:
            return len(self.bins) - 1 if self.missing_bin else None
        if isinstance(value, str):
            for i, b in enumerate(self.bins):
                if b.key == value:
                    return i
            return None
        numeric = [b for b in self.bins if b.lo is not None]
        for i, b in enumerate(self.bins):
            if b.lo is None or b.hi is None:
                continue
            last = b is numeric[-1]
            if b.lo <= value < b.hi or (last and value == b.hi):
                return i
        return None


@dataclass
class Facet:
    key: str
    label: str
    options: list[tuple[str, str]]  # (key, label); ALL is added automatically
    value: Callable[[dict[str, Any]], str | None]
    planned_value: Callable[[dict[str, Any]], str | None] | None = None


@dataclass
class GridSpec:
    key: str
    label: str
    families: set[str]
    description: str
    x: Axis
    y: Axis
    facets: list[Facet] = field(default_factory=list)
    planned: bool = False
    include: Callable[[dict[str, Any]], bool] = lambda r: True
    outcome: Callable[[dict[str, Any]], str | None] = lambda r: None
    notes: list[str] = field(default_factory=list)


# ---------- shared bins ----------


def _range_bins(edges: list[float], unit: str, fmt: str = "{:g}") -> list[Bin]:
    return [
        Bin(f"{lo:g}-{hi:g}", f"{fmt.format(lo)}–{fmt.format(hi)}", lo, hi)
        for lo, hi in zip(edges, edges[1:], strict=False)
    ]


OXYGEN_EDGES = [10, 12.5, 15, 17.5, 20, 22.5, 25, 27.5, 30, 32.5, 35]
PRESSURE_EDGES = [0.4, 0.6, 0.8, 0.95, 1.1, 1.75, 2.5, 3.25]
# (band key, label, upper edge): a bin belongs to the first band whose edge it does not pass.
OXYGEN_BANDS = [
    ("low", "Low O₂ (<17.5 %)", 17.5),
    ("mid", "Mid O₂ (17.5–25 %)", 25.0),
    ("high", "High O₂ (≥25 %)", float("inf")),
]
PRESSURE_BANDS = [
    ("low", "low pressure (<0.6 atm)", 0.6),
    ("mid", "mid pressure (0.6–1.1 atm)", 1.1),
    ("high", "high pressure (>1.1 atm)", float("inf")),
]


def _banded(bins: list[Bin], bands: list[tuple[str, str, float]]) -> list[Bin]:
    for b in bins:
        if b.hi is not None:
            b.band = next(key for key, _, edge in bands if b.hi <= edge)
    return bins


def _band_labels(bands: list[tuple[str, str, float]]) -> dict[str, str]:
    return {key: label for key, label, _ in bands}


def _oxygen_bins() -> list[Bin]:
    return _banded(_range_bins(OXYGEN_EDGES, "%"), OXYGEN_BANDS)


# ---------- material classes (explicit, reviewable) ----------

# Ordered rules over the raw material text (lowercased); the first match wins. Edit here
# when a reviewer corrects a class. Unmatched text falls into "Other" and stays visible.
BASS_MATERIAL_RULES: list[tuple[str, str]] = [
    ("wax", r"wax|candle|paraf|parraf"),
    ("sibal", r"sibal"),
    ("nomex", r"nomex"),
    ("ultem", r"ultem"),
    ("pmma-sphere", r"sphere|spherical"),
    ("pmma-rod", r"\brod\b"),
    ("pmma-film", r"film|micron|thick"),
    ("pmma-slab", r"slab"),
    ("pmma-flat", r"pmma"),
]
BASS_MATERIAL_LABELS = {
    "sibal": "SIBAL fabric",
    "pmma-rod": "PMMA rod",
    "pmma-sphere": "PMMA sphere",
    "pmma-film": "PMMA film",
    "pmma-flat": "PMMA flat sample",
    "pmma-slab": "PMMA slab",
    "wax": "Wax / candle",
    "nomex": "Nomex",
    "ultem": "Ultem sheet",
    "other": "Other",
}
NOT_A_BURN = re.compile(r"soot cleaning", re.I)


def bass_material(record: dict[str, Any]) -> str | None:
    raw = (record.get("raw") or {}).get("Fuel Sample Material") or record.get("material") or ""
    text = " ".join(str(raw).split()).lower()
    if not text:
        return None
    # BASS-II "100 micron film 2 cm wide" / "200 micron 2 cm wide" carry no "PMMA" text;
    # the BASS-II summary describes these films as PMMA.
    for key, pattern in BASS_MATERIAL_RULES:
        if re.search(pattern, text):
            return key
    return "other"


SAFFIRE_MATERIAL_RULES: list[tuple[str, str]] = [
    ("pmma-nomex", r"pmma.*nomex|nomex.*pmma"),
    ("sibal", r"sibal"),
    ("silicone", r"silicone"),
    ("pmma", r"pmma"),
]
SAFFIRE_MATERIAL_LABELS = {
    "sibal": "SIBAL (cotton-fiberglass)",
    "silicone": "Silicone",
    "pmma": "PMMA",
    "pmma-nomex": "PMMA + Nomex",
    "other": "Other",
}


def saffire_material(record: dict[str, Any]) -> str | None:
    text = (record.get("material") or "").lower()
    if not text:
        return None
    for key, pattern in SAFFIRE_MATERIAL_RULES:
        if re.search(pattern, text):
            return key
    return "other"


def saffire_flow(record: dict[str, Any]) -> str | None:
    raw = record.get("raw") or {}
    direction = next(
        (str(v).strip().lower() for k, v in raw.items() if "direction" in k.lower() and v), ""
    )
    flow = record.get("flow_cm_s")
    if flow is None or direction not in {"concurrent", "opposed"}:
        return None
    return f"{flow:g}-{direction}"


def _is_saffire_run(record: dict[str, Any]) -> bool:
    return record.get("flow_cm_s") is not None


# ---------- FLEX ----------

PLANNED_FUELS = {"ch3oh": "methanol", "c7h16": "heptane"}


def flex_fuel(record: dict[str, Any]) -> str | None:
    text = (record.get("material") or "").strip().lower()
    return text or None


def flex_planned_fuel(test: dict[str, Any]) -> str | None:
    text = (test.get("fuel") or "").strip().lower()
    return PLANNED_FUELS.get(text, text or None)


def _fraction(raw: dict[str, Any], prefix: str) -> float | None:
    for key, value in raw.items():
        if key.lower().startswith(prefix.lower()):
            return _number(str(value or "").strip())
    return None


def flex_diluent(record: dict[str, Any]) -> str | None:
    raw = record.get("raw") or {}
    co2 = _fraction(raw, "CO initial")  # FLEX prints "CO" without the subscript: CO₂
    he = _fraction(raw, "He initial")
    if co2 is None or he is None:
        return None
    if co2 > 0 and he > 0:
        return "co2-he"
    if co2 > 0:
        return "co2"
    if he > 0:
        return "he"
    return "none"


def flex_planned_diluent(test: dict[str, Any]) -> str:
    suppressant = (test.get("suppressant") or "").strip().lower()
    return {"co2": "co2", "he": "he", "helium": "he", "sf6": "sf6"}.get(suppressant, "none")


def flex_pressure_atm(record: dict[str, Any]) -> float | None:
    kpa = record.get("pressure_kpa")
    if kpa is None or kpa <= 0:  # one FLEX row prints 0 mmHg: not a usable pressure
        return None
    return float(kpa) / ATM_KPA


def flex_planned_pressure(test: dict[str, Any]) -> float | None:
    kpa = test["fields"].get("pressure_kpa")
    return None if kpa is None else kpa / ATM_KPA


def flex_outcome(record: dict[str, Any]) -> str | None:
    value = ((record.get("raw") or {}).get("Test end") or "").strip()
    return value or None


def _numeric(key: str) -> Callable[[dict[str, Any]], float | None]:
    return lambda r: r.get(key)


def _planned_numeric(key: str) -> Callable[[dict[str, Any]], float | None]:
    return lambda p: p["fields"].get(key)


def grid_specs() -> list[GridSpec]:
    bass_rows = [Bin(k, v) for k, v in BASS_MATERIAL_LABELS.items()]
    saffire_rows = [Bin(k, v) for k, v in SAFFIRE_MATERIAL_LABELS.items()] + [
        Bin(NOT_RECORDED, NOT_RECORDED)
    ]
    return [
        GridSpec(
            key="bass",
            label="BASS & BASS-II",
            families={"BASS", "BASS-II"},
            description=(
                "Solid-fuel flame spread runs by initial oxygen and sample material. BASS (PSI-26) "
                "records no oxygen, so its runs sit in the “Not recorded” column."
            ),
            x=Axis(
                "oxygen_pct",
                "Initial oxygen",
                "% vol",
                [*_oxygen_bins(), Bin(NOT_RECORDED, NOT_RECORDED)],
                ordered=True,
                value=_numeric("oxygen_pct"),
                missing_bin=True,
                bands=_band_labels(OXYGEN_BANDS),
            ),
            y=Axis(
                "material", "Sample material", None, bass_rows, ordered=False, value=bass_material
            ),
            include=lambda r: (
                not NOT_A_BURN.search(str((r.get("raw") or {}).get("Fuel Sample Material") or ""))
            ),
            notes=[
                "BASS-II airflow was recorded as uncalibrated fan/air display settings, so flow "
                "is not an axis.",
                "Material classes come from the table’s material text by explicit rules; "
                "BASS-II films without a material name are counted as PMMA film.",
            ],
        ),
        GridSpec(
            key="flex",
            label="FLEX",
            families={"FLEX"},
            description=(
                "Droplet combustion runs by ambient oxygen and pressure. Planned tests from the "
                "EIRD test matrices are hatched and never count as runs."
            ),
            x=Axis(
                "oxygen_pct",
                "Ambient oxygen",
                "% mole",
                _oxygen_bins(),
                ordered=True,
                value=_numeric("oxygen_pct"),
                planned_value=_planned_numeric("oxygen_pct"),
                bands=_band_labels(OXYGEN_BANDS),
            ),
            y=Axis(
                "pressure_atm",
                "Ambient pressure",
                "atm",
                _banded(_range_bins(PRESSURE_EDGES, "atm"), PRESSURE_BANDS),
                ordered=True,
                value=flex_pressure_atm,
                planned_value=flex_planned_pressure,
                bands=_band_labels(PRESSURE_BANDS),
            ),
            facets=[
                Facet(
                    "fuel",
                    "Fuel",
                    [("methanol", "Methanol"), ("heptane", "Heptane")],
                    value=flex_fuel,
                    planned_value=flex_planned_fuel,
                ),
                Facet(
                    "diluent",
                    "Added diluent",
                    [
                        ("none", "None (O₂/N₂)"),
                        ("co2", "CO₂"),
                        ("he", "Helium"),
                        ("co2-he", "CO₂ + helium"),
                        ("sf6", "SF₆"),
                    ],
                    value=flex_diluent,
                    planned_value=flex_planned_diluent,
                ),
            ],
            planned=True,
            outcome=flex_outcome,
            notes=[
                "Observed pressure is converted from mmHg and planned pressure from atm; oxygen "
                "is the mole fraction × 100.",
            ],
        ),
        GridSpec(
            key="saffire",
            label="Saffire",
            families={"Saffire"},
            description=(
                "Large-scale spacecraft fire runs by air flow, flow direction and material. "
                "Oxygen was close to cabin air (about 21.5 %) in every run, so it is not an axis."
            ),
            x=Axis(
                "flow",
                "Air flow and direction",
                None,
                [
                    Bin("20-concurrent", "20 cm/s concurrent", band="20-concurrent"),
                    Bin("20-opposed", "20 cm/s opposed", band="20-opposed"),
                    Bin("30-concurrent", "30 cm/s concurrent", band="30"),
                    Bin("30-opposed", "30 cm/s opposed", band="30"),
                ],
                ordered=False,
                value=saffire_flow,
                bands={
                    "20-concurrent": "20 cm/s concurrent flow",
                    "20-opposed": "20 cm/s opposed flow",
                    "30": "Higher air flow (30 cm/s)",
                },
            ),
            y=Axis(
                "material",
                "Sample material",
                None,
                saffire_rows,
                ordered=False,
                value=saffire_material,
                missing_bin=True,
            ),
            include=_is_saffire_run,
            notes=[
                "Saffire tables also hold flow-visualization rows and notes; only samples with "
                "an air flow are counted as runs."
            ],
        ),
    ]


# ---------- aggregation ----------


def classify(observed: int, planned: int) -> str:
    if observed >= STRONG:
        return "strong"
    if observed >= MODERATE:
        return "moderate"
    if observed == 1:
        return "sparse"
    return "planned" if planned else "gap"


def _neighbours(spec: GridSpec, i: int, j: int) -> list[tuple[int, int]]:
    dx = [-1, 0, 1] if spec.x.ordered else [0]
    dy = [-1, 0, 1] if spec.y.ordered else [0]
    out = []
    for a, b in product(dx, dy):
        if (a, b) == (0, 0):
            continue
        ni, nj = i + a, j + b
        if not (0 <= ni < len(spec.x.bins) and 0 <= nj < len(spec.y.bins)):
            continue
        # "Not recorded" columns/rows are not physically next to anything.
        if spec.x.bins[ni].key == NOT_RECORDED or spec.y.bins[nj].key == NOT_RECORDED:
            continue
        out.append((ni, nj))
    return out


def _block(axis: Axis, index: int) -> str:
    """Gap block of a bin: its band when the axis has bands, else the bin itself."""
    b = axis.bins[index]
    return b.band if axis.bands and b.band else f"bin:{index}"


def _gap_groups(
    spec: GridSpec, cells: dict[tuple[int, int], dict[str, Any]]
) -> list[dict[str, Any]]:
    """Condition bands with no runs at all, grouped and described in a few words.

    A block is (x band or bin) x (y band or bin). It is a gap only when no run falls in any
    of its cells, and "planned" when planned tests fall in it. Blocks are grouped by their
    banded sides; unbanded sides (materials) are listed by name.
    """

    def real(axis: Axis, i: int) -> bool:
        return axis.bins[i].key != NOT_RECORDED

    xs = [i for i in range(len(spec.x.bins)) if real(spec.x, i)]
    ys = [j for j in range(len(spec.y.bins)) if real(spec.y, j)]
    # An unbanded bin (a material) only counts if it has runs at a recorded value on the
    # other axis: materials whose runs all lack oxygen say nothing about oxygen coverage.
    if not spec.y.bands:
        ys = [j for j in ys if any(cells[(i, j)]["observed"] for i in xs)]
    if not spec.x.bands:
        xs = [i for i in xs if any(cells[(i, j)]["observed"] for j in ys)]
    blocks: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for i, j in product(xs, ys):
        blocks.setdefault((_block(spec.x, i), _block(spec.y, j)), []).append((i, j))
    groups: dict[tuple[str, str | None, str | None], dict[str, Any]] = {}
    for (bx, by), members in blocks.items():
        if any(cells[m]["observed"] for m in members):
            continue
        planned = sum(cells[m]["planned"] for m in members)
        status = "planned" if planned else "unplanned"
        gx = None if bx.startswith("bin:") else bx
        gy = None if by.startswith("bin:") else by
        group = groups.setdefault((status, gx, gy), {"cells": [], "planned": 0, "names": []})
        group["cells"] += [[i, j] for i, j in members]
        group["planned"] += planned
        if gx is None:
            group["names"].append(spec.x.bins[members[0][0]].label)
        if gy is None:
            group["names"].append(spec.y.bins[members[0][1]].label)
    out: list[dict[str, Any]] = []
    for (status, gx, gy), group in groups.items():
        parts = [spec.x.bands[gx]] if gx else []
        parts += [spec.y.bands[gy]] if gy else []
        label = " at ".join(parts) if parts else "Untested combinations"
        names = list(dict.fromkeys(group["names"]))
        listed = spec.x if gx is None else spec.y
        every = len(names) > 1 and len(names) == len(xs if gx is None else ys)
        detail = []
        if names:
            detail.append(f"every {listed.label.lower()}" if every else ", ".join(names))
        if group["planned"]:
            n = group["planned"]
            detail.append(f"{n} planned test{'s' if n != 1 else ''}")
        out.append(
            {
                "status": status,
                "label": label[:1].upper() + label[1:],
                "detail": " · ".join(detail),
                "cells": group["cells"],
                "planned": group["planned"],
                "_order": (
                    list(spec.x.bands).index(gx) if gx else 0,
                    list(spec.y.bands).index(gy) if gy else 0,
                ),
            }
        )
    out.sort(key=lambda g: (g["status"] != "planned", g["_order"]))
    for g in out:
        del g["_order"]
    return out


def _view(
    spec: GridSpec,
    placed: list[tuple[int, int, dict[str, Any], dict[str, str]]],
    planned: list[tuple[int, int, int, dict[str, str]]],
    combo: dict[str, str],
) -> dict[str, Any]:
    def match(values: dict[str, str]) -> bool:
        return all(v == ALL or values.get(k) == v for k, v in combo.items())

    cells: dict[tuple[int, int], dict[str, Any]] = {}
    for i, j in product(range(len(spec.x.bins)), range(len(spec.y.bins))):
        cells[(i, j)] = {
            "x": i,
            "y": j,
            "ids": [],
            "planned_ids": [],
            "outcomes": {},
            "reviewed": 0,
        }
    for i, j, record, values in placed:
        if not match(values):
            continue
        cell = cells[(i, j)]
        cell["ids"].append(record["id"])
        cell["reviewed"] += record.get("review_status") == "reviewed"
        outcome = spec.outcome(record)
        if outcome:
            cell["outcomes"][outcome] = cell["outcomes"].get(outcome, 0) + 1
    for i, j, index, values in planned:
        if match(values):
            cells[(i, j)]["planned_ids"].append(index)
    for (i, j), cell in cells.items():
        cell["observed"] = len(cell["ids"])
        cell["planned"] = len(cell["planned_ids"])
        cell["neighbours"] = sum(1 for n in _neighbours(spec, i, j) if cells[n]["ids"])
        cell["class"] = classify(cell["observed"], cell["planned"])
    gaps = _gap_groups(spec, cells)
    observed = [c for c in cells.values() if c["observed"]]
    return {
        "cells": [c for c in cells.values() if c["observed"] or c["planned"]],
        "gaps": gaps,
        "totals": {
            "observed": sum(c["observed"] for c in observed),
            "planned": sum(c["planned"] for c in cells.values()),
            "cells_with_runs": len(observed),
            "cells": len(cells),
        },
    }


def _bin_json(b: Bin) -> dict[str, Any]:
    return {"key": b.key, "label": b.label, "lo": b.lo, "hi": b.hi}


def build_grid(
    spec: GridSpec, records: list[dict[str, Any]], proposed: list[dict[str, Any]]
) -> dict[str, Any]:
    placed: list[tuple[int, int, dict[str, Any], dict[str, str]]] = []
    unplaced: list[str] = []
    for record in records:
        if record.get("family") not in spec.families or not spec.include(record):
            continue
        i, j = spec.x.locate(spec.x.value(record)), spec.y.locate(spec.y.value(record))
        values = {f.key: f.value(record) or "" for f in spec.facets}
        if i is None or j is None:
            unplaced.append(record["id"])
            continue
        placed.append((i, j, record, values))
    planned: list[tuple[int, int, int, dict[str, str]]] = []
    unplaced_planned = 0
    if spec.planned:
        for index, test in enumerate(proposed):
            xv = spec.x.planned_value(test) if spec.x.planned_value else None
            yv = spec.y.planned_value(test) if spec.y.planned_value else None
            i, j = spec.x.locate(xv), spec.y.locate(yv)
            if i is None or j is None:
                unplaced_planned += 1
                continue
            values = {
                f.key: (f.planned_value(test) if f.planned_value else None) or ""
                for f in spec.facets
            }
            planned.append((i, j, index, values))
    # Categorical bins with nothing in them (e.g. an unused "Other" row) are dropped.
    used_x = {i for i, *_ in placed} | {i for i, *_ in planned}
    used_y = {j for _, j, *_ in placed} | {j for _, j, *_ in planned}
    keep_x = [i for i in range(len(spec.x.bins)) if spec.x.ordered or i in used_x]
    keep_y = [j for j in range(len(spec.y.bins)) if spec.y.ordered or j in used_y]
    if len(keep_x) < len(spec.x.bins) or len(keep_y) < len(spec.y.bins):
        mx = {old: new for new, old in enumerate(keep_x)}
        my = {old: new for new, old in enumerate(keep_y)}
        spec = replace(
            spec,
            x=replace(spec.x, bins=[spec.x.bins[i] for i in keep_x]),
            y=replace(spec.y, bins=[spec.y.bins[j] for j in keep_y]),
        )
        placed = [(mx[i], my[j], r, v) for i, j, r, v in placed]
        planned = [(mx[i], my[j], p, v) for i, j, p, v in planned]
    combos = [
        dict(zip([f.key for f in spec.facets], choice, strict=True))
        for choice in product(*[[ALL, *[k for k, _ in f.options]] for f in spec.facets])
    ]
    views = {view_key(c): _view(spec, placed, planned, c) for c in combos}
    notes = list(spec.notes)
    if unplaced:
        notes.append(
            f"{len(unplaced)} run{'s lack' if len(unplaced) != 1 else ' lacks'} a usable value "
            "on one of the axes and "
            f"{'are' if len(unplaced) != 1 else 'is'} left off the grid."
        )
    if unplaced_planned:
        notes.append(
            f"{unplaced_planned} planned tests lack oxygen or pressure and are not in the grid."
        )
    return {
        "key": spec.key,
        "label": spec.label,
        "description": spec.description,
        "x": {
            "key": spec.x.key,
            "label": spec.x.label,
            "unit": spec.x.unit,
            "bins": [_bin_json(b) for b in spec.x.bins],
        },
        "y": {
            "key": spec.y.key,
            "label": spec.y.label,
            "unit": spec.y.unit,
            "bins": [_bin_json(b) for b in spec.y.bins],
        },
        "facets": [
            {
                "key": f.key,
                "label": f.label,
                "options": [{"key": ALL, "label": "All"}]
                + [{"key": k, "label": v} for k, v in f.options],
            }
            for f in spec.facets
        ],
        "has_planned": spec.planned,
        "views": views,
        "unplaced": unplaced,
        "notes": notes,
    }


def view_key(combo: dict[str, str]) -> str:
    return "|".join(f"{k}={v}" for k, v in combo.items()) or ALL


def build_grids(
    records: list[dict[str, Any]], proposed: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [build_grid(spec, records, proposed) for spec in grid_specs()]


THRESHOLDS = {
    "strong": f"{STRONG}+ observed runs",
    "moderate": f"{MODERATE}–{STRONG - 1} observed runs",
    "sparse": "1 observed run",
    "planned": "No runs; planned tests only",
    "gap": "No runs or planned tests",
}
