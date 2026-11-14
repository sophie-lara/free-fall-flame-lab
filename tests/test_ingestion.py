import tempfile
import unittest
from pathlib import Path

from combustion_atlas.ingestion import read_csv_losslessly


class IngestionTests(unittest.TestCase):
    def test_preserves_source_whitespace_and_missing_cells(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.csv"
            path.write_text(
                "Test #,Fuel Sample Material,Note\nB1,  PMMA film  ,\n", encoding="utf-8"
            )
            table = read_csv_losslessly(path)

        self.assertEqual(table.rows[0].record_number, 2)
        self.assertEqual(table.rows[0].cells["Fuel Sample Material"], "  PMMA film  ")
        self.assertEqual(table.rows[0].cells["Note"], "")
        self.assertEqual(len(table.sha256), 64)
