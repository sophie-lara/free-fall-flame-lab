# Table 8: mapping review

Unreviewed proposal.

**Evidence class:** planned_test_matrix
**Quote:** "CO2 suppressant efficacy test matrix."
**Reason:** The caption describes the table as a test matrix, and the rows specify combinations of planned pressure and mole-fraction conditions rather than outcomes or measurements.

## Columns

| Column | Header | Field | Unit | Kind | Note |
|---|---|---|---|---|---|
| 0 | Test No. | test_number |  | identifier |  |
| 1 | P (atm) | pressure | atm | planned_condition |  |
| 2 | XO2 | oxygen_mole_fraction |  | planned_condition | Mole fraction is dimensionless. |
| 3 | XCO2 | suppressant_mole_fraction |  | planned_condition | Mole fraction is dimensionless; the suppressant is CO2. |

## Condition rows

| Row | Field | Source text | Value | Unit | Status |
|---|---|---|---|---|---|
| 0 | fuel | Fuel: C7H16 | C7H16 |  | single |
| 0 | diluent | Diluent: N2 | N2 |  | single |
| 0 | suppressant | Suppressant: CO2 | CO2 |  | single |
| 0 | fiber_support | No fiber support | No fiber support |  | single |
| 0 | flow_velocity | Flow: 0.0 cm/s | 0.0 | cm/s | single |
| 0 | droplet_diameter | D0 = 3, 5 mm | 3, 5 | mm | multiple_values_unassigned |
| 0 | diluent_mole_fraction | XN2 = 1.0 − XO2 − XCO2 | 1.0 − XO2 − XCO2 |  | formula |
| 30 | fuel | Fuel: CH3OH. | CH3OH |  | single |

## Automated checks

- context_flag:D0 is not defined in the provided pages; the row states two possible values without assigning them to tests.
- context_flag:The formula for XN2 relates it to XO2 and XCO2; the table does not separately define the X notation, though the column headers identify the oxygen and CO2 fractions.

## Expanded records: 56

Example: `FLEX-T8-51`

- pressure = 0.7 atm 
- oxygen_mole_fraction = 0.25  (model: Mole fraction is dimensionless.)
- suppressant_mole_fraction = 0.15  (model: Mole fraction is dimensionless; the suppressant is CO2.)
- fuel = C7H16  
- diluent = N2  
- suppressant = CO2  
- fiber_support = No fiber support  
- flow_velocity = 0.0 cm/s 
- droplet_diameter = 3, 5 mm (model: The table does not assign the listed diameters to individual tests.; ambiguous: The table states 'D0 = 3, 5 mm' for these tests without saying which value applies to each test.)
- condition_XN2 = 1.0 − XO2 − XCO2  (model: N2 is identified as the diluent.; unresolved: Stated as a formula in the source; kept as written, not computed.)
