# Evidence integrity workflow

CSV ingestion rejects blank or duplicate normalized headers and rows with a
different number of cells. Source strings and record positions remain intact.
Normalization accepts complete finite scalar numbers, including scientific
notation. Ranges, approximations, bounds, unsupported numeric formats and
ambiguous leading-zero literals are preserved as source text and routed to review.
Explicit source markers and source blanks have distinct qualifiers; absent fields
remain absent. No meaning is inferred for a source marker.

Thickness and width are extracted independently when the material description
explicitly states them. A material or geometry name is populated only when
explicitly present. Instrument settings remain separate from physical variables.
Negative ppm readings and unparsed qualified values remain visible for review.

New draft notes include a candidate fingerprint. The UI identifies whether a
fingerprint matches the displayed candidate, is stale, or is absent. Existing
notes are preserved unchanged. `data/review/review-bindings.json` records a
retrospective association of those notes with candidate and source hashes; it
does not prove an original fingerprint or constitute adjudication. Confirm the
associations and evidence before converting any drafts into decisions.

The review CLI requires unique decisions, a nonblank reviewer and rationale,
timezone-aware review time, supporting references, and a matching candidate
fingerprint. Corrections retain raw cells, identity and source provenance; their
measurements must cite matching source cells. Validation runs again after a
correction. Human acceptance does not replace deterministic validation status or
erase flags. Output paths must be unused and distinct from the inputs; approved
search replays the decision file against its candidate batch before loading it.

The regression tests include source-shaped cases from the review: independently
extractable dimensions, missing final gas measurements, and a negative CO reading
that must be preserved and flagged. The generated B1–B5 check at
`data/review/design-audit/verified-bass.json` is a separate diagnostic candidate
batch, not a replacement for reviewed candidates or a gold fixture.

Remaining work before a broad LLM run includes explicit representation and
evaluation of ranges and qualitative outcomes, atomic multi-file review exports,
additional review-bound fixtures, and a bounded model-assisted pilot. The current
parser quarantines qualified numeric forms rather than interpreting them.
