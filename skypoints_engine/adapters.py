"""Regional feed adapters for heterogeneous country CSV files.

Normalizes diverse column naming, date patterns, and namespaces local IDs.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Generator


def parse_regional_csv(
    file_path: str | Path,
    country_code: str,
) -> Generator[dict[str, Any], None, None]:
    """Parse regional CSV files with diverse headers and structure.

    Namespaces member IDs (e.g. 'USA-1', 'AUS-1', 'IND-1') to prevent cross-source collision.
    """
    path = Path(file_path)
    now = datetime.utcnow()
    namespace = country_code.upper()

    with open(path, mode="r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=1):
            # Normalize key case and whitespace
            clean_row = {k.strip().lower(): (v.strip() if v else None) for k, v in row.items() if k}

            # Map ID
            raw_id = (
                clean_row.get("unique id")
                or clean_row.get("id")
                or clean_row.get("member id")
            )
            namespaced_id = f"{namespace}-{raw_id}" if raw_id else None

            # Map Name
            name = (
                clean_row.get("member name")
                or clean_row.get("name")
            )

            # Map Tier
            tier = (
                clean_row.get("tier type")
                or clean_row.get("tiercode")
                or clean_row.get("tier_code")
                or clean_row.get("tier")
            )

            # Map Enrollment Date
            enroll = (
                clean_row.get("date of enrollment")
                or clean_row.get("enrollmentdate")
                or clean_row.get("enrollment date")
                or clean_row.get("enrollment_date")
            )

            # Map Flight Date
            flight = (
                clean_row.get("date of flight")
                or clean_row.get("flightdate")
                or clean_row.get("flight date")
                or clean_row.get("flight_date")
            )

            # Map DOB
            dob = (
                clean_row.get("date of birth")
                or clean_row.get("dob")
            )

            # Member Type / Corporate
            member_type = "INDIVIDUAL"
            corp_flag = clean_row.get("individual or corporate")
            if corp_flag and corp_flag.upper() == "C":
                member_type = "CORPORATE"

            yield {
                "batch_id": f"REGIONAL_{namespace}",
                "batch_timestamp": now,
                "source_file": path.name,
                "source_row_number": idx,
                "raw_payload": str(row),
                "source_namespace": namespace,
                "member_id": namespaced_id,
                "member_name": name,
                "enrollment_date_raw": enroll,
                "last_flight_date_raw": flight,
                "tier_code": tier,
                "agent_name": None,
                "state_code": None,
                "country_raw": country_code,
                "post_code": None,
                "dob_raw": dob,
                "is_active": "A",
                "member_type": member_type,
            }
