"""Date normalization, age derivation, and flight inactivity metrics."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def parse_flexible_date(val: Any) -> date | None:
    """Parse heterogeneous date formats into a datetime.date object.

    Supported patterns:
      - 'YYYYMMDD' (e.g. '20101012')
      - 'MMDDYYYY' (e.g. '03051985')
      - 'YYYY-MM-DD' (e.g. '2022-05-11')
      - 'M/D/YYYY' or 'MM/DD/YYYY' (e.g. '12/1/1998', '8/13/1982')
      - 'MDDYYYY' (e.g. '6152022' -> 06/15/2022)

    Returns None if date is empty, malformed, or invalid (e.g. month 13).
    """
    if val is None:
        return None

    s = str(val).strip()
    if not s or s.upper() in ("NULL", "NONE", "NA", ""):
        return None

    # Pattern 1: ISO style YYYY-MM-DD
    if "-" in s:
        parts = s.split("-")
        if len(parts) == 3:
            try:
                y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                return date(y, m, d)
            except ValueError:
                return None

    # Pattern 2: Slash style M/D/YYYY or MM/DD/YYYY
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 3:
            try:
                m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
                return date(y, m, d)
            except ValueError:
                return None

    # Pattern 3: Compact numeric string
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return None

    # Length 8: YYYYMMDD vs MMDDYYYY
    if len(digits) == 8:
        # Check if first 4 digits represent a plausible year (1900-2099)
        first_four = int(digits[:4])
        if 1900 <= first_four <= 2099:
            try:
                return datetime.strptime(digits, "%Y%m%d").date()
            except ValueError:
                pass

        # Otherwise try MMDDYYYY (e.g. 03051985)
        try:
            return datetime.strptime(digits, "%m%d%Y").date()
        except ValueError:
            pass

    # Length 7: E.g., '3051985' (MDDYYYY -> 03051985) or '6152022' (06152022)
    if len(digits) == 7:
        padded = "0" + digits
        try:
            return datetime.strptime(padded, "%m%d%Y").date()
        except ValueError:
            pass

    return None


def calculate_age(dob: date | None, as_of: date) -> int | None:
    """Calculate completed calendar years of age as of an evaluation date.

    Correctly handles leap years and birthday anniversaries.
    Returns None if dob is None or chronologically in the future.
    """
    if dob is None:
        return None
    if dob > as_of:
        return None

    years = as_of.year - dob.year
    if (as_of.month, as_of.day) < (dob.month, dob.day):
        years -= 1
    return max(0, years)


def calculate_flight_stale_flag(
    last_flight: date | None,
    as_of: date,
    threshold_days: int = 90,
) -> tuple[int | None, str]:
    """Calculate days since last flight and determine stale member status.

    Rule: If days since flight > 90, Stale_Member is 'Y', else 'N'.
    If flight_date is None (no flight recorded), days is None and stale is 'Y'.
    """
    if last_flight is None:
        return None, "Y"

    days = (as_of - last_flight).days
    stale_flag = "Y" if days > threshold_days else "N"
    return days, stale_flag
