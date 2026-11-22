"""Unit tests for country target routing and 'Latest Record Wins' migration."""

from datetime import date, datetime
import unittest

from skypoints_engine.router import CountryRouter


class TestCountryRouter(unittest.TestCase):
    def setUp(self):
        self.router = CountryRouter()
        self.ts_day1 = datetime(2024, 1, 15, 6, 0, 0)
        self.ts_day2 = datetime(2024, 1, 16, 6, 0, 0)
        self.ts_old = datetime(2024, 1, 10, 6, 0, 0)

    def test_initial_country_distribution(self):
        records = [
            {
                "member_id": "M1",
                "member_name": "Elena",
                "country_code": "USA",
                "batch_timestamp": self.ts_day1,
                "source_row_number": 1,
            },
            {
                "member_id": "M2",
                "member_name": "Ravi",
                "country_code": "IND",
                "batch_timestamp": self.ts_day1,
                "source_row_number": 2,
            },
        ]
        counts = self.router.route_batch(records)
        self.assertEqual(counts["inserted"], 2)
        self.assertIn("M1", self.router.tables["table_usa"])
        self.assertIn("M2", self.router.tables["table_india"])

    def test_country_migration_latest_wins(self):
        # Day 1: Elena in USA
        day1_records = [
            {
                "member_id": "223457",
                "member_name": "Elena",
                "country_code": "USA",
                "batch_timestamp": self.ts_day1,
                "source_row_number": 1,
            }
        ]
        self.router.route_batch(day1_records)
        self.assertIn("223457", self.router.tables["table_usa"])
        self.assertNotIn("223457", self.router.tables["table_india"])

        # Day 2: Elena moves to India!
        day2_records = [
            {
                "member_id": "223457",
                "member_name": "Elena",
                "country_code": "IND",
                "batch_timestamp": self.ts_day2,
                "source_row_number": 1,
            }
        ]
        counts = self.router.route_batch(day2_records)
        self.assertEqual(counts["migrated"], 1)

        # Assert Elena is now in table_india AND deleted from table_usa
        self.assertNotIn("223457", self.router.tables["table_usa"])
        self.assertIn("223457", self.router.tables["table_india"])
        self.assertEqual(self.router.registry["223457"].current_country, "IND")
        self.assertEqual(len(self.router.migration_events), 1)

    def test_outdated_file_replay_discarded(self):
        # Day 2 state already processed
        day2_records = [
            {
                "member_id": "M1",
                "member_name": "Elena",
                "country_code": "IND",
                "batch_timestamp": self.ts_day2,
                "source_row_number": 1,
            }
        ]
        self.router.route_batch(day2_records)

        # Outdated day 1 file replayed late
        outdated_records = [
            {
                "member_id": "M1",
                "member_name": "Elena",
                "country_code": "USA",
                "batch_timestamp": self.ts_old,
                "source_row_number": 1,
            }
        ]
        counts = self.router.route_batch(outdated_records)
        self.assertEqual(counts["discarded_outdated"], 1)
        # Elena must STILL be in India!
        self.assertIn("M1", self.router.tables["table_india"])
        self.assertNotIn("M1", self.router.tables["table_usa"])


if __name__ == "__main__":
    unittest.main()
