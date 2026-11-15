# Table 12: mapping review

Unreviewed proposal.

**Evidence class:** planned_test_matrix
**Quote:** "Table 12: Suppressant in a radiative environment test matrix."
**Reason:** The caption explicitly calls this a test matrix, and the rows specify test settings rather than reporting outcomes.

## Columns

| Column | Header | Field | Unit | Kind | Note |
|---|---|---|---|---|---|
| 0 | Test No. | test_number |  | identifier |  |
| 1 | P (atm) | pressure | atm | planned_condition |  |
| 2 | XO2 | oxygen_mole_fraction |  | planned_condition | No unit is stated. |
| 3 | XCO2 | suppressant_mole_fraction |  | planned_condition | The row-header identifies CO2 as the suppressant. No unit is stated. |

## Condition rows

| Row | Field | Source text | Value | Unit | Status |
|---|---|---|---|---|---|
| 0 | fuel | Fuel: C7H16 | C7H16 |  | single |
| 0 | diluent | Diluent: N2 | N2 |  | single |
| 0 | suppressant | Suppressant: CO2 | CO2 |  | single |
| 0 | fiber_support | No fiber
support | No fiber support |  | single |
| 0 | flow_velocity | Flow: 0.0 cm/s | 0.0 | cm/s | single |
| 0 | droplet_diameter | D0 = 3, 5 mm | 3, 5 | mm | multiple_values_unassigned |
| 0 | diluent_mole_fraction | XN2 = 1.0 − XO2 − XCO2. | 1.0 − XO2 − XCO2 |  | formula |
| 18 | fuel | Fuel: CH3OH | CH3OH |  | single |

## Automated checks

- context_flag:The droplet-diameter condition lists 3 and 5 mm without assigning either value to particular tests.
- context_flag:The row-header gives XN2 as a formula rather than listing it as a separate table column.
- context_flag:The caption identifies a radiative environment, but the table does not state a radiative-environment parameter or value.

## Expanded records: 32

Example: `FLEX-T12-259`

- pressure = 2.0 atm 
- oxygen_mole_fraction = 0.1  (model: No unit is stated.)
- suppressant_mole_fraction = 0.15  (model: The row-header identifies CO2 as the suppressant. No unit is stated.)
- fuel = C7H16  
- diluent = N2  
- suppressant = CO2  
- fiber_support = No fiber support  
- flow_velocity = 0.0 cm/s 
- droplet_diameter = 3, 5 mm (ambiguous: The table states 'D0 = 3, 5 mm' for these tests without saying which value applies to each test.)
- condition_XN2 = 1.0 − XO2 − XCO2  (model: XN2 is the N2 mole fraction; the expression relates it to the oxygen and suppressant mole fractions.; unresolved: Stated as a formula in the source; kept as written, not computed.)
