# BASS-II and Saffire-II CSV run v1: flag review decisions

Status: **decided by Sophie on 11/14/2026. D1–D8 applied; D7's Fig. 5 lookup, A1 audit, G1 and D9 (M5) are still open.** This document is the human-readable decision record for the flags in this run. The machine-readable twin, [bass-saffire-csv-run-v1-flag-decisions.json](bass-saffire-csv-run-v1-flag-decisions.json), lists the exact rows each decision covers and is what `combustion_atlas.review.flag_decisions` applies. A decision applies to every row listed under it unless a row-level override is written in its Notes.

| Item | Value |
|---|---|
| Run | `data/processed/full-runs/nasa-csv-v1` (123 rows, model `gpt-6-luna`) |
| Plan SHA-256 (as recorded by the run) | `7a193eb9be658cf84f9070264301c2e829c765be504b2b255abc6bf9b6f805eb` |
| review-index.json SHA-256 | `5d0eaa2bf978f9eca7e0a12e5dc211f3ddd7bf565bfcefa047aa399edb061e2e` |
| Source PSI-25 | `PSI-25_Experimental table_BASS-II.csv`, SHA-256 `71e792bf6b5fb5ea620c5dd70fbbac05515992e12aefcf5dff47312caa48c042` |
| Source PSI-99 | `PSI-99_Experimental table_SAFFIRE-2.csv`, SHA-256 `3c24390b9ef86f3d1ebaab911a1a3cc95a8759aebf42062371370e6d4b31b8ac` |
| Imported candidates | `data/review/model-candidates/full-csv-review-all-v1.json` (122 of 123 rows; M5 skipped, see D9). Superseded: `data/review/model-candidates-superseded/full-csv-review-v1.json` (flagged + audit rows only) |

**Decision options.** *Accept as mapped*: value and field are right. *Accept, interpretation unresolved*: transcription is faithful but the scientific meaning is genuinely ambiguous; keep it with the caveat and don't block on it. *Correct*: give the right field/value/unit. *Reject*: drop the mapping (the raw source cell stays attached).

## Decision table

| ID | Topic | Rows | Decision | Reviewer notes |
|---|---|---|---|---|
| D1 | BASS material cell with unlabeled dimensions | 3 | Accept as proposed, with a note | |
| D2 | BASS material cell with one unlabeled dimension | 13 (+16 unflagged by pattern) | Correct: no field assigned; dimension kept as an unresolved extra | Also applied to unflagged rows with the same pattern |
| D3 | BASS rod samples with inch dimensions | 34 (+20 unflagged by pattern) | Correct: no PMMA unless named; rod dimension kept as an unresolved extra | Also applied to unflagged rows with the same pattern |
| D4 | BASS material cell with labeled dimensions | 7 | Accept as proposed | |
| D5 | Saffire-II `?-g` column headers (all 4 Saffire rows) | 4 | Accept, interpretation unresolved | |
| D6 | BASS CO readings with marker `OR` | 2 | Accept, interpretation unresolved | |
| D7 | Saffire-II thickness cells | 2 | Accept with note; Fig. 5 pending | Sophie to check Fig. 5 |
| D8 | Row-level: extractable field missing from proposal | 2 | Accept | |
| D9 | M5: material cell gives two thicknesses | 1 | Pending | Not importable until decided |
| A1 | Audit sample: unflagged rows, check cell by cell | 5 | Pending | See A1: T1 shows the D2 problem |
| G1 | Global: BASS instrument/control settings | 119 | Pending | |

Reviewer: **Sophie** · Date: **11/14/2026** (recorded in the JSON spec as `reviewer` and `reviewed_at`)

## Reviewer comments (Sophie, 11/14/2026)

Recorded as given, for the record.

- **General:** "Longterm we want to leave flags, so that when people search the UI and see the raw results, there will be notes saying where things were uncertain, ambiguous, or were assumed based on x." (Implemented as per-value `notes`.)
- **D1:** "It is clear by context that 2cm refers to the width and the mm/micron refers to the thickness. Accept these as proposed, but can retain a note/flag about it."
- **D2:** "Agree it should not be thickness. If none of the material cells with unlabeled dimensions are clear, we can leave this unclear/unresolved/blank, and create a note listing the provided dimension, but saying it is unclear what this corresponds to. Do not force it to be thickness or sibal etc." Later: "please do implement the D2/D3 changes as well" for the unflagged rows with the same pattern.
- **D3:** "Should not be PMMA unnecessarily. Perhaps we should have an 'additional field' catch-all, where unmappable fields are put with a note noting their ambiguity, instead of forcing them into these buckets, when it is clear they cannot all be put." (Implemented as `additional_fields`.)
- **D4:** "Agree with the proposals in this note."
- **D5:** "This is not particularly clear to me, I believe it should be accept, but interpretation unresolved."
- **D6:** "The interpretation of OR as over-range or out of range makes sense, but we should not assume. Leave these flagged as notes, but leave the OR as-is, with note explaining that this likely signifies out of range."
- **D7:** "For 037 it should have a note that this is likely 0.37, that this 0.37 was inferred by us. For the Fig 5 I will look for this." (Open: Sophie to check Fig. 5.)
- **D8:** "Accept D8."
- **Implementation choices made on Sophie's behalf, open to revision:** B13's unmapped `2 cm` and M19's `2 cm 2ide` were assigned as width under the D1/D4 context rule (with *assumed* notes); SIBAL is kept as material where the cell names it.

## D1. BASS material cell with unlabeled dimensions (3 rows)

