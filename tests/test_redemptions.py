"""Unit tests for semi-structured JSON flattening and member profile joins."""

from datetime import date
from pathlib import Path
import unittest

from skypoints_engine.redemptions import (
    join_redemptions_with_members,
    parse_and_flatten_redemptions,
)

SAMPLE_JSON = Path("F:/Incubyte/data/raw/redemptions_20240115.json")


class TestRedemptions(unittest.TestCase):
    def test_flatten_sample_json(self):
        txns, rejected = parse_and_flatten_redemptions(SAMPLE_JSON)
        self.assertEqual(len(rejected), 0)
        self.assertEqual(len(txns), 2)

        # Check first transaction: RX10091
        t1 = txns[0]
        self.assertEqual(t1["member_id"], "223457")
        self.assertEqual(t1["txn_id"], "RX10091")
        self.assertEqual(t1["partner_name"], "AeroLink")
        self.assertEqual(t1["miles_redeemed"], 12000)
        self.assertEqual(t1["status"], "COMPLETED")
        self.assertEqual(t1["txn_date"], date(2024, 1, 10))

        # Check second transaction: RX10092
        t2 = txns[1]
        self.assertEqual(t2["txn_id"], "RX10092")
        self.assertEqual(t2["miles_redeemed"], 5000)
        self.assertEqual(t2["status"], "PENDING")

    def test_join_with_member_profiles(self):
        txns, _ = parse_and_flatten_redemptions(SAMPLE_JSON)

        # Mock member profiles
        member_lookup = {
            "223457": {
                "member_name": "Elena",
                "country_code": "USA",
                "tier_code": "GLD",
                "age": 38,
                "stale_member": "Y",
            }
        }

        joined = join_redemptions_with_members(txns, member_lookup)
        self.assertEqual(len(joined), 2)

        j1 = joined[0]
        self.assertEqual(j1["member_name"], "Elena")
        self.assertEqual(j1["country_code"], "USA")
        self.assertEqual(j1["tier_code"], "GLD")
        self.assertEqual(j1["age"], 38)
        self.assertEqual(j1["miles_redeemed"], 12000)


if __name__ == "__main__":
    unittest.main()
