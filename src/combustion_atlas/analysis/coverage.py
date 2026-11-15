"""Experiment coverage from PSI experiment tables (unreviewed candidates).

Each source table gets an explicit, reviewable column map onto the contributor's
canonical field vocabulary (`ingestion.mapping_contract.CanonicalField`). Raw cells
are always kept; a value becomes numeric only when the whole cell is a plain number
(`normalization.extractor._number`), so ranges, bounds and approximations stay as
text. Gaps are empty regions *in this collection*, never claims that nothing was
studied.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from combustion_atlas.ingestion.models import RawRow
from combustion_atlas.ingestion.table_parser import read_csv_losslessly
from combustion_atlas.normalization.extractor import _number, extract_bass_row

# Display metadata for fields that can be plotted or predicted.
FIELDS: dict[str, dict[str, str]] = {
    "oxygen_pct": {"label": "Oxygen", "unit": "% vol"},
    "flow_cm_s": {"label": "Flow velocity", "unit": "cm/s"},
    "pressure_kpa": {"label": "Pressure", "unit": "kPa"},
    "thickness_mm": {"label": "Sample thickness", "unit": "mm"},
    "droplet_diameter_mm": {"label": "Initial droplet diameter", "unit": "mm"},
    "helium_pct": {"label": "Helium in ambient", "unit": "% mole"},
}
OUTCOMES: dict[str, dict[str, str]] = {
    "extinction_diameter_mm": {"label": "Flame extinction diameter", "unit": "mm"},
    "burn_time_s": {"label": "Burn time", "unit": "s"},
    # FLEX prints "Burning rate; mm"; the physical unit is unverified (likely mm²/s).
    "burning_rate_printed": {"label": "Burning rate (unit as printed)", "unit": "mm (as printed)"},
    "spread_rate_1g_mm_s": {"label": "1-g flame spread rate", "unit": "mm/s"},
}


@dataclass
class Column:
    key: str  # FIELDS/OUTCOMES key, or "material", "geometry", "test_id", "gravity"
    scale: float = 1.0  # source unit -> display unit (e.g. 10 for cm -> mm)
    suffix: str | None = None  # unit printed inside cells, e.g. "cm/s" in "20 cm/s"


@dataclass
class TableMap:
    accession: str
    family: str
    pattern: str  # glob under data/raw/psi/<accession>/
    columns: dict[str, Column] = field(default_factory=dict)  # exact source header
    gravity: str | None = "microgravity"
    notes: list[str] = field(default_factory=list)
    encoding: str = "utf-8-sig"
    geometry: str | None = None
    hook: Callable[[RawRow, dict[str, Any], str, str], None] | None = None


def _bass_ii(row: RawRow, record: dict[str, Any], source_url: str, sha: str) -> None:
    """Reuse the established BASS-II parser for material, geometry and thickness."""
    try:
        parsed = extract_bass_row(
            row, investigation_id="PSI-25", source_url=source_url, source_sha256=sha
        )
    except ValueError:
        return
    record["material"] = parsed.conditions.material or parsed.conditions.material_original
    record["geometry"] = parsed.conditions.geometry
    thickness = parsed.conditions.dimensions.get("thickness_um")
    if thickness is not None and thickness.value is not None:
        record["thickness_mm"] = thickness.value / 1000


PSI = "https://psi.nasa.gov/physci/repo/data/investigations/{}"

# Explicit per-table maps; headers match after whitespace collapse and lowercasing.
# Edit here (and in tests) when a reviewer confirms or corrects a column meaning.
TABLE_MAPS: list[TableMap] = [
    TableMap(
        "PSI-69",
        "FLEX",
        "Experimental_table/*.csv",
        encoding="cp1252",
        geometry="droplet",
        columns={
            "FLEX Identifier": Column("test_id"),
            "Fuel": Column("material"),
            "Ambient pressure; mmHg": Column("pressure_kpa", scale=0.1333224),
            "O initial ambient composition; mole fraction": Column("oxygen_pct", scale=100),
            "He initial ambient composition; mole fraction": Column("helium_pct", scale=100),
            "Droplet initial diameter; mm": Column("droplet_diameter_mm"),
            "Visible flame extinction diameter; mm": Column("extinction_diameter_mm"),
            "Burning rate; mm": Column("burning_rate_printed"),
            "Burn time; s": Column("burn_time_s"),
        },
        notes=[
            "FLEX headers print 'O', 'N', 'CO' and 'He' without subscripts; 'O' is read as O₂.",
            "FLEX 'Burning rate; mm' is shown with its printed unit; the physical unit is "
            "unverified.",
            "FLEX diluent CO/CO₂ fraction is not used as a model feature.",
        ],
    ),
    TableMap(
        "PSI-25",
        "BASS-II",
        "Experimental_table/*.csv",
        hook=_bass_ii,
        columns={
            "Test #": Column("test_id"),
            "Calibrated initial O2 % by vol": Column("oxygen_pct"),
        },
        notes=[
            "BASS-II flow is recorded as fan/air display settings without a documented "
            "calibration, so BASS-II runs have no flow velocity here.",
        ],
    ),
    TableMap(
        "PSI-26",
        "BASS",
        "Experimental_table/*.csv",
        columns={"Test #": Column("test_id"), "Fuel Sample Material": Column("material")},
        notes=["The BASS table lists materials only; its runs have no plotted conditions."],
    ),
    TableMap(
        "PSI-98",
        "Saffire",
        "Experimental_table/*.csv",
        columns={
            "Sample Number": Column("test_id"),
            "Material": Column("material"),
            "Sample Thickness (cm)": Column("thickness_mm", scale=10),
            "Air Flow (cm/s)": Column("flow_cm_s"),
            "Percent O2": Column("oxygen_pct"),
            "Burn Time (s)": Column("burn_time_s"),
        },
    ),
    TableMap(
        "PSI-99",
        "Saffire",
        "Experimental_table/*.csv",
        columns={
            "Sample Number": Column("test_id"),
            "Material": Column("material"),
            "Samle Thickness": Column("thickness_mm", suffix="mm"),
            "Air Flow (cm/s)": Column("flow_cm_s", suffix="cm/s"),
            "Percent O2 (Note 1)": Column("oxygen_pct"),
            "Burn Time (s)": Column("burn_time_s", suffix="s"),
            "1-g Spread Rate": Column("spread_rate_1g_mm_s", suffix="mm/s"),
        },
        notes=["Saffire oxygen values are mostly approximate ('~ 21.5') and stay as text."],
    ),
    TableMap(
        "PSI-100",
        "Saffire",
        "Experimental_table/*.csv",
        columns={
            "Sample Number": Column("test_id"),
            "Material": Column("material"),
            "Sample Thickness": Column("thickness_mm", scale=10, suffix="cm"),
            "Air Flow": Column("flow_cm_s", suffix="cm/s"),
        },
    ),
    TableMap(
        "PSI-102",
        "SAME",
        "Experimental_table/*.csv",
        columns={
            "Sample #": Column("test_id"),
            "Sample Material": Column("material"),
            "Air Flow (cm/s)": Column("flow_cm_s"),
        },
        notes=["SAME heats materials to produce smoke; its runs are not flames."],
    ),
]
# Current scope (Sophie, 2026-11-14): BASS, FLEX and Saffire. SAME stays off.
ACTIVE_ACCESSIONS = {"PSI-25", "PSI-26", "PSI-69", "PSI-98", "PSI-99", "PSI-100"}

EXCLUDED = {
    "PSI-68": "The FLEX-2 table is a test matrix (lists and ranges), not individual runs.",
}


def _norm(header: str) -> str:
    return " ".join(header.split()).lower()


def _families() -> dict[str, list[str]]:
    families: dict[str, list[str]] = {}
    for table in TABLE_MAPS:
        if table.accession in ACTIVE_ACCESSIONS:
            families.setdefault(table.family, []).append(table.accession)
    return families


def load_records(raw_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for table in TABLE_MAPS:
        if table.accession not in ACTIVE_ACCESSIONS:
            continue
        for path in sorted((raw_root / table.accession).glob(table.pattern)):
            parsed = read_csv_losslessly(path, encoding=table.encoding)
            lookup = {_norm(h): h for h in parsed.columns}
            mapped = {
                lookup[_norm(source)]: column
                for source, column in table.columns.items()
                if _norm(source) in lookup
            }
            digest = parsed.sha256
            for row in parsed.rows:
                cells = row.cells
                record: dict[str, Any] = {
                    "investigation_id": table.accession,
                    "family": table.family,
                    "test_id": None,
                    "material": None,
                    "geometry": table.geometry,
                    "gravity": table.gravity,
                    "outcomes": {},
                    "review_status": "unreviewed",
                    "source": {
                        "file": path.name,
                        "record": row.record_number,
                        "sha256": digest,
                    },
                    "raw": {k: v for k, v in cells.items() if v not in (None, "")},
                }
                for key in FIELDS:
                    record[key] = None
                for header, column in mapped.items():
                    raw = (cells.get(header) or "").strip()
                    if column.key in {"test_id", "material", "geometry", "gravity"}:
                        record[column.key] = raw or record[column.key]
                        continue
                    text = raw
                    if column.suffix and text.endswith(column.suffix):
                        text = text[: -len(column.suffix)].strip()
                    number = _number(text)
                    value = None if number is None else number * column.scale
                    if column.key in FIELDS:
                        record[column.key] = value
                    elif column.key in OUTCOMES:
                        record["outcomes"][column.key] = {
                            "value": value,
                            "raw": raw,
                            "unit": OUTCOMES[column.key]["unit"],
                        }
                if table.hook is not None:
                    table.hook(row, record, PSI.format(table.accession), digest)
                record["id"] = f"{table.accession}:{record['source']['record']}"
                records.append(record)
    return records


def find_gaps(
    records: list[dict[str, Any]], x: str, y: str, *, bins: int = 6, limit: int = 4
) -> list[dict[str, Any]]:
    """Empty grid cells surrounded by data on at least three sides (interior holes)."""
    points = [(r[x], r[y]) for r in records if r.get(x) is not None and r.get(y) is not None]
    if len(points) < 12:
        return []
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if x1 <= x0 or y1 <= y0:
        return []
    wx, wy = (x1 - x0) / bins, (y1 - y0) / bins
    filled = {
        (min(int((px - x0) / wx), bins - 1), min(int((py - y0) / wy), bins - 1))
        for px, py in points
    }
    gaps: list[dict[str, Any]] = []
    for i in range(bins):
        for j in range(bins):
            if (i, j) in filled:
                continue
            sides = sum(
                any((a, j) in filled for a in range(0, i))
                if d == "left"
                else any((a, j) in filled for a in range(i + 1, bins))
                if d == "right"
                else any((i, b) in filled for b in range(0, j))
                if d == "below"
                else any((i, b) in filled for b in range(j + 1, bins))
                for d in ("left", "right", "below", "above")
            )
            if sides >= 3:
                gaps.append(
                    {
                        "x_field": x,
                        "y_field": y,
                        "x_range": [round(x0 + i * wx, 3), round(x0 + (i + 1) * wx, 3)],
                        "y_range": [round(y0 + j * wy, 3), round(y0 + (j + 1) * wy, 3)],
                        "sides": sides,
                    }
                )
    gaps.sort(key=lambda g: -g["sides"])
    for gap in gaps:
        fx, fy = FIELDS[x], FIELDS[y]
        gap["note"] = (
            f"No runs in this collection with {fx['label'].lower()} "
            f"{gap['x_range'][0]:g}–{gap['x_range'][1]:g} {fx['unit']} and "
            f"{fy['label'].lower()} {gap['y_range'][0]:g}–{gap['y_range'][1]:g} {fy['unit']}."
        )
        del gap["sides"]
    return gaps[:limit]


def apply_reviewed(records: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    """Reviewed evidence supersedes table-parsed values for the same run identity."""
    from .evidence_bridge import coverage_overrides

    overrides, report = coverage_overrides(root)
    # Reviewed IDs may carry an investigation prefix the table does not ("SAFFIRE-II-2-8").
    prefixes = {"PSI-98": "SAFFIRE-I-", "PSI-99": "SAFFIRE-II-", "PSI-100": "SAFFIRE-III-"}
    by_id: dict[tuple[str, str], dict[str, Any]] = {}
    for r in records:
        by_id[(r["investigation_id"], str(r["test_id"]))] = r
        prefix = prefixes.get(r["investigation_id"])
        if prefix:
            by_id[(r["investigation_id"], prefix + str(r["test_id"]))] = r
    applied = 0
    for item in overrides:
        target = by_id.get((item["investigation_id"], str(item["test_id"])))
        if target is None:
            continue  # reviewed run without a parsed table row: reported, not invented
        for key, value in item["fields"].items():
            target[key] = value
        for key, outcome in item["outcomes"].items():
            target["outcomes"][key] = {**outcome, "unit": OUTCOMES.get(key, {}).get("unit")}
        target["review_status"] = "reviewed"
        target["review_action"] = item["review_action"]
        applied += 1
    report["applied_to_runs"] = applied
    return report


def coverage_payload(workspace: Any) -> dict[str, Any]:
    raw_root = Path(workspace.data) / "raw/psi"
    records = load_records(raw_root)
    bridge = apply_reviewed(records, Path(workspace.data).parent)
    fields: list[dict[str, Any]] = [
        {
            "key": key,
            "label": meta["label"],
            "unit": meta["unit"],
            "count": sum(r.get(key) is not None for r in records),
        }
        for key, meta in FIELDS.items()
    ]
    plottable: list[str] = [str(f["key"]) for f in fields if int(f["count"]) >= 12]
    gaps = [
        gap
        for i, x in enumerate(plottable)
        for y in plottable[i + 1 :]
        for gap in find_gaps(records, x, y)
    ]
    families = [
        {
            "key": re.sub(r"\W+", "-", name.lower()).strip("-"),
            "label": name,
            "investigation_ids": ids,
            "count": sum(r["family"] == name for r in records),
        }
        for name, ids in _families().items()
    ]
    notes = [
        "Runs are parsed from PSI experiment tables and have not been reviewed.",
        "Only cells that are plain numbers are plotted; ranges and qualified values stay "
        "as source text.",
        "Gaps mean no runs in this collection, not that the conditions were never studied.",
        (
            f"{bridge['applied_to_runs']} runs use reviewed table evidence; "
            f"{len(bridge['rejected'])} reviewed records rejected, "
            f"{len(bridge['unconverted'])} values kept as text."
            if bridge["accepted"]
            else "Reviewed table evidence is not available on this server yet."
        ),
        *dict.fromkeys(
            note
            for table in TABLE_MAPS
            if table.accession in ACTIVE_ACCESSIONS
            for note in table.notes
        ),
    ]
    from .evidence_bridge import proposed_tests

    # Proposed (planned) tests: a separate layer, never runs and never used for gaps.
    proposed = proposed_tests(Path(workspace.data).parent)
    if proposed:
        notes.append(
            f"{len(proposed)} proposed FLEX tests (EIRD test matrices) are shown as a separate "
            "layer: planned conditions that were not run as listed, with no results. They do "
            "not count toward gaps. Pressure is converted from atm and mole fractions to %."
        )
    return {
        "records": records,
        "fields": fields,
        "families": families,
        "gaps": gaps,
        "notes": notes,
        "proposed": proposed,
    }