Cells like `2 cm   0.2 mm PMMA film` give two dimensions without saying which is which. The model reads the first (cm) as **width** and the second (mm/micron) as **thickness**, marked `proposed`. Decide whether that ordering rule is acceptable for all such rows.

| Test | Source cell | material | geometry | width | thickness | unmapped / other | Flags |
|---|---|---|---|---|---|---|---|
| [B11](../../data/processed/full-runs/nasa-csv-v1/row-0001/01.json) | `2 cm   0.2 mm PMMA film` | PMMA *(proposed)* | – | 2.0 cm *(proposed)* | 0.2 mm *(proposed)* | – | width: model_reported_uncertainty<br>width: unverified_width_interpretation |
| [B15](../../data/processed/full-runs/nasa-csv-v1/row-0005/01.json) | `2 cm   0.1 mm PMMA film` | PMMA | – | 2.0 cm | 0.1 mm | – | width: unverified_width_interpretation |
| [M15](../../data/processed/full-runs/nasa-csv-v1/row-0031/01.json) | `2 cm   4 mm 1 sided PMMA slab` | PMMA | slab | 2 cm *(proposed)* | 4 mm *(proposed)* | – | width: model_reported_uncertainty<br>width: unverified_width_interpretation |

**Decision:** Accept as proposed, with a note

**Notes:** Clear from context: the cm value is the width, the mm/micron value the thickness. Values are kept, and each carries an *assumed* note saying the assignment came from context.

## D2. BASS material cell with one unlabeled dimension (13 rows)

Cells like `2 cm SIBAL` or `4 cm spherical section` give a single dimension with no label. The model is **inconsistent** across identical cells: sometimes `thickness`, sometimes `unmapped`, sometimes dropped. A 2 cm *thickness* is implausible for a SIBAL fabric sample, so if it's mapped at all, width (or size/diameter for the spherical section) is more likely. Decide one rule for all identical cells: map to width, keep as an unlabeled dimension, or mark unresolved. Whatever you choose, the `thickness` readings probably shouldn't stand. (Some values also show the unit twice, e.g. `2 cm cm`: the model put the unit in both the value and unit fields; the import should strip one.)

| Test | Source cell | material | geometry | width | thickness | unmapped / other | Flags |
|---|---|---|---|---|---|---|---|
| [T2](../../data/processed/full-runs/nasa-csv-v1/row-0092/01.json) | `2 cm SIBAL` | SIBAL *(proposed)* | – | – | 2.0 cm *(proposed)* | – | thickness: model_reported_uncertainty |
| [T3](../../data/processed/full-runs/nasa-csv-v1/row-0093/01.json) | `4 cm spherical section` | – | spherical | – | – | 4 cm cm [Dimension of spherical section; dimension type not specified] | unmapped: unmapped_source_field |
| [T4](../../data/processed/full-runs/nasa-csv-v1/row-0094/01.json) | `2 cm SIBAL` | SIBAL *(proposed)* | – | – | – | – | material: model_reported_uncertainty |
| [T5](../../data/processed/full-runs/nasa-csv-v1/row-0095/01.json) | `2 cm SIBAL` | SIBAL *(proposed)* | – | – | 2.0 cm *(proposed)* | – | material: model_reported_uncertainty<br>thickness: model_reported_uncertainty |
| [T6](../../data/processed/full-runs/nasa-csv-v1/row-0096/01.json) | `2 cm SIBAL` | SIBAL *(proposed)* | – | – | – | 2 cm cm | unmapped: unmapped_source_field |
| [T7](../../data/processed/full-runs/nasa-csv-v1/row-0097/01.json) | `4 cm spherical section` | – | spherical section | – | – | 4 cm cm | unmapped: unmapped_source_field |
| [T10](../../data/processed/full-runs/nasa-csv-v1/row-0099/01.json) | `2 cm SIBAL` | SIBAL *(proposed)* | – | – | 2.0 cm (mapping_uncertain) *(proposed)* | – | thickness: mapping_uncertain<br>thickness: model_reported_uncertainty |
| [T12](../../data/processed/full-runs/nasa-csv-v1/row-0101/01.json) | `2 cm SIBAL` | SIBAL *(proposed)* | – | – | 2.0 cm *(proposed)* | – | thickness: model_reported_uncertainty |
| [T16](../../data/processed/full-runs/nasa-csv-v1/row-0105/01.json) | `2 cm SIBAL` | SIBAL *(proposed)* | – | – | – | 2 cm cm | unmapped: unmapped_source_field |
| [T24](../../data/processed/full-runs/nasa-csv-v1/row-0113/01.json) | `1 cm SIBAL   top side ign` | SIBAL *(proposed)* | – | – | 1.0 cm *(proposed)* | – | thickness: model_reported_uncertainty |
| [T26](../../data/processed/full-runs/nasa-csv-v1/row-0115/01.json) | `2 cm SIBAL` | SIBAL *(proposed)* | – | – | 2.0 cm *(proposed)* | – | thickness: model_reported_uncertainty |
| [T28a](../../data/processed/full-runs/nasa-csv-v1/row-0117/01.json) | `1 cm SIBAL` | SIBAL *(proposed)* | – | – | – | 1 cm (mapping_uncertain) | unmapped: mapping_uncertain<br>unmapped: model_reported_uncertainty<br>unmapped: unmapped_source_field |
| [T28b](../../data/processed/full-runs/nasa-csv-v1/row-0118/01.json) | `1 cm SIBAL` | SIBAL *(proposed)* | – | – | – | 1 cm | material: model_reported_uncertainty<br>unmapped: unmapped_source_field |

