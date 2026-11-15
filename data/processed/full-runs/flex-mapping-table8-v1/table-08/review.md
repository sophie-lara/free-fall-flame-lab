# Table 8: mapping review

Unreviewed proposal.

**Evidence class:** planned_test_matrix (basis: "The caption identifies this as “CO2 suppressant efficacy test matrix.” The phrase “test matrix” indicates planned test conditions, not observed results.")

## Columns

| Column | Header | Field | Unit | Kind | Note |
|---|---|---|---|---|---|
| 0 | Test No. | test_number |  | identifier |  |
| 1 | P (atm) | pressure | atm | planned_condition |  |
| 2 | XO2 | oxygen_mole_fraction | mole fraction (dimensionless) | planned_condition |  |
| 3 | XCO2 | suppressant_mole_fraction | mole fraction (dimensionless) | planned_condition | Suppressant is identified as CO2 in the condition row. |

## Condition rows

| Row | Field | Source text | Value | Unit | Status |
|---|---|---|---|---|---|
| 0 | fuel | Fuel: C7H16 | C7H16 |  | single |
| 0 | diluent | Diluent: N2 | N2 |  | single |
| 0 | suppressant | Suppressant: CO2 | CO2 |  | single |
| 0 | fiber_support | No fiber support | No fiber support |  | single |
| 0 | flow_velocity | Flow: 0.0 cm/s | 0.0 cm/s | cm/s | single |
| 0 | droplet_diameter | D0 = 3, 5 mm | 3, 5 mm | mm | multiple_values_unassigned |
| 0 | inert_mole_fraction | XN2 = 1.0 − XO2 − XCO2. | XN2 = 1.0 − XO2 − XCO2. | mole fraction (dimensionless) | formula |
| 30 | fuel | Fuel: CH3OH. | CH3OH |  | single |

## Automated checks

- evidence_class_basis_not_verbatim
- context_flag:The condition D0 = 3, 5 mm lists multiple droplet-diameter values without assigning them to tests.
- context_flag:D0 is not defined on the provided pages.
- context_flag:The N2 mole fraction is given by the formula XN2 = 1.0 − XO2 − XCO2.

## Expanded records: 56

Example: `FLEX-T8-51`

- pressure = 0.7 atm 
- oxygen_mole_fraction = 0.25 mole fraction (dimensionless) 
- suppressant_mole_fraction = 0.15 mole fraction (dimensionless) (model: Suppressant is identified as CO2 in the condition row.)
- fuel = C7H16  
- diluent = N2  
- suppressant = CO2  
- fiber_support = No fiber support  
- flow_velocity = 0.0 cm/s cm/s 
- droplet_diameter = 3, 5 mm mm (model: The cell does not assign the listed values to particular tests.; ambiguous: The table states 'D0 = 3, 5 mm' for these tests without saying which value applies to each test.)
- condition_XN2 = XN2 = 1.0 − XO2 − XCO2. mole fraction (dimensionless) (model: Defines the N2 mole fraction in terms of the oxygen and CO2 mole fractions.; unresolved: Stated as a formula in the source; kept as written, not computed.)
