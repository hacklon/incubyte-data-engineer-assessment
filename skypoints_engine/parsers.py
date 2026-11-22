"""Flat file and JSON ingestion parsers for the SkyPoints Data Engine."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Generator

from .dates import parse_flexible_date

_TIMESTAMP_RE = re.compile(r"(\d{8})_(\d{6})")
_DATE_ONLY_RE = re.compile(r"(\d{8})")


def extract_batch_metadata(file_path: str | Path) -> tuple[str, datetime]:
    """Extract batch ID and timestamp from filename."""
    path = Path(file_path)
    name = path.name

    # Try YYYYMMDD_HHMMSS
    match = _TIMESTAMP_RE.search(name)
    if match:
        dt_str = f"{match.group(1)}_{match.group(2)}"
        try:
            return dt_str, datetime.strptime(dt_str, "%Y%m%d_%H%M%S")
        except ValueError:
            pass

    # Try YYYYMMDD
    match_date = _DATE_ONLY_RE.search(name)
    if match_date:
        d_str = match_date.group(1)
        try:
            return d_str, datetime.strptime(d_str, "%Y%m%d")
        except ValueError:
            pass

    # Fallback to current time
    now = datetime.utcnow()
    return now.strftime("%Y%m%d_%H%M%S"), now


def parse_pipe_flat_file(file_path: str | Path) -> Generator[dict[str, Any], None, None]:
    """Parse pipe-delimited member profile file (|H|... |D|...).

    Tolerant to schema drift (e.g. 10 tokens vs 11 tokens).
    Yields parsed record dicts.
    """
    path = Path(file_path)
    batch_id, batch_ts = extract_batch_metadata(path)

    with open(path, mode="r", encoding="utf-8", errors="replace") as f:
        for row_idx, line in enumerate(f, start=1):
            line_str = line.strip()
            if not line_str:
                continue

            # Split tokens by pipe
            raw_tokens = line_str.split("|")
            # If leading or trailing pipes exist, trim empty boundaries
            tokens = [t.strip() for t in raw_tokens]
            if tokens and tokens[0] == "":
                tokens.pop(0)
            if tokens and tokens[-1] == "":
                tokens.pop()

            if not tokens:
                continue

            record_type = tokens[0].upper()
            if record_type != "D":
                # Header or trailer record; skip detail extraction
                continue

            # Expected fields after record_type 'D':
            # 1: Member_Name
            # 2: Member_Id
            # 3: Enrollment_Date
            # 4: Last_Flight_Date
            # 5: Tier_Code
            # 6: Agent_Name
            # 7: State
            # 8: Country
            # 9: DOB
            # 10: Is_Active (Optional / defaults to 'A')
            member_name = tokens[1] if len(tokens) > 1 else None
            member_id = tokens[2] if len(tokens) > 2 else None
            enroll_raw = tokens[3] if len(tokens) > 3 else None
            flight_raw = tokens[4] if len(tokens) > 4 else None
            tier_code = tokens[5] if len(tokens) > 5 else None
            agent_name = tokens[6] if len(tokens) > 6 else None
            state_val = tokens[7] if len(tokens) > 7 else None
            country_raw = tokens[8] if len(tokens) > 8 else None

            # Handle 10-token vs 11-token drift:
            # If 10 items total after splitting: DOB is at index 9, Is_Active at index 10 (or missing)
            post_code = None
            dob_raw = None
            is_active = "A"

            if len(tokens) == 10:
                # Layout: D, Name, Id, Enroll, Flight, Tier, Agent, State, Country, DOB
                dob_raw = tokens[9]
            elif len(tokens) >= 11:
                # If token 9 looks like DOB (8 or 7 digits) and token 10 is 1 char (e.g. 'A')
                if len(tokens[10]) <= 2 and not tokens[10].isdigit():
                    dob_raw = tokens[9]
                    is_active = tokens[10]
                else:
                    # Layout with Post Code: D, Name, Id, Enroll, Flight, Tier, Agent, State, Country, PostCode, DOB, [Active]
                    post_code = tokens[9]
                    dob_raw = tokens[10]
                    if len(tokens) > 11:
                        is_active = tokens[11]

            yield {
                "batch_id": batch_id,
                "batch_timestamp": batch_ts,
                "source_file": path.name,
                "source_row_number": row_idx,
                "raw_payload": line_str,
                "source_namespace": "GLOBAL",
                "member_id": member_id,
                "member_name": member_name,
                "enrollment_date_raw": enroll_raw,
                "last_flight_date_raw": flight_raw,
                "tier_code": tier_code,
                "agent_name": agent_name,
                "state_code": state_val,
                "country_raw": country_raw,
                "post_code": post_code,
                "dob_raw": dob_raw,
                "is_active": is_active or "A",
            }
