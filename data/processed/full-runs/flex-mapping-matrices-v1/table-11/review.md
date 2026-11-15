# Table 11: mapping review

Unreviewed proposal.

**Evidence class:** planned_test_matrix
**Quote:** "test matrix"
**Reason:** The caption identifies this as a test matrix, and the rows list test numbers with pressure and composition conditions rather than observed outcomes.

## Columns

| Column | Header | Field | Unit | Kind | Note |
|---|---|---|---|---|---|
| 0 | Test No. | test_number |  | identifier |  |
| 1 | P (atm) | pressure | atm | planned_condition |  |
| 2 | XO2 | oxygen_mole_fraction | mole fraction | planned_condition |  |
| 3 | XCO2 | suppressant_mole_fraction | mole fraction | planned_condition | CO2 is identified as the suppressant in the condition row. |

## Condition rows

| Row | Field | Source text | Value | Unit | Status |
|---|---|---|---|---|---|
| 0 | fuel | Fuel: C7H16 | C7H16 |  | single |
| 0 | diluent | Diluent: N2 | N2 |  | single |
| 0 | suppressant | Suppressant: CO2 | CO2 |  | single |
| 0 | fiber_support | No fiber | No fiber |  | single |
| 0 | flow_velocity | Flow: 1.5 cm/s | 1.5 | cm/s | single |
| 0 | droplet_diameter | D0 = 3, 5 mm | 3, 5 | mm | multiple_values_unassigned |
| 0 | diluent_mole_fraction | XN2 = 1.0−XO2−XCO2. | 1.0−XO2−XCO2 | mole fraction | formula |
| 22 | fuel | Fuel: CH3OH | CH3OH |  | single |

## Automated checks

- context_flag:D0 is not defined on the supplied pages; the condition gives two diameter values without assigning them to tests.
- context_flag:The XN2 formula refers to XO2 and XCO2, whose table headers identify oxygen and CO2 mole fractions.

## Expanded records: 40

Example: `FLEX-T11-219`

- pressure = 0.7 atm 
- oxygen_mole_fraction = 0.1 mole fraction 
- suppressant_mole_fraction = 0.15 mole fraction (model: CO2 is identified as the suppressant in the condition row.)
- fuel = C7H16  
- diluent = N2  
- suppressant = CO2  
- fiber_support = No fiber  
- flow_velocity = 1.5 cm/s 
- droplet_diameter = 3, 5 mm (model: The pages do not assign the two stated diameters to particular tests.; ambiguous: The table states 'D0 = 3, 5 mm' for these tests without saying which value applies to each test.)
- condition_XN2 = 1.0−XO2−XCO2 mole fraction (model: N2 is identified as the diluent; the formula relates its mole fraction to the oxygen and CO2 mole fractions.; unresolved: Stated as a formula in the source; kept as written, not computed.)
