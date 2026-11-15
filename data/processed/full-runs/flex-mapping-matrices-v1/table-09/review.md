# Table 9: mapping review

Unreviewed proposal.

**Evidence class:** planned_test_matrix
**Quote:** "He suppressant efficacy test matrix."
**Reason:** The caption explicitly calls this a test matrix, and the table lists test numbers alongside set pressure and mole-fraction conditions rather than reporting outcomes.

## Columns

| Column | Header | Field | Unit | Kind | Note |
|---|---|---|---|---|---|
| 0 | Test No. | test_number |  | identifier |  |
| 1 | P (atm) | pressure | atm | planned_condition |  |
| 2 | XO2 | oxygen_mole_fraction |  | planned_condition | Mole fraction; dimensionless. |
| 3 | XHe | suppressant_mole_fraction |  | planned_condition | He is identified as the suppressant in the condition row; mole fraction is dimensionless. |

## Condition rows

| Row | Field | Source text | Value | Unit | Status |
|---|---|---|---|---|---|
| 0 | fuel | Fuel: C7H16 | C7H16 |  | single |
| 0 | diluent | Diluent: N2 | N2 |  | single |
| 0 | suppressant | Suppressant: He | He |  | single |
| 0 | fiber_support | No fiber support | No |  | single |
| 0 | flow_velocity | Flow: 0.0 cm/s | 0.0 | cm/s | single |
| 0 | droplet_diameter | D0 = 3, 5 mm | 3, 5 | mm | multiple_values_unassigned |
| 0 | diluent_mole_fraction | XN2 = 1.0 − XO2 − XHe. | 1.0 − XO2 − XHe |  | formula |
| 30 | fuel | Fuel: CH3OH | CH3OH |  | single |

## Automated checks

- context_flag:D0 is not defined on the provided pages; the stated droplet-diameter values are unassigned to individual tests.
- context_flag:The XN2 formula relates the diluent mole fraction to XO2 and XHe; it does not assign a separate per-test value in the condition row.

## Expanded records: 56

Example: `FLEX-T9-107`

- pressure = 0.7 atm 
- oxygen_mole_fraction = 0.25  (model: Mole fraction; dimensionless.)
- suppressant_mole_fraction = 0.15  (model: He is identified as the suppressant in the condition row; mole fraction is dimensionless.)
- fuel = C7H16  
- diluent = N2  
- suppressant = He  
- fiber_support = No  
- flow_velocity = 0.0 cm/s 
- droplet_diameter = 3, 5 mm (model: The table does not specify which test uses each diameter.; ambiguous: The table states 'D0 = 3, 5 mm' for these tests without saying which value applies to each test.)
- condition_XN2 = 1.0 − XO2 − XHe  (unresolved: Stated as a formula in the source; kept as written, not computed.)
