"""Human-readable mapping report with explicit review tasks."""

from __future__ import annotations

from combustion_atlas.artifacts import CandidateBatch


def render_mapping_report(batch: CandidateBatch) -> str:
    lines = [
        f"# {batch.source.investigation_id} candidate mapping review",
        "",
        (
            "This report is a review queue, not an acceptance record. "
            "Check every candidate against the NASA source."
        ),
        "",
        "## Source identity",
        "",
        f"- Source: {batch.source.source_url}",
        f"- Local file: `{batch.source.local_path}`",
        f"- SHA-256: `{batch.source.sha256}`",
        f"- Generated: {batch.generated_at.isoformat()}",
        "",
        "## Batch checklist",
        "",
        "- [ ] Confirm investigation, test, and sample identifiers.",
        "- [ ] Compare every normalized numeric value with its raw cell.",
        "- [ ] Confirm original values and units are preserved.",
        "- [ ] Confirm condition, outcome, instrument, and metadata classifications.",
        "- [ ] Confirm missing values remain null.",
        "- [ ] Confirm source URL, checksum, CSV record, and column provenance.",
        "- [ ] Record accept, correct, needs_research, or reject decisions separately.",
        "",
        "## Field mapping inventory",
        "",
        "| Source field | Category | Canonical field | Review | Note |",
        "| --- | --- | --- | --- | --- |",
    ]
    for decision in batch.mapping_decisions:
        lines.append(
            "| "
            + " | ".join(
                [
                    decision.source_field.replace("|", "\\|"),
                    decision.category,
                    decision.canonical_field or "-",
                    "required" if decision.requires_review else "-",
                    (decision.note or "-").replace("|", "\\|"),
                ]
            )
            + " |"
        )
    for record in batch.records:
        lines.extend(
            [
                "",
                f"## Test {record.test_id}",
                "",
                f"- [ ] Verify sample ID `{record.sample_id or 'null'}`.",
                f"- [ ] Verify material text `{record.conditions.material_original or 'null'}`.",
                f"- [ ] Review status `{record.validation_status}` and messages: "
                + ("; ".join(record.validation_messages) or "none"),
                "- [ ] Check all instrument settings remain uncalibrated metadata.",
                "- [ ] Add rationale and NASA evidence to the decision file.",
            ]
        )
    return "\n".join(lines) + "\n"
