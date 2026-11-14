import unittest

from combustion_atlas.normalization.schema import (
    Conditions,
    ExperimentRecord,
    Measurement,
    Provenance,
)
from combustion_atlas.retrieval import filter_records, reciprocal_rank_fusion


class RetrievalTests(unittest.TestCase):
    def test_range_excludes_missing_and_nonmatching_values(self) -> None:
        provenance = Provenance(source_url="https://example.test/source", source_sha256="b" * 64)
        matching = ExperimentRecord(
            investigation_id="PSI-25",
            test_id="B1",
            conditions=Conditions(
                material="PMMA",
                oxygen_pct=Measurement(
                    value=22.2, unit="%", original_value="22.2", provenance=provenance
                ),
            ),
            provenance=[provenance],
        )
        missing = ExperimentRecord(investigation_id="PSI-25", test_id="B2", provenance=[provenance])
        results = filter_records(
            [matching, missing], material="pmma", oxygen_min_pct=20, oxygen_max_pct=23
        )
        self.assertEqual([record.test_id for record in results], ["B1"])

    def test_fuses_independent_rankings(self) -> None:
        fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]])
        self.assertEqual(fused[0][0], "b")
