"""Unit tests for regional feed adapters."""

from datetime import date
from pathlib import Path
import unittest

from skypoints_engine.adapters import parse_regional_csv
from skypoints_engine.validator import validate_and_enrich_member

DATA_DIR = Path("F:/Incubyte/data/raw")


class TestRegionalAdapters(unittest.TestCase):
    def setUp(self):
        self.as_of = date(2024, 1, 15)

    def test_regional_usa_feed(self):
        usa_file = DATA_DIR / "regional_usa.csv"
        records = list(parse_regional_csv(usa_file, "USA"))
        self.assertEqual(len(records), 3)

        # Sam (ID 1 -> USA-1)
        r1 = records[0]
        self.assertEqual(r1["member_id"], "USA-1")
        self.assertEqual(r1["member_name"], "Sam")
        v1 = validate_and_enrich_member(r1, self.as_of)
        self.assertTrue(v1["is_valid"])
        self.assertEqual(v1["country_code"], "USA")

    def test_regional_aus_invalid_date_quarantined(self):
        aus_file = DATA_DIR / "regional_aus.csv"
        records = list(parse_regional_csv(aus_file, "AUS"))
        self.assertEqual(len(records), 3)

        # Row 2 is Jonnathan with invalid month 13 in enrollment date '2021-13-13'
        jonnathan = records[1]
        self.assertEqual(jonnathan["member_id"], "AUS-2")
        v2 = validate_and_enrich_member(jonnathan, self.as_of)
        self.assertFalse(v2["is_valid"])
        self.assertEqual(v2["dq_rule_id"], "E_INVALID_ENROLLMENT_DATE")

        # Row 3 is Cristina, valid
        cristina = records[2]
        v3 = validate_and_enrich_member(cristina, self.as_of)
        self.assertTrue(v3["is_valid"])
        self.assertEqual(v3["country_code"], "AUS")

    def test_regional_ind_corporate_and_slashes(self):
        ind_file = DATA_DIR / "regional_ind.csv"
        records = list(parse_regional_csv(ind_file, "IND"))
        self.assertEqual(len(records), 3)

        # Row 2 is Rahul (Corporate)
        rahul = records[1]
        self.assertEqual(rahul["member_type"], "CORPORATE")
        v = validate_and_enrich_member(rahul, self.as_of)
        self.assertTrue(v["is_valid"])
        self.assertEqual(v["country_code"], "IND")
        self.assertEqual(v["age"], 41)


if __name__ == "__main__":
    unittest.main()
