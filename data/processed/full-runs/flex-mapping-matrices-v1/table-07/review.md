# Table 7: mapping review

Unreviewed proposal.

**Evidence class:** planned_test_matrix
**Quote:** "Slow flow LOI test matrix"
**Reason:** The caption identifies this as a test matrix, and the columns and full-width rows specify test settings rather than measured outcomes.

## Columns

| Column | Header | Field | Unit | Kind | Note |
|---|---|---|---|---|---|
| 0 | Test No. | test_number |  | identifier |  |
| 1 | P (atm) | pressure | atm | planned_condition |  |
| 2 | XO2 | oxygen_mole_fraction |  | planned_condition | No unit is stated; the column gives oxygen mole-fraction values. |

## Condition rows

| Row | Field | Source text | Value | Unit | Status |
|---|---|---|---|---|---|
| 0 | fuel | Fuel: C7H16 | C7H16 |  | single |
| 0 | diluent | Diluent: N2 | N2 |  | single |
| 0 | fiber_support | SiC fiber support | SiC |  | single |
| 0 | flow_velocity | Flow: 1.5 cm/s | 1.5 | cm/s | single |
| 0 | droplet_diameter | D0 = 3, 5 mm | 3, 5 | mm | multiple_values_unassigned |
| 0 | diluent_mole_fraction | XN2 = 1.0 − XO2. | 1.0 − XO2 |  | formula |
| 13 | fuel | Fuel: CH3OH | CH3OH |  | single |

## Automated checks

- context_flag:The source does not define D0 in the table or the adjacent pages.
- context_flag:The listed droplet diameters 3 and 5 mm are not assigned to specific tests.
- context_flag:The diluent mole fraction is given by the formula XN2 = 1.0 − XO2; no separate XN2 values are tabulated.

## Expanded records: 22

Example: `FLEX-T7-29`

- pressure = 0.5 atm 
- oxygen_mole_fraction = 0.2  (model: No unit is stated; the column gives oxygen mole-fraction values.)
- fuel = C7H16  
- diluent = N2  
- fiber_support = SiC  
- flow_velocity = 1.5 cm/s 
- droplet_diameter = 3, 5 mm (model: The source does not assign a diameter to a particular test.; ambiguous: The table states 'D0 = 3, 5 mm' for these tests without saying which value applies to each test.)
- condition_XN2 = 1.0 − XO2  (unresolved: Stated as a formula in the source; kept as written, not computed.)
