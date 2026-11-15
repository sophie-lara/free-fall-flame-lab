# FLEX EIRD tables v1: extraction review record

Source: `PSI-69_Engineering Documents_FLEX_EIRD_v4.pdf`, SHA-256
`be236c283ffd597bb79a4715fd4b24d296b2b93de1144c676c119b52a3a3ebe9`.
Machine-readable twin: [flex-eird-tables-v1-review.json](flex-eird-tables-v1-review.json).

Reviewer: **Sophie** · Date: **11/14/2026**

| Table | Extraction run | Status | Notes |
|---|---|---|---|
| 1 | `flex-pdf-remaining-v1` | **Excluded** | Reduced Damköhler number formulas set out as a table; not data. |
| 2 | `flex-pdf-remaining-v1` | **Checked** | Background data (agent MEC values). |
| 6, 7, 9, 10, 11, 12 | `flex-pdf-remaining-v1` | **Spot-checked** (not line by line) | Numeric rows verified automatically against the text layer; headers and condition rows only spot-checked. |
| 8 | `flex-pdf-table8-v1` | **Checked**: table, headers and entries correct | Held-out table. |
| 13 | `flex-pdf-remaining-v1` | Regression only | Used during development. |
| 14 | `flex-pdf-remaining-v1` | **Checked**, with symbol definitions | See below. |

## Reviewer comments

- **Table 2 and promotion:** "I checked table 2, it looks good. I want to move all of the table results into reviewed status. Use the definitions we pulled from table 14 context." All FLEX table results (Tables 2, 6–12, 14) are therefore promoted to reviewed status; Tables 6, 7 and 9–12 keep their spot-check note.

- **Tables 6, 7, 9–12:** "I am doing quick spot checks of 6, 7, 9–12, not enough time for a full line by line. Let's proceed with mapping."

- **Table 1:** "I no longer want to include table 1. It is not really relevant, could it just as well be formulas in-text but they just happen to be in a table."
- **Table 14:** "beta is Soret's effect. phi is multicomponent diffusion. DIO is binary diffusion coefficient of O2 in diluent, DO is O2 diffusion coefficient, LeO is oxygen Lewis number. The subscript is fine to write out like this I think, like LeO."

## Note applied to all test-matrix records (Tables 6–12)

**N1, preliminary test matrices.** EIRD physical page 45 states: "The following test matrices, then are designed to allow the engineering team to adequately plan for the experiment and do not represent the final test matrix. These test matrices provide for an envelope in which all of the actual tests will be conducted."

Page 45 is only inside Table 6's page window, but the statement covers every matrix. Sophie approved attaching it to all 290 records from Tables 6–12 ("Yes, add the note").

## Table 14 symbol definitions (reviewer-supplied)

| Symbol (as transcribed) | Meaning |
|---|---|
| β | Soret transport (Soret effect) factor |
| φ | multicomponent diffusion factor |
| D_IO | binary diffusion coefficient of O₂ in the diluent |
| D_O | effective O₂ diffusion coefficient (D_O = β φ D_IO, EIRD eq. 8) |
| Le_O | oxygen Lewis number (columns given for D_IO and D_O) |

The extraction flagged β and φ as "not defined on the supplied pages". That flag was
overstated: context page 79 links β to Soret effects and φ to multicomponent diffusion.
The formal definitions (eq. 8, shown by the reviewer) are outside the supplied pages.
These definitions are attached to Table 14 records as reviewer notes.

**Subscript convention:** writing subscripts inline (`LeO`, `DIO`, `DO`, or with an
underscore as transcribed) is acceptable. The two headers flagged
`label_text_not_matched` (`D_IO (cm²/s)`, `D_O (cm²/s)`) are accepted.
