"""Configuration and reference lookups for the SkyPoints Data Engine."""

from __future__ import annotations

# Canonical Country Normalization Map
COUNTRY_CODE_MAP: dict[str, str] = {
    "IND": "IND",
    "INDIA": "IND",
    "IN": "IND",
    "USA": "USA",
    "US": "USA",
    "UNITED STATES": "USA",
    "CAN": "CAN",
    "CANADA": "CAN",
    "CA": "CAN",
    "AUS": "AUS",
    "AU": "AUS",
    "AUSTRALIA": "AUS",
    "PHIL": "PHL",
    "PHL": "PHL",
    "PHILIPPINES": "PHL",
    "PH": "PHL",
    "DEU": "DEU",
    "GERMANY": "DEU",
    "DE": "DEU",
    "GBR": "GBR",
    "UK": "GBR",
    "UNITED KINGDOM": "GBR",
}

# Country Target Table Identifiers
COUNTRY_TARGET_TABLES: dict[str, str] = {
    "IND": "table_india",
    "USA": "table_usa",
    "AUS": "table_australia",
    "CAN": "table_canada",
    "PHL": "table_philippines",
}
DEFAULT_TARGET_TABLE = "table_other_countries"

# Loyalty Tiers
VALID_TIER_CODES: set[str] = {"GLD", "SLV", "PLT", "BRZ", "DIA"}

# Business Logic Thresholds
STALE_FLIGHT_DAYS_THRESHOLD = 90
MAX_HUMAN_AGE_YEARS = 120
