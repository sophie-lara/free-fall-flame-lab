from types import SimpleNamespace

from combustion_atlas.ingestion.llm_handoff import SourceBatch, SourceCellRef
from combustion_atlas.ingestion.mapping_contract import (
    MappedField,
    MappedRow,
    mapping_request,
    propose_mapping,
    validate_mapping,
)
from combustion_atlas.ingestion.pilot_mapping import FLEX_SHA


def flex_source() -> SourceBatch:
    return SourceBatch(cells=[SourceCellRef(source_sha256=FLEX_SHA, filename="source.pdf",
        kind="pdf_table", physical_page=76, artifact_id="FLEX-table-13-capture", table_row=0,
        table_column=0, source_label="k (mm²/s)", text="0.55", state="present", unit="mm²/s")])


def mapped_field(**changes) -> MappedField:
    data = {"canonical_field": "burning_rate_constant", "source_indexes": [0], "value": 0.55,
            "unit": "mm²/s", "qualifier": None, "missingness": "reported",
            "mapping_status": "proposed", "note": None}
    data.update(changes)
    return MappedField.model_validate(data)


def test_controlled_profile_and_source_evidence() -> None:
    source = flex_source()
    row = MappedRow(schema_version="mapping-proposal-v1", profile="flex_table_13",
                    fields=[mapped_field()])
    assert not validate_mapping(row, "flex_table_13", source)
    row.fields = [mapped_field(mapping_status="direct", source_indexes=[9])]
    assert "fields[0]:invalid_source_reference" in validate_mapping(row, "flex_table_13", source)
    row.fields = [mapped_field(mapping_status="direct")]
    assert "fields[0]:flex_mapping_must_remain_proposed" in validate_mapping(
        row, "flex_table_13", source)
    row.fields = [mapped_field(canonical_field="camera_1")]
    assert "fields[0]:field_outside_profile" in validate_mapping(row, "flex_table_13", source)


def test_source_marker_cannot_become_a_measurement() -> None:
    source = SourceBatch(cells=[SourceCellRef(source_sha256="a" * 64, filename="a.csv",
        kind="csv", csv_record=2, csv_column="x", text="n/a", state="present")])
    field = mapped_field(canonical_field="camera_1", missingness="source_marker", value=1.0)
    row = MappedRow(schema_version="mapping-proposal-v1", profile="saffire_ii", fields=[field])
    assert "fields[0]:unsupported_value_for_missing_source" in validate_mapping(
        row, "saffire_ii", source)
    field.value = "n/a"
    assert not validate_mapping(row, "saffire_ii", source)


def test_provider_interface_uses_schema_and_does_not_send_review_notes() -> None:
    source = flex_source()
    row = MappedRow(schema_version="mapping-proposal-v1", profile="flex_table_13",
                    fields=[mapped_field()])
    usage = SimpleNamespace(model_dump=lambda **_: {"input_tokens": 1, "output_tokens": 1})
    response = SimpleNamespace(output_parsed=row, usage=usage, model="fake", id="fake")
    calls = []
    def parse(**kwargs):
        calls.append(kwargs)
        return response
    result = propose_mapping(SimpleNamespace(responses=SimpleNamespace(parse=parse)),
                             "fake", "flex_table_13", source)
    assert calls[0]["text_format"] is MappedRow
    assert "review_history" not in calls[0]["input"]
    assert result["validation_issues"] == []
    assert result["status"] == "unreviewed"
    assert "unmapped" in mapping_request("flex_table_13", source)["allowed_fields"]
