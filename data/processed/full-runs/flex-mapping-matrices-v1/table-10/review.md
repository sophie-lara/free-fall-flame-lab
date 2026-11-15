# Table 10: mapping review

Unreviewed proposal.

**Evidence class:** planned_test_matrix
**Quote:** "test matrix"
**Reason:** The caption identifies the table as a test matrix, and the columns list test numbers and conditions rather than measured outcomes.

## Columns

| Column | Header | Field | Unit | Kind | Note |
|---|---|---|---|---|---|
| 0 | Test No. | test_number |  | identifier |  |
| 1 | P (atm) | pressure | atm | planned_condition |  |
| 2 | XO2 | oxygen_mole_fraction |  | planned_condition | Mole fraction; no unit stated. |
| 3 | XSF6 | suppressant_mole_fraction |  | planned_condition | Mole fraction of SF6; no unit stated. |

## Condition rows

| Row | Field | Source text | Value | Unit | Status |
|---|---|---|---|---|---|
| 0 | fuel | Fuel: C7H16 | C7H16 |  | single |
| 0 | diluent | Diluent: N2 | N2 |  | single |
| 0 | suppressant | Suppressant: SF6 | SF6 |  | single |
| 0 | fiber_support | No fiber support | No |  | single |
| 0 | flow_velocity | Flow: 0.0 cm/s | 0.0 | cm/s | single |
| 0 | droplet_diameter | D0 = 3, 5 mm | 3, 5 | mm | multiple_values_unassigned |
| 0 | diluent_mole_fraction | XN2 = 1.0 − XO2 − XSF6. | 1.0 − XO2 − XSF6 |  | formula |
| 30 | fuel | Fuel: CH3OH | CH3OH |  | single |

## Automated checks

- context_flag:The condition row lists D0 = 3, 5 mm without assigning a diameter to a particular test.
- context_flag:The symbols D0 and XN2 are defined only by their use in the condition row; the formula states the relation for XN2.

## Expanded records: 56

Example: `FLEX-T10-163`

- pressure = 0.7 atm 
- oxygen_mole_fraction = 0.25  (model: Mole fraction; no unit stated.)
- suppressant_mole_fraction = 0.15  (model: Mole fraction of SF6; no unit stated.)
- fuel = C7H16  
- diluent = N2  
- suppressant = SF6  
- fiber_support = No  
- flow_velocity = 0.0 cm/s 
- droplet_diameter = 3, 5 mm (model: The table does not assign the listed diameters to particular tests.; ambiguous: The table states 'D0 = 3, 5 mm' for these tests without saying which value applies to each test.)
- condition_XN2 = 1.0 − XO2 − XSF6  (model: Formula for the N2 mole fraction.; unresolved: Stated as a formula in the source; kept as written, not computed.)
