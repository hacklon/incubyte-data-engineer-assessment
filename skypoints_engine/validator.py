"""Data validation and staging enrichment engine."""

from __future__ import annotations

from datetime import date
from typing import Any

from .config import (
    COUNTRY_CODE_MAP,
    MAX_HUMAN_AGE_YEARS,
    STALE_FLIGHT_DAYS_THRESHOLD,
    VALID_TIER_CODES,
)
from .dates import (
    calculate_age,
    calculate_flight_stale_flag,
    parse_flexible_date,
)


def validate_and_enrich_member(
    raw_record: dict[str, Any],
    as_of: date,
) -> dict[str, Any]:
    """Validate a parsed member record, derive Age & Stale_Member, and assign DQ status.

    Returns an enriched record dict with:
      - is_valid: bool
      - dq_rule_id: str | None
      - dq_reason: str | None
      - enriched attributes: age, stale_member, days_since_flight, parsed dates, normalized country
    """
    enriched = dict(raw_record)

    member_id = (raw_record.get("member_id") or "").strip()
    member_name = (raw_record.get("member_name") or "").strip()
    country_raw = (raw_record.get("country_raw") or "").strip().upper()

    # Rule 1: Mandatory Member ID
    if not member_id:
        enriched.update({
            "is_valid": False,
            "dq_rule_id": "E_MANDATORY_NULL",
            "dq_reason": "Member ID is missing or empty",
            "dq_field": "MEMBER_ID",
            "dq_severity": "BLOCKING",
        })
        return enriched

    # Rule 2: Mandatory Member Name
    if not member_name:
        enriched.update({
            "is_valid": False,
            "dq_rule_id": "E_MANDATORY_NULL",
            "dq_reason": "Member Name is missing or empty",
            "dq_field": "MEMBER_NAME",
            "dq_severity": "BLOCKING",
        })
        return enriched

    # Rule 3: Mandatory & Valid Enrollment Date
    enroll_dt = parse_flexible_date(raw_record.get("enrollment_date_raw"))
    if enroll_dt is None:
        enriched.update({
            "is_valid": False,
            "dq_rule_id": "E_INVALID_ENROLLMENT_DATE",
            "dq_reason": f"Enrollment date '{raw_record.get('enrollment_date_raw')}' is invalid or missing",
            "dq_field": "ENROLLMENT_DATE",
            "dq_severity": "BLOCKING",
        })
        return enriched

    # Rule 4: Mandatory & Valid Country Code
    if not country_raw:
        enriched.update({
            "is_valid": False,
            "dq_rule_id": "E_MISSING_COUNTRY",
            "dq_reason": "Country code is missing",
            "dq_field": "COUNTRY",
            "dq_severity": "BLOCKING",
        })
        return enriched

    normalized_country = COUNTRY_CODE_MAP.get(country_raw, country_raw)

    # Optional Date Parsing
    flight_dt = parse_flexible_date(raw_record.get("last_flight_date_raw"))
    dob = parse_flexible_date(raw_record.get("dob_raw"))

    # Rule 5: Date Consistency — DOB prior to Enrollment Date
    if dob is not None and dob > enroll_dt:
        enriched.update({
            "is_valid": False,
            "dq_rule_id": "E_DOB_AFTER_ENROLLMENT",
            "dq_reason": f"Date of birth ({dob}) cannot be after enrollment date ({enroll_dt})",
            "dq_field": "DATE_OF_BIRTH",
            "dq_severity": "BLOCKING",
        })
        return enriched

    # Derived Metrics (Deliverable 2)
    calculated_age = calculate_age(dob, as_of)
    days_since_flight, stale_flag = calculate_flight_stale_flag(
        flight_dt,
        as_of,
        threshold_days=STALE_FLIGHT_DAYS_THRESHOLD,
    )

    # Sanity checks on derived values
    if calculated_age is not None and calculated_age > MAX_HUMAN_AGE_YEARS:
        enriched.update({
            "is_valid": False,
            "dq_rule_id": "W_IMPLAUSIBLE_AGE",
            "dq_reason": f"Calculated age ({calculated_age}) exceeds {MAX_HUMAN_AGE_YEARS}",
            "dq_field": "AGE",
            "dq_severity": "WARNING",
        })

    # Normalized fields
    tier = (raw_record.get("tier_code") or "").strip().upper()
    if tier and tier not in VALID_TIER_CODES:
        tier = "UNKNOWN"

    enriched.update({
        "is_valid": True,
        "dq_rule_id": None,
        "dq_reason": None,
        "member_id": member_id,
        "member_name": member_name,
        "enrollment_date": enroll_dt,
        "last_flight_date": flight_dt,
        "dob": dob,
        "country_code": normalized_country,
        "tier_code": tier or None,
        "age": calculated_age,
        "days_since_flight": days_since_flight,
        "stale_member": stale_flag,
        "is_active": (raw_record.get("is_active") or "A").strip().upper()[:1],
    })
    return enriched
