from combustion_atlas.ingestion.llm_handoff import (
    FieldProposal,
    Proposal,
    SourceBatch,
    SourceCellRef,
    check_proposal,
)
from combustion_atlas.ingestion.pilot_mapping import (
    BASS_SHA,
    FLEX_SHA,
    SAFFIRE_SHA,
    coverage_issues,
    flex_mapping,
    reviewed_source_issues,
)


def test_exact_source_marker_does_not_create_fabrication_flag() -> None:
    cell = SourceCellRef(
        source_sha256=BASS_SHA,
        filename="source.csv",
        kind="csv",
        csv_record=2,
        csv_column="value",
        text="n/a",
        state="present",
    )
    batch = SourceBatch(cells=[cell])
    field = FieldProposal(
        field="value",
        value="n/a",
        unit=None,
        qualifier=None,
        cell_indexes=[0],
        review_reason=None,
        missingness="source_marker",
    )
    proposal = Proposal(investigation_id="i", test_id="t", fields=[field])
    assert not check_proposal(batch, proposal)
    field.value = 5.0
    assert "source_missing_marker" in {i.code for i in check_proposal(batch, proposal)}


def test_flex_mapping_is_shared_but_remains_proposed() -> None:
    for row in range(3):
        cells = [
            SourceCellRef(
                source_sha256=FLEX_SHA,
                filename="source.pdf",
                kind="pdf_table",
                artifact_id="FLEX-table-13-capture",
                physical_page=76,
                table_row=row,
                table_column=col,
                source_label=label,
                text=value,
                state="present",
                unit=unit,
            )
            for col, (label, value, unit) in enumerate(
                [("d (mm)", "2.02", "mm"), ("k (mm²/s)", "0.56", "mm²/s")]
            )
        ]
        mapped, issues = flex_mapping(
            SourceBatch(cells=cells), {"investigation_id": "PSI-69", "source_sha256": FLEX_SHA}
        )
        assert [m["canonical_field"] for m in mapped] == [
            "droplet_diameter",
            "burning_rate_constant",
        ]
        assert [m["mapping_status"] for m in mapped] == ["proposed", "proposed"]
        assert all(i.code == "unverified_field_mapping" for i in issues)
    assert not flex_mapping(
        SourceBatch(cells=cells), {"investigation_id": "PSI-69", "source_sha256": "a" * 64}
    )[0]


def test_reviewed_ambiguity_remains_tied_to_source() -> None:
    for sha, test, column, value in [
        (BASS_SHA, "B2", "Calibrated final O2 % by vol", "1.6"),
        (SAFFIRE_SHA, "SAFFIRE-II-2-4", "Samle Thickness", "037 mm"),
    ]:
        cell = SourceCellRef(
            source_sha256=sha,
            filename="source.csv",
            kind="csv",
            csv_record=2,
            csv_column=column,
            text=value,
            state="present",
        )
        issues = reviewed_source_issues(
            SourceBatch(cells=[cell]), {"source_sha256": sha, "test_id": test}
        )
        assert issues[0].code == "reviewed_source_ambiguity"
        assert issues[0].source_cells[0].text == value


def test_coverage_flags_unmapped_cells_but_not_verified_identity() -> None:
    cells = [
        SourceCellRef(
            source_sha256=BASS_SHA,
            filename="source.csv",
            kind="csv",
            csv_record=2,
            csv_column=column,
            text=value,
            state="present",
        )
        for column, value in [("Test #", "B2"), ("value", "12")]
    ]
    issues = coverage_issues(
        SourceBatch(cells=cells),
        Proposal(investigation_id="PSI-25", test_id="B2", fields=[]),
        {"test_id": "B2"},
    )
    assert [(issue.code, issue.field) for issue in issues] == [("unmapped_source_cell", "value")]
