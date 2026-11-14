import unittest

from combustion_atlas.normalization.schema import (
    Conditions,
    ExperimentRecord,
    Measurement,
    Provenance,
)
from combustion_atlas.normalization.validate import validate_candidate


def provenance() -> Provenance:
    return Provenance(
        source_url="https://psi.nasa.gov/physci/repo/data/investigations/PSI-25",
        source_sha256="a" * 64,
        record_number=2,
        column_name="Calibrated initial O2 % by vol",
    )


class NormalizationTests(unittest.TestCase):
    def test_preserves_controls_as_instrument_settings(self) -> None:
        record = ExperimentRecord(
            investigation_id=" PSI-25 ",
            test_id=" B1 ",
            conditions=Conditions(
                oxygen_pct=Measurement(
                    value=22.2, unit="%", original_value="22.2", provenance=provenance()
                )
            ),
            instrument_settings={"Fan display": "62"},
            raw_cells={"Fan display": "62"},
            provenance=[provenance()],
        )

        self.assertEqual(record.investigation_id, "PSI-25")
        self.assertEqual(record.test_id, "B1")
        self.assertIsNone(record.conditions.airflow_cm_s)
        self.assertEqual(record.instrument_settings["Fan display"], "62")

    def test_flags_physically_invalid_oxygen_for_review(self) -> None:
        record = ExperimentRecord(
            investigation_id="PSI-25",
            test_id="B2",
            conditions=Conditions(
                oxygen_pct=Measurement(
                    value=120, unit="%", original_value="120", provenance=provenance()
                )
            ),
            provenance=[provenance()],
        )

        self.assertEqual(validate_candidate(record).validation_status, "review_required")
