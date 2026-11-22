"""Unit tests for flat file parsing and validation."""

from datetime import date
from pathlib import Path
import unittest

from skypoints_engine.parsers import parse_pipe_flat_file
from skypoints_engine.validator import validate_and_enrich_member

SAMPLE_FILE = Path("F:/Incubyte/data/raw/skypoints_members_20240115_060000.dat")


class TestParsersAndValidation(unittest.TestCase):
    def setUp(self):
        self.as_of = date(2024, 1, 15)

    def test_parse_sample_file_row_count(self):
        records = list(parse_pipe_flat_file(SAMPLE_FILE))
        # 5 detail records in sample file
        self.assertEqual(len(records), 5)

    def test_parse_elena_record(self):
        records = list(parse_pipe_flat_file(SAMPLE_FILE))
        elena = records[0]
        self.assertEqual(elena["member_name"], "Elena")
        self.assertEqual(elena["member_id"], "223457")
        self.assertEqual(elena["country_raw"], "USA")

        # Validate Elena
        validated = validate_and_enrich_member(elena, self.as_of)
        self.assertTrue(validated["is_valid"])
        self.assertEqual(validated["country_code"], "USA")
        self.assertEqual(validated["age"], 38)
        self.assertEqual(validated["stale_member"], "Y")

    def test_country_normalization_phil_and_au(self):
        records = list(parse_pipe_flat_file(SAMPLE_FILE))
        # Mateo has country PHIL
        mateo = records[2]
        val_mateo = validate_and_enrich_member(mateo, self.as_of)
        self.assertEqual(val_mateo["country_code"], "PHL")

        # Jacob has country AU
        jacob = records[4]
        val_jacob = validate_and_enrich_member(jacob, self.as_of)
        self.assertEqual(val_jacob["country_code"], "AUS")

    def test_mandatory_missing_id_quarantined(self):
        bad_record = {
            "member_id": "",
            "member_name": "Test User",
            "enrollment_date_raw": "20200101",
            "country_raw": "USA",
        }
        res = validate_and_enrich_member(bad_record, self.as_of)
        self.assertFalse(res["is_valid"])
        self.assertEqual(res["dq_rule_id"], "E_MANDATORY_NULL")

    def test_dob_after_enrollment_quarantined(self):
        bad_record = {
            "member_id": "999",
            "member_name": "Time Traveler",
            "enrollment_date_raw": "20100101",
            "dob_raw": "20150101",  # Born 5 years after enrolled!
            "country_raw": "IND",
        }
        res = validate_and_enrich_member(bad_record, self.as_of)
        self.assertFalse(res["is_valid"])
        self.assertEqual(res["dq_rule_id"], "E_DOB_AFTER_ENROLLMENT")


if __name__ == "__main__":
    unittest.main()
