"""End-to-end regression test suite for SkyPoints Data Engine."""

from datetime import date
from pathlib import Path
import sqlite3
import tempfile
import unittest

from skypoints_engine.pipeline import SkyPointsPipeline

DATA_DIR = Path("F:/Incubyte/data/raw")


class TestPipelineE2E(unittest.TestCase):
    def setUp(self):
        self.as_of = date(2024, 1, 15)
        self.pipeline = SkyPointsPipeline(as_of=self.as_of)

    def test_full_pipeline_ingest_and_sqlite_export(self):
        # 1. Process Day 1 Flat File
        f1 = DATA_DIR / "skypoints_members_20240115_060000.dat"
        s1 = self.pipeline.process_member_file(f1)
        self.assertEqual(s1["total_raw"], 5)
        self.assertEqual(s1["valid_staged"], 5)
        self.assertEqual(s1["inserted"], 5)

        # 2. Process Regional CSVs
        self.pipeline.process_regional_csv(DATA_DIR / "regional_usa.csv", "USA")
        self.pipeline.process_regional_csv(DATA_DIR / "regional_aus.csv", "AUS")
        self.pipeline.process_regional_csv(DATA_DIR / "regional_ind.csv", "IND")

        # 3. Process Day 1 Redemptions
        j1 = DATA_DIR / "redemptions_20240115.json"
        rj1 = self.pipeline.process_redemptions_json(j1)
        self.assertEqual(rj1["valid_txns"], 2)

        # 4. Check Elena in USA prior to move
        self.assertIn("223457", self.pipeline.router.tables["table_usa"])
        self.assertNotIn("223457", self.pipeline.router.tables["table_india"])

        # 5. Process Day 2 Flat File (Elena moves to India, Hans joins in DEU)
        f2 = DATA_DIR / "skypoints_members_20240116_060000.dat"
        s2 = self.pipeline.process_member_file(f2)
        self.assertEqual(s2["migrated"], 1)
        self.assertEqual(s2["inserted"], 1)

        # Elena must now be in table_india and deleted from table_usa
        self.assertNotIn("223457", self.pipeline.router.tables["table_usa"])
        self.assertIn("223457", self.pipeline.router.tables["table_india"])

        # 6. Process Day 2 Redemptions (Status transition)
        j2 = DATA_DIR / "redemptions_20240116.json"
        self.pipeline.process_redemptions_json(j2)

        # Verify 360 Joined View
        enriched = self.pipeline.get_enriched_redemptions_360()
        self.assertTrue(len(enriched) >= 2)

        # 7. Test SQLite Database Export & Schema Queries
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            self.pipeline.export_to_sqlite(tmp_path)
            conn = sqlite3.connect(tmp_path)
            cur = conn.cursor()

            # Elena in India in SQLite
            cur.execute("SELECT COUNT(*) FROM table_india WHERE member_id = '223457'")
            self.assertEqual(cur.fetchone()[0], 1)

            # Elena deleted from USA in SQLite
            cur.execute("SELECT COUNT(*) FROM table_usa WHERE member_id = '223457'")
            self.assertEqual(cur.fetchone()[0], 0)

            # Quarantined record present for Jonnathan (2021-13-13)
            cur.execute("SELECT rule_id FROM dq_quarantine_log WHERE rule_id = 'E_INVALID_ENROLLMENT_DATE'")
            self.assertEqual(cur.fetchone()[0], "E_INVALID_ENROLLMENT_DATE")

            # Redemptions present
            cur.execute("SELECT COUNT(*) FROM fact_mileage_redemption")
            self.assertTrue(cur.fetchone()[0] >= 2)

            conn.close()
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


if __name__ == "__main__":
    unittest.main()
