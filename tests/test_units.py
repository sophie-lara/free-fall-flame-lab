import unittest

from combustion_atlas.normalization.units import UnsupportedUnitError, to_kpa


class UnitConversionTests(unittest.TestCase):
    def test_converts_atmospheres_to_kpa(self) -> None:
        self.assertEqual(to_kpa(1, "atm"), 101.325)

    def test_rejects_undocumented_pressure_units(self) -> None:
        with self.assertRaises(UnsupportedUnitError):
            to_kpa(1, "fan display")
