# Table 6: mapping review

Unreviewed proposal.

**Evidence class:** planned_test_matrix
**Quote:** "do not represent the final test matrix"
**Reason:** The surrounding text describes these matrices as plans prepared for engineering and safety review, and explicitly says they are not the final test matrix.

## Columns

| Column | Header | Field | Unit | Kind | Note |
|---|---|---|---|---|---|
| 0 | Test No. | test_number |  | identifier |  |
| 1 | P (atm) | pressure | atm | planned_condition |  |
| 2 | XO2 | oxygen_mole_fraction |  | planned_condition | Mole fraction is dimensionless. |

## Condition rows

| Row | Field | Source text | Value | Unit | Status |
|---|---|---|---|---|---|
| 0 | fuel | Fuel: C7H16 | C7H16 |  | single |
| 0 | diluent | Diluent: N2 | N2 |  | single |
| 0 | fiber_support | No fiber support | No |  | single |
| 0 | flow_velocity | Flow: 0.0 cm/s | 0.0 | cm/s | single |
| 0 | droplet_diameter | D0 = 3, 5 mm | 3, 5 | mm | multiple_values_unassigned |
| 0 | diluent_mole_fraction | XN2 = 1.0 − XO2 | 1.0 − XO2 |  | formula |
| 16 | fuel | Fuel: CH3OH | CH3OH |  | single |

## Automated checks

- context_flag:D0 is not defined in the provided pages.
- context_flag:The listed droplet diameters (3, 5 mm) are not assigned to particular tests.

## Expanded records: 28

Example: `FLEX-T6-1`

- pressure = 0.5 atm 
- oxygen_mole_fraction = 0.2  (model: Mole fraction is dimensionless.)
- fuel = C7H16  
- diluent = N2  
- fiber_support = No  
- flow_velocity = 0.0 cm/s 
- droplet_diameter = 3, 5 mm (model: The source does not assign the listed diameters to particular tests.; ambiguous: The table states 'D0 = 3, 5 mm' for these tests without saying which value applies to each test.)
- condition_XN2 = 1.0 − XO2  (unresolved: Stated as a formula in the source; kept as written, not computed.)