**Decision:** Correct: no field assigned; dimension kept as an unresolved extra

**Notes:** Must not be thickness. The single dimension is unclear, so it is removed from thickness/width and kept under `additional_fields.unlabeled_dimension` with an *unresolved* note giving the stated value and saying it is unclear what it measures. Material (e.g. SIBAL) is kept only because the cell names it. **Also applied by pattern to the 16 unflagged rows with the same kind of cell** (including audit rows T1 and T18); those rows are marked *not individually reviewed*.

## D3. BASS rod samples with inch dimensions (34 rows)

Cells like `1/4" clear rod`. A rod's single dimension is presumably a **diameter**, which the BASS profile has no field for. The model handles it inconsistently: as `width`, as `unmapped`, or not at all. Several of these cells also name no material (`clear rod`); the model leaves material empty rather than assuming PMMA. Decide: (a) diameter handling, (b) whether `clear rod` may be read as PMMA or stays unspecified.

| Test | Source cell | material | geometry | width | thickness | unmapped / other | Flags |
|---|---|---|---|---|---|---|---|
| [O1](../../data/processed/full-runs/nasa-csv-v1/row-0037/01.json) | `1/4" clear rod` | – | rod *(proposed)* | – | – | 1/4" | geometry: model_reported_uncertainty<br>unmapped: unmapped_source_field |
| [O2](../../data/processed/full-runs/nasa-csv-v1/row-0038/01.json) | `1/4" clear rod` | – | rod | – | – | 1/4" | unmapped: model_reported_uncertainty<br>unmapped: unmapped_source_field |
| [O3a](../../data/processed/full-runs/nasa-csv-v1/row-0039/01.json) | `1/4" clear rod` | – | rod *(proposed)* | – | – | 1/4" in | unmapped: model_reported_uncertainty<br>unmapped: unmapped_source_field |
| [O4](../../data/processed/full-runs/nasa-csv-v1/row-0041/01.json) | `3/8"clear rod` | – | rod *(proposed)* | 3/8 in *(proposed)* | – | – | width: model_reported_uncertainty<br>width: unverified_width_interpretation |
| [O5b](../../data/processed/full-runs/nasa-csv-v1/row-0043/01.json) | `1/2" clear PMMA rod` | PMMA | rod | 1/2 in (mapping_uncertain) *(proposed)* | – | – | width: mapping_uncertain<br>width: model_reported_uncertainty<br>width: unverified_width_interpretation |
| [O6](../../data/processed/full-runs/nasa-csv-v1/row-0044/01.json) | `1/4" clear rod` | – | rod *(proposed)* | – | – | – | geometry: model_reported_uncertainty |
| [O7](../../data/processed/full-runs/nasa-csv-v1/row-0045/01.json) | `1/4" clear rod` | – | rod *(proposed)* | – | – | – | geometry: model_reported_uncertainty |
| [O8a](../../data/processed/full-runs/nasa-csv-v1/row-0046/01.json) | `1/4" clear rod` | – | rod *(proposed)* | – | – | – | description: note-keyword |
| [O8b](../../data/processed/full-runs/nasa-csv-v1/row-0047/01.json) | `1/4" clear rod` | – | rod | – | – | 1/4" (mapping_uncertain) | unmapped: mapping_uncertain<br>unmapped: model_reported_uncertainty<br>unmapped: unmapped_source_field |
| [O10](../../data/processed/full-runs/nasa-csv-v1/row-0049/01.json) | `1/4" clear rod` | – | rod *(proposed)* | – | – | – | description: note-keyword |
| [O12](../../data/processed/full-runs/nasa-csv-v1/row-0051/01.json) | `3/8" clear rod` | – | rod *(proposed)* | – | – | – | description: note-keyword<br>geometry: model_reported_uncertainty |
| [O13b](../../data/processed/full-runs/nasa-csv-v1/row-0053/01.json) | `1/2" clear PMMA rod` | PMMA | rod | – | – | 1/2" | unmapped: unmapped_source_field |
| [O14](../../data/processed/full-runs/nasa-csv-v1/row-0054/01.json) | `1/4" black rod` | – | rod | – | – | 1/4" [dimension] | geometry: model_reported_uncertainty<br>unmapped: unmapped_source_field |
| [O15a](../../data/processed/full-runs/nasa-csv-v1/row-0055/01.json) | `3/8" clear rod` | – | rod *(proposed)* | – | – | 3/8" (mapping_uncertain) | unmapped: mapping_uncertain<br>unmapped: model_reported_uncertainty<br>unmapped: unmapped_source_field |
| [O15b](../../data/processed/full-runs/nasa-csv-v1/row-0056/01.json) | `3/8" clear rod` | – | rod *(proposed)* | 3/8 in [rod diameter; mapped to width] *(proposed)* | – | – | description: note-keyword<br>width: unverified_width_interpretation |
| [O16](../../data/processed/full-runs/nasa-csv-v1/row-0057/01.json) | `3/8"clear rod` | – | rod *(proposed)* | – | – | 3/8" | geometry: model_reported_uncertainty<br>unmapped: unmapped_source_field |
| [O20](../../data/processed/full-runs/nasa-csv-v1/row-0061/01.json) | `1/4" clear rod` | – | rod *(proposed)* | – | – | – | description: note-keyword<br>geometry: model_reported_uncertainty |
| [O21](../../data/processed/full-runs/nasa-csv-v1/row-0062/01.json) | `3/8" clear rod` | – | rod | – | – | 3/8" [rod dimension] | unmapped: unmapped_source_field |
| [O22](../../data/processed/full-runs/nasa-csv-v1/row-0063/01.json) | `1/2" clear rod` | – | rod | – | – | 1/2" in | description: note-keyword<br>unmapped: model_reported_uncertainty<br>unmapped: unmapped_source_field |
| [P1](../../data/processed/full-runs/nasa-csv-v1/row-0064/01.json) | `1/4" black rod` | – | rod *(proposed)* | – | – | 1/4" | description: note-keyword<br>unmapped: model_reported_uncertainty<br>unmapped: unmapped_source_field |
| [P2](../../data/processed/full-runs/nasa-csv-v1/row-0065/01.json) | `1/4" black rod` | – | rod *(proposed)* | – | – | 1/4" in | unmapped: unmapped_source_field |
| [P3a](../../data/processed/full-runs/nasa-csv-v1/row-0066/01.json) | `1/4" clear rod` |  (mapping_uncertain) *(proposed)* | rod *(proposed)* | – | – | 1/4" [dimension; likely rod diameter, but no diameter field is available] | material: mapping_uncertain<br>material: model_reported_uncertainty<br>unmapped: unmapped_source_field |
| [P3b](../../data/processed/full-runs/nasa-csv-v1/row-0067/01.json) | `1/4 clear rod` | – | rod | – | – | – | geometry: model_reported_uncertainty |
| [P6](../../data/processed/full-runs/nasa-csv-v1/row-0070/01.json) | `1/4" black rod` | – | rod | – | – | – | description: note-keyword |
| [P8](../../data/processed/full-runs/nasa-csv-v1/row-0071/01.json) | `3/8" black rod` | – | rod *(proposed)* | – | – | 3/8" | description: note-keyword<br>unmapped: model_reported_uncertainty<br>unmapped: unmapped_source_field |
| [P9](../../data/processed/full-runs/nasa-csv-v1/row-0072/01.json) | `0.5" black rod` | – | rod *(proposed)* | 0.5 in *(proposed)* | – | – | description: note-keyword<br>width: model_reported_uncertainty<br>width: unverified_width_interpretation |
| [P13a](../../data/processed/full-runs/nasa-csv-v1/row-0075/01.json) | `0.5" black rod` | – | rod *(proposed)* | 0.5 in [rod diameter; source text: 0.5"] *(proposed)* | – | – | width: model_reported_uncertainty<br>width: unverified_width_interpretation |
| [P13b](../../data/processed/full-runs/nasa-csv-v1/row-0076/01.json) | `0.5" black rod` | – | rod *(proposed)* | 0.5 in *(proposed)* | – | – | description: note-keyword<br>width: model_reported_uncertainty<br>width: unverified_width_interpretation |
| [P16](../../data/processed/full-runs/nasa-csv-v1/row-0079/01.json) | `1/4" black rod` | – | rod | – | – | 1/4" | description: note-keyword<br>unmapped: model_reported_uncertainty<br>unmapped: unmapped_source_field |
| [P17](../../data/processed/full-runs/nasa-csv-v1/row-0080/01.json) | `1/4"  black rod` | – | rod | – | – | 1/4" in | unmapped: unmapped_source_field |
| [P19](../../data/processed/full-runs/nasa-csv-v1/row-0082/01.json) | `1/4" black rod` | – | rod *(proposed)* | – | – | 1/4" | description: note-keyword<br>unmapped: unmapped_source_field |
| [P22a](../../data/processed/full-runs/nasa-csv-v1/row-0086/01.json) | `3/8" black rod` | – | rod *(proposed)* | – | – | 3/8" | description: note-keyword<br>unmapped: unmapped_source_field |
| [P24](../../data/processed/full-runs/nasa-csv-v1/row-0089/01.json) | `3/8" black rod` | – | rod *(proposed)* | – | – | – | geometry: model_reported_uncertainty |
| [P25](../../data/processed/full-runs/nasa-csv-v1/row-0090/01.json) | `3/8" clear rod` | – | rod *(proposed)* | – | – | 3/8" (mapping_uncertain) | description: note-keyword<br>unmapped: mapping_uncertain<br>unmapped: unmapped_source_field |

**Decision:** Correct: no PMMA unless named; rod dimension kept as an unresolved extra

**Notes:** PMMA is not inferred where the cell names no material; `material_description` carries an *unresolved* note saying so. The rod dimension is removed from width/unmapped and kept under `additional_fields.rod_dimension` with a note (probably diameter, not stated). P3b's `1/4` has no inch mark; its note says the unit is not stated. **Also applied by pattern to the 20 unflagged rod rows** (including audit row P21a); those rows are marked *not individually reviewed*.

## D4. BASS material cell with labeled dimensions (7 rows)

Dimensions are labeled (`1 cm wide 200 micron thick PMMA`). Flags here are mostly the model's notes tripping the uncertainty keyword check, or a leftover phrase sent to `unmapped` (e.g. `1 sided`, `slab`, coatings). Usually a quick accept; check the geometry and unmapped columns.

| Test | Source cell | material | geometry | width | thickness | unmapped / other | Flags |
|---|---|---|---|---|---|---|---|
| [B13](../../data/processed/full-runs/nasa-csv-v1/row-0003/01.json) | `2 cm   0.4 mm thick film` | – | film | – | 0.4 mm | 2 cm cm | unmapped: unmapped_source_field |
| [B16](../../data/processed/full-runs/nasa-csv-v1/row-0006/01.json) | `2 cm 100 micron thick PMMA` | PMMA *(proposed)* | – | 2.0 cm [dimension axis not specified in source] *(proposed)* | 100.0 micron | – | width: model_reported_uncertainty<br>width: unverified_width_interpretation |
| [B19](../../data/processed/full-runs/nasa-csv-v1/row-0009/01.json) | `2 cm 100 micron thick PMMA` | PMMA *(proposed)* | – | 2 cm cm *(proposed)* | 100 micron micron | – | width: model_reported_uncertainty<br>width: unverified_width_interpretation |
| [B20](../../data/processed/full-runs/nasa-csv-v1/row-0010/01.json) | `2 cm 100 micron thick PMMA` | PMMA | – | 2.0 cm *(proposed)* | 100.0 micron | – | width: model_reported_uncertainty<br>width: unverified_width_interpretation |
| [M1](../../data/processed/full-runs/nasa-csv-v1/row-0017/01.json) | `1 mm thick PMMA   1 sided   2 cm` | PMMA *(proposed)* | 1 sided *(proposed)* | 2.0 cm *(proposed)* | 1.0 mm *(proposed)* | – | geometry: model_reported_uncertainty<br>width: model_reported_uncertainty<br>width: unverified_width_interpretation |
| [M14](../../data/processed/full-runs/nasa-csv-v1/row-0030/01.json) | `2mm thick PMMA   1 sided   2 cm wide` | PMMA | 1 sided *(proposed)* | 2.0 cm | 2.0 mm | – | geometry: model_reported_uncertainty |
| [M19](../../data/processed/full-runs/nasa-csv-v1/row-0035/01.json) | `4 mm thick   2 cm 2ide PMMA slab` | PMMA | slab | – | 4.0 mm | – | description: note-keyword |

**Decision:** Accept as proposed

**Notes:** Accepted. Where the cm value is unlabeled (B16, B19, B20, M1), the D1 context rule and note apply. Two consistency fixes, applied by the same rule (please confirm): B13 `2 cm   0.4 mm thick film`: the model left `2 cm` unmapped; assigned as width with an *assumed* note. M19 `2 cm 2ide`: the model dropped it; assigned as width with a note that `2ide` is taken as a typo for `wide`.

## D5. Saffire-II `?-g` column headers (all 4 Saffire rows)

The source CSV literally labels two columns `?-g Burn Length` and `?-g Spread Length`; the gravity level isn't stated (other columns say `1-g`). The second column is reported in mm/s, which is a rate, not a length. Decide: (a) what gravity level these columns represent (likely the µg/flight measurement given the separate 1-g columns, but not stated in the CSV), (b) whether `Spread Length` in mm/s should be treated as a spread **rate**. If neither can be confirmed from the source paper, mark *accept, interpretation unresolved*.

| Test | Source column | Source cell | Mapped field | Mapped value | Status | Flags | Model note |
|---|---|---|---|---|---|---|---|
| [SAFFIRE-II-2-3](../../data/processed/full-runs/nasa-csv-v1/row-0120/01.json) | `?-g Burn Length` | `~ 0` | burn_length_unspecified_gravity | 0.0 [~] | direct | ambiguous_source_gravity_header |  |
| [SAFFIRE-II-2-3](../../data/processed/full-runs/nasa-csv-v1/row-0120/01.json) | `?-g Spread Length` | `n/a` | spread_length_unspecified_gravity | n/a (source_marker) | direct | ambiguous_source_gravity_header |  |
| [SAFFIRE-II-2-5](../../data/processed/full-runs/nasa-csv-v1/row-0121/01.json) | `?-g Burn Length` | `29 cm` | burn_length_unspecified_gravity | 29 cm | direct | ambiguous_source_gravity_header | Source column label: "?-g Burn Length". |
| [SAFFIRE-II-2-5](../../data/processed/full-runs/nasa-csv-v1/row-0121/01.json) | `?-g Spread Length` | `2.1 mm/s` | spread_length_unspecified_gravity | 2.1 mm/s (mapping_uncertain) | proposed | mapping_uncertain, ambiguous_source_gravity_header, unit_conflicts_with_field_name | Source column label: "?-g Spread Length"; the reported unit is mm/s, which is a rate unit. |
| [SAFFIRE-II-2-8](../../data/processed/full-runs/nasa-csv-v1/row-0122/01.json) | `?-g Burn Length` | `~ 10 cm (note 3)` | burn_length_unspecified_gravity | 10.0 cm [~] | direct | ambiguous_source_gravity_header | Source text: "~ 10 cm (note 3)". Note 3: "This is the length of fuel with significant visible damage." |
| [SAFFIRE-II-2-8](../../data/processed/full-runs/nasa-csv-v1/row-0122/01.json) | `?-g Spread Length` | `Note 4` | spread_length_unspecified_gravity |  (source_marker) | direct | ambiguous_source_gravity_header, source_marker_mismatch | Source text: "Note 4"; no spread-length value is given. Note 4: "The flames remain anchored at the base of the sample which has a very slow regression rate (0.01 to 0.04 mm/s)". |
| [SAFFIRE-II-2-9](../../data/processed/full-runs/nasa-csv-v1/row-0123/01.json) | `?-g Burn Length` | `~ 10 cm (note 4)` | burn_length_unspecified_gravity | 10.0 cm [~] | direct | ambiguous_source_gravity_header | Source text: "~ 10 cm (note 4)". Note 4: flames remain anchored at the base of the sample, which has a very slow regression rate (0.01 to 0.04 mm/s). |
| [SAFFIRE-II-2-9](../../data/processed/full-runs/nasa-csv-v1/row-0123/01.json) | `?-g Spread Length` | `Note 4` | spread_length_unspecified_gravity |  (source_marker) | direct | ambiguous_source_gravity_header, source_marker_mismatch | Source text: "Note 4"; this cell contains a note reference but no spread-length value. Note 4: flames remain anchored at the base of the sample, which has a very slow regression rate (0.01 to 0.04 mm/s). |

**Decision:** Accept, interpretation unresolved

**Notes:** Values kept. Each `?-g` value has an *ambiguous* note that the header doesn't state the gravity level; the mm/s spread value also notes the rate unit under a length header.

## D6. BASS CO readings with marker `OR`

Some CO cells contain `OR` instead of a number. Its meaning isn't defined in the CSV, but O13b's Final CO cell literally says `over`, which supports reading `OR` as "over range" (sensor saturated). Either way there's no numeric reading. The model kept `OR` as a source marker; the validator flags a mismatch because `OR` isn't in its known-marker list. Decide whether to record `OR` as "over range" or leave it unresolved.

| Test | Source column | Source cell | Mapped field | Mapped value | Status | Flags | Model note |
|---|---|---|---|---|---|---|---|
| [O12](../../data/processed/full-runs/nasa-csv-v1/row-0051/01.json) | `Initial CO (ppm)` | `OR` | initial_co | OR ppm (source_marker) | direct | source_marker_mismatch | Source marker “OR” preserved; meaning unresolved. |
| [O12](../../data/processed/full-runs/nasa-csv-v1/row-0051/01.json) | `Final CO (ppm)` | `OR` | final_co | OR ppm (source_marker) | direct | source_marker_mismatch | Source marker “OR” preserved; meaning unresolved. |
| [O13b](../../data/processed/full-runs/nasa-csv-v1/row-0053/01.json) | `Final CO (ppm)` | `over` | final_co | over ppm | direct | model_reported_uncertainty | Literal source value preserved; the source does not provide a numeric reading. |

**Decision:** Accept, interpretation unresolved

**Notes:** `OR` (and O13b's `over`) kept as written, with an *unresolved* note that it likely means over/out of range but is not defined in the source.

## D7. Saffire-II thickness cells

`037 mm` looks like `0.37 mm` with the decimal dropped (or 0.037?). The other cell says `See Fig. 5`: the thickness exists only in a figure of the source paper, so the CSV has no value. Decide the `037` reading (or leave it unresolved); for `See Fig. 5`, accept as "no value in CSV" unless you want to pull it from the paper.

| Test | Source column | Source cell | Mapped field | Mapped value | Status | Flags | Model note |
|---|---|---|---|---|---|---|---|
| [SAFFIRE-II-2-5](../../data/processed/full-runs/nasa-csv-v1/row-0121/01.json) | `Samle Thickness` | `037 mm` | thickness | 037 mm | direct | ambiguous_leading_zero |  |
| [SAFFIRE-II-2-8](../../data/processed/full-runs/nasa-csv-v1/row-0122/01.json) | `Samle Thickness` | `See Fig. 5` | thickness |  (source_marker) | direct | source_marker_mismatch | Source text: "See Fig. 5". Figure reference; its thickness value is not provided here. |

**Decision:** Accept with note; Fig. 5 pending

**Notes:** `037 mm` kept as written, with an *inferred* note: likely 0.37 mm, and 0.37 is our inference, not a source value. **2-8 `See Fig. 5`: pending, reviewer to look up Fig. 5 in the source paper.** That row stays `needs_research` until then.

## D8. Row-level: extractable field missing from the proposal

For B11 and B15 (`2 cm   0.2 mm PMMA film`), the model proposed width, thickness and material but no geometry, even though the cell says `film`. Separately from the model, the import step runs a simple rule-based parser over the same cell; it found the word `film` and added `geometry = film` itself, flagged `missing_extractable_field:geometry`. So the question is only: keep the importer-added `geometry = film` for these two rows? The word is literally in the cell, so accepting is low-risk.

| Test | Missing field | Source cell | Deterministic value |
|---|---|---|---|
| [B11](../../data/processed/full-runs/nasa-csv-v1/row-0001/01.json) | geometry | `2 cm   0.2 mm PMMA film` | film |
| [B15](../../data/processed/full-runs/nasa-csv-v1/row-0005/01.json) | geometry | `2 cm   0.1 mm PMMA film` | film |

**Decision:** Accept

**Notes:** Geometry `film` is kept for B11 and B15. Each carries a note that the importer's rule-based parser, not the model, supplied it from the literal word `film` in the cell.

## D9. M5: material cell gives two thicknesses (new, found while importing all rows)

M5's cell reads `3 mm thick PMMA   2 sided   2 cm thick`. The model kept both readings as `thickness` (3 mm and 2 cm), with a note that the source contradicts itself. The review format allows one value per field, so the importer refuses this row and lists it as skipped. By the D1 context rule, `2 cm thick` is probably a slip for `2 cm wide`, but that would be our inference.

| Test | Source cell | Model output |
|---|---|---|
| [M5](../../data/processed/full-runs/nasa-csv-v1/row-0021/01.json) | `3 mm thick PMMA   2 sided   2 cm thick` | thickness 3.0 mm; thickness 2.0 cm (both, with a contradiction note) |

**Decision:** Pending

**Notes:** Options: (a) thickness 3 mm, with `2 cm` kept as an additional field noting the source says "thick" but it is likely the width; (b) leave both unresolved.

## A1. Audit sample (unflagged rows)

These rows raised no flags. The risk here is a confident but wrong mapping, so check each value against its source cell. If all are clean, the 57 unflagged rows can be labeled *automatically checked, not reviewed*; if any fail, sample more.

> **Finding while applying D2/D3:** T1 (`2 cm SIBAL`) maps `2 cm` to **thickness** without any flag: exactly what D2 rejects. P21a (`1/4 black rod`) is a D3-type rod. Across the 57 unflagged rows, 16 have the D2 pattern and 20 the D3 pattern. Per Sophie's decision, D2/D3 are now also applied to those rows (all 123 rows were imported for this).

### [F4](../../data/processed/full-runs/nasa-csv-v1/row-0016/01.json) (CSV record 27)

| Source column | Source cell | Mapped field | Mapped value | Status |
|---|---|---|---|---|
| `PI` | `Ferkul` | principal_investigator | Ferkul | direct |
| `Test #` | `F4` | test_id | F4 | direct |
| `Date` | `6/24/2014` | date | 6/24/2014 | direct |
| `GMT` | `175` | gmt | 175 | direct |
| `Sample #` | `39M` | sample_id | 39M | direct |
| `Fuel Sample Material` | `Japan Wax candle` | material | Japan Wax candle | direct |
| `Flow restrictor` | `2` | flow_restrictor | 2 | direct |
| `Fan display` | `see notes` | fan_display | see notes | direct |
| `Air display` | `3 ign` | air_display | 3 ign | direct |
| `Radiometer gain   (1000   250   50   10)` | `250` | radiometer_gain | 250 | direct |
| `Total Frames Shot` | `270` | frames_shot | 270 | direct |
| `Calibrated  initial O2 % by vol` | `17.4` | initial_oxygen | 17.4 % by vol | direct |
| `Calibrated final O2 % by vol` | `17.4` | final_oxygen | 17.4 % by vol | direct |
| `Initial CO2 % by vol` | `0.38` | initial_co2 | 0.38 % by vol | direct |
| `Final CO2 % by vol` | `0.48` | final_co2 | 0.48 % by vol | direct |
| `Initial CO (ppm)` | `22` | initial_co | 22 ppm | direct |
| `Final CO (ppm)` | `56` | final_co | 56 ppm | direct |

**Result:** ☐ all correct · ☐ errors (list): ____

### [M18](../../data/processed/full-runs/nasa-csv-v1/row-0034/01.json) (CSV record 45)

| Source column | Source cell | Mapped field | Mapped value | Status |
|---|---|---|---|---|
| `PI` | `Miller` | principal_investigator | Miller | direct |
| `Test #` | `M18` | test_id | M18 | direct |
| `Date` | `7/15/2014` | date | 7/15/2014 | direct |
| `GMT` | `196` | gmt | 196 | direct |
| `Sample #` | `168m` | sample_id | 168m | direct |
| `Fuel Sample Material` | `2 cm wide PMMA 3 mm thick` | material_description | 2 cm wide PMMA 3 mm thick | direct |
| `Fuel Sample Material` | `2 cm wide PMMA 3 mm thick` | material | PMMA | proposed |
| `Fuel Sample Material` | `2 cm wide PMMA 3 mm thick` | width | 2.0 cm | proposed |
| `Fuel Sample Material` | `2 cm wide PMMA 3 mm thick` | thickness | 3.0 mm | proposed |
| `Flow restrictor` | `2` | flow_restrictor | 2 | direct |
| `Fan display` | `Fan pot 3.5   5 (brief)   3  5   2.2` | fan_display | Fan pot 3.5   5 (brief)   3  5   2.2 | direct |
| `Air display` | `10   15 (brief)   10   8` | air_display | 10   15 (brief)   10   8 | direct |
| `Radiometer gain   (1000   250   50   10)` | `50>250` | radiometer_gain | 50>250 | direct |
| `Total Frames Shot` | `178` | frames_shot | 178.0 | direct |
| `Calibrated  initial O2 % by vol` | `17.9` | initial_oxygen | 17.9 % by vol | direct |
| `Calibrated final O2 % by vol` | `16.8` | final_oxygen | 16.8 % by vol | direct |
| `Initial CO2 % by vol` | `0.32` | initial_co2 | 0.32 % by vol | direct |
| `Final CO2 % by vol` | `1.31` | final_co2 | 1.31 % by vol | direct |
| `Initial CO (ppm)` | `0` | initial_co | 0.0 ppm | direct |
| `Final CO (ppm)` | `335` | final_co | 335.0 ppm | direct |

**Result:** ☐ all correct · ☐ errors (list): ____

### [P21a](../../data/processed/full-runs/nasa-csv-v1/row-0084/01.json) (CSV record 95)

| Source column | Source cell | Mapped field | Mapped value | Status |
|---|---|---|---|---|
| `PI` | `Fernandez-Pello` | principal_investigator | Fernandez-Pello | direct |
| `Test #` | `P21a` | test_id | P21a | direct |
| `Date` | `6/23/2014` | date | 6/23/2014 | direct |
| `GMT` | `174` | gmt | 174 | direct |
| `Sample #` | `196M` | sample_id | 196M | direct |
| `Fuel Sample Material` | `1/4 black rod` | material_description | 1/4 black rod | direct |
| `Flow restrictor` | `2` | flow_restrictor | 2 | direct |
| `Fan display` | `46` | fan_display | 46 | direct |
| `Air display` | `5` | air_display | 5 | direct |
| `Radiometer gain   (1000   250   50   10)` | `250` | radiometer_gain | 250 | direct |
| `Total Frames Shot` | `57` | frames_shot | 57 | direct |
| `Calibrated  initial O2 % by vol` | `16.3` | initial_oxygen | 16.3 % by vol | direct |
| `Calibrated final O2 % by vol` | `16.3` | final_oxygen | 16.3 % by vol | direct |
| `Initial CO2 % by vol` | `0.96` | initial_co2 | 0.96 % by vol | direct |
| `Final CO2 % by vol` | `1` | final_co2 | 1 % by vol | direct |
| `Initial CO (ppm)` | `86` | initial_co | 86 ppm | direct |
| `Final CO (ppm)` | `94` | final_co | 94 ppm | direct |

**Result:** ☐ all correct · ☐ errors (list): ____

### [T1](../../data/processed/full-runs/nasa-csv-v1/row-0091/01.json) (CSV record 102)

| Source column | Source cell | Mapped field | Mapped value | Status |
|---|---|---|---|---|
| `PI` | `T'ien` | principal_investigator | T'ien | direct |
| `Test #` | `T1` | test_id | T1 | direct |
| `Date` | `2/14/2014` | date | 2/14/2014 | direct |
| `GMT` | `45` | gmt | 45 | direct |
| `Sample #` | `128` | sample_id | 128 | direct |
| `Fuel Sample Material` | `2 cm SIBAL` | material_description | 2 cm SIBAL | direct |
| `Fuel Sample Material` | `2 cm SIBAL` | material | SIBAL | proposed |
| `Fuel Sample Material` | `2 cm SIBAL` | thickness | 2 cm | proposed |
| `Flow restrictor` | `2` | flow_restrictor | 2 | direct |
| `Fan display` | `80` | fan_display | 80 | direct |
| `Air display` | `10` | air_display | 10 | direct |
| `Radiometer gain   (1000   250   50   10)` | `50` | radiometer_gain | 50 | direct |
| `Total Frames Shot` | `85` | frames_shot | 85 | direct |
| `Calibrated  initial O2 % by vol` | `18.5` | initial_oxygen | 18.5 % by vol | direct |
| `Calibrated final O2 % by vol` | `18.5` | final_oxygen | 18.5 % by vol | direct |
| `Initial CO2 % by vol` | `0.35` | initial_co2 | 0.35 % by vol | direct |
| `Final CO2 % by vol` | `0.41` | final_co2 | 0.41 % by vol | direct |
| `Initial CO (ppm)` | `0` | initial_co | 0 ppm | direct |
| `Final CO (ppm)` | `40` | final_co | 40 ppm | direct |

**Result:** ☐ all correct · ☐ errors (list): ____

### [T18](../../data/processed/full-runs/nasa-csv-v1/row-0107/01.json) (CSV record 118)

| Source column | Source cell | Mapped field | Mapped value | Status |
|---|---|---|---|---|
| `PI` | `T'ien` | principal_investigator | T'ien | direct |
| `Test #` | `T18` | test_id | T18 | direct |
| `Date` | `6/24/2018` | date | 6/24/2018 | direct |
| `GMT` | `175` | gmt | 175.0 | direct |
| `Sample #` | `141M` | sample_id | 141M | direct |
| `Fuel Sample Material` | `2 cm SIBAL` | material_description | 2 cm SIBAL | direct |
| `Flow restrictor` | `2` | flow_restrictor | 2.0 | direct |
| `Fan display` | `–` | fan_display |  (source_blank) | direct |
| `Air display` | `5  2` | air_display | 5  2 | direct |
| `Radiometer gain   (1000   250   50   10)` | `250` | radiometer_gain | 250.0 | direct |
| `Total Frames Shot` | `49` | frames_shot | 49.0 | direct |
| `Calibrated  initial O2 % by vol` | `17.4` | initial_oxygen | 17.4 % by vol | direct |
| `Calibrated final O2 % by vol` | `17.4` | final_oxygen | 17.4 % by vol | direct |
| `Initial CO2 % by vol` | `0.36` | initial_co2 | 0.36 % by vol | direct |
| `Final CO2 % by vol` | `0.38` | final_co2 | 0.38 % by vol | direct |
| `Initial CO (ppm)` | `2` | initial_co | 2.0 ppm | direct |
| `Final CO (ppm)` | `22` | final_co | 22.0 ppm | direct |

**Result:** ☐ all correct · ☐ errors (list): ____

## G1. Global caveat: BASS instrument and control settings

All 119 BASS rows carry `instrument_settings_require_interpretation`. Columns such as fan display, flow restrictor and radiometer gain are kept as raw settings, not converted to physical quantities. Confirm this stays a global caveat rather than a per-row review item.

**Decision:** ☐ keep as global caveat · ☐ other: ____


## Applying these decisions

```bash
.venv/Scripts/python.exe -m combustion_atlas.review.flag_decisions --spec docs/review_decisions/bass-saffire-csv-run-v1-flag-decisions.json --output data/processed/reviewed-evidence-csv-run-v1.json --decisions-output data/processed/reviewed-decisions-csv-run-v1.json
```

The command checks the candidate file, review index and every model result against their recorded SHA-256 hashes. It then writes reviewed evidence in the existing `reviewed-evidence-v1` format, with the original candidate kept unchanged beside the reviewed one. Every value can carry `notes` (`kind`: assumed, inferred, ambiguous, unresolved, pending or model). Source content with no faithful field goes to `additional_fields` with a note instead of being forced into a bucket.

Result: **97 records.**

- 61 flagged rows reviewed: 11 accepted, 49 corrected, 1 `needs_research` (Saffire 2-8, Fig. 5).
- 36 unflagged rows with D2/D3 changes applied by pattern: marked *not individually reviewed* (`human_review_status: unreviewed`).

Not in the output: 25 unflagged rows with no applicable decision (still plain unreviewed candidates, including audit rows F4 and M18 pending A1), and M5 (D9).
