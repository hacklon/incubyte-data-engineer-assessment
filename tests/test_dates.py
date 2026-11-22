"""Unit tests for date parsing, age derivation, and stale member logic."""

from datetime import date
import unittest

from skypoints_engine.dates import (
    calculate_age,
    calculate_flight_stale_flag,
    parse_flexible_date,
)


class TestDateUtilities(unittest.TestCase):
    def test_parse_yyyymmdd(self):
        d = parse_flexible_date("20101012")
        self.assertEqual(d, date(2010, 10, 12))

    def test_parse_mmddyyyy(self):
        d = parse_flexible_date("03051985")
        self.assertEqual(d, date(1985, 3, 5))

    def test_parse_iso_dash(self):
        d = parse_flexible_date("2022-05-11")
        self.assertEqual(d, date(2022, 5, 11))

    def test_parse_slash_format(self):
        d1 = parse_flexible_date("12/1/1998")
        self.assertEqual(d1, date(1998, 12, 1))
        d2 = parse_flexible_date("8/13/1982")
        self.assertEqual(d2, date(1982, 8, 13))

    def test_parse_7_digit_compact(self):
        d = parse_flexible_date("6152022")
        self.assertEqual(d, date(2022, 6, 15))

    def test_parse_invalid_month_13(self):
        # As observed in regional Australia feed: '2021-13-13'
        d = parse_flexible_date("2021-13-13")
        self.assertIsNone(d)

    def test_parse_null_and_empty(self):
        self.assertIsNone(parse_flexible_date(None))
        self.assertIsNone(parse_flexible_date(""))
        self.assertIsNone(parse_flexible_date("NULL"))


class TestAgeCalculation(unittest.TestCase):
    def setUp(self):
        self.as_of = date(2024, 1, 15)

    def test_age_after_birthday_this_year(self):
        # Born Jan 10, 1990 -> already had birthday by Jan 15, 2024 (age 34)
        dob = date(1990, 1, 10)
        self.assertEqual(calculate_age(dob, self.as_of), 34)

    def test_age_before_birthday_this_year(self):
        # Born March 5, 1985 -> birthday not yet reached by Jan 15, 2024 (age 38)
        dob = date(1985, 3, 5)
        self.assertEqual(calculate_age(dob, self.as_of), 38)

    def test_age_exact_birthday(self):
        # Born Jan 15, 2000 -> turns exactly 24 today
        dob = date(2000, 1, 15)
        self.assertEqual(calculate_age(dob, self.as_of), 24)

    def test_age_leap_year(self):
        # Born Feb 29, 2000
        dob = date(2000, 2, 29)
        as_of_leap = date(2024, 2, 28)
        as_of_bday = date(2024, 2, 29)
        self.assertEqual(calculate_age(dob, as_of_leap), 23)
        self.assertEqual(calculate_age(dob, as_of_bday), 24)

    def test_age_null_or_future(self):
        self.assertIsNone(calculate_age(None, self.as_of))
        future_dob = date(2025, 1, 1)
        self.assertIsNone(calculate_age(future_dob, self.as_of))


class TestStaleMemberFlag(unittest.TestCase):
    def setUp(self):
        self.as_of = date(2024, 1, 15)

    def test_flight_within_90_days_is_active(self):
        # Flight on Dec 1, 2023 -> 45 days ago -> Stale = 'N'
        flight = date(2023, 12, 1)
        days, stale = calculate_flight_stale_flag(flight, self.as_of)
        self.assertEqual(days, 45)
        self.assertEqual(stale, "N")

    def test_flight_exactly_90_days_is_active(self):
        # Rule specifies > 90 days
        flight = date(2023, 10, 17)  # 90 days prior to 2024-01-15
        days, stale = calculate_flight_stale_flag(flight, self.as_of)
        self.assertEqual(days, 90)
        self.assertEqual(stale, "N")

    def test_flight_greater_than_90_days_is_stale(self):
        # Flight on Oct 13, 2012 -> 4111 days ago -> Stale = 'Y'
        flight = date(2012, 10, 13)
        days, stale = calculate_flight_stale_flag(flight, self.as_of)
        self.assertTrue(days > 90)
        self.assertEqual(stale, "Y")

    def test_null_flight_is_stale(self):
        days, stale = calculate_flight_stale_flag(None, self.as_of)
        self.assertIsNone(days)
        self.assertEqual(stale, "Y")


if __name__ == "__main__":
    unittest.main()
