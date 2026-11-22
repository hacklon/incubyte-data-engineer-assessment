"""End-to-End SkyPoints ETL Pipeline Orchestration Engine."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3
from typing import Any

from .adapters import parse_regional_csv
from .config import COUNTRY_TARGET_TABLES
from .dates import parse_flexible_date
from .parsers import parse_pipe_flat_file
from .redemptions import (
    join_redemptions_with_members,
    parse_and_flatten_redemptions,
)
from .router import CountryRouter
from .validator import validate_and_enrich_member


class SkyPointsPipeline:
    """Enterprise batch pipeline orchestrating landing -> staging -> routing -> joins."""

    def __init__(self, as_of: date | None = None):
        self.as_of = as_of or date(2024, 1, 15)
        self.router = CountryRouter()
        self.staged_valid_records: list[dict[str, Any]] = []
        self.quarantined_records: list[dict[str, Any]] = []
        self.flattened_redemptions: dict[str, dict[str, Any]] = {}
        self.processed_files: set[str] = set()

    def process_member_file(self, file_path: str | Path) -> dict[str, int]:
        """Ingest, validate, enrich and route a pipe-delimited member profile file."""
        path = Path(file_path)
        self.processed_files.add(path.name)

        raw_records = list(parse_pipe_flat_file(path))
        valid_batch = []

        for rec in raw_records:
            validated = validate_and_enrich_member(rec, self.as_of)
            if validated["is_valid"]:
                valid_batch.append(validated)
                self.staged_valid_records.append(validated)
            else:
                self.quarantined_records.append(validated)

        route_stats = self.router.route_batch(valid_batch)
        return {
            "total_raw": len(raw_records),
            "valid_staged": len(valid_batch),
            "quarantined": len(raw_records) - len(valid_batch),
            **route_stats,
        }

    def process_regional_csv(self, file_path: str | Path, country_code: str) -> dict[str, int]:
        """Ingest regional CSV feed with custom headers and namespace."""
        path = Path(file_path)
        self.processed_files.add(path.name)

        raw_records = list(parse_regional_csv(path, country_code))
        valid_batch = []

        for rec in raw_records:
            validated = validate_and_enrich_member(rec, self.as_of)
            if validated["is_valid"]:
                valid_batch.append(validated)
                self.staged_valid_records.append(validated)
            else:
                self.quarantined_records.append(validated)

        route_stats = self.router.route_batch(valid_batch)
        return {
            "total_raw": len(raw_records),
            "valid_staged": len(valid_batch),
            "quarantined": len(raw_records) - len(valid_batch),
            **route_stats,
        }

    def process_redemptions_json(self, file_path: str | Path) -> dict[str, int]:
        """Ingest, flatten, and merge partner mileage redemption JSON."""
        path = Path(file_path)
        self.processed_files.add(path.name)

        txns, rejected = parse_and_flatten_redemptions(path)
        for r in rejected:
            self.quarantined_records.append({
                "source_file": path.name,
                "is_valid": False,
                "dq_rule_id": r["rule_id"],
                "dq_reason": r["reason"],
                "raw_payload": str(r["payload"]),
            })

        for t in txns:
            pk = t["redemption_pk"]
            if pk not in self.flattened_redemptions:
                self.flattened_redemptions[pk] = t
            else:
                existing = self.flattened_redemptions[pk]
                # Update if incoming feed_date is newer or equal (status transitions e.g. PENDING -> COMPLETED)
                if (t["feed_date"] or date.min) >= (existing["feed_date"] or date.min):
                    self.flattened_redemptions[pk] = t

        return {
            "valid_txns": len(txns),
            "rejected_txns": len(rejected),
            "total_active_txns": len(self.flattened_redemptions),
        }

    def get_consolidated_members(self) -> dict[str, dict[str, Any]]:
        """Return active members across all country tables."""
        members = {}
        for tbl, data in self.router.tables.items():
            for mid, rec in data.items():
                members[mid] = rec
        return members

    def get_enriched_redemptions_360(self) -> list[dict[str, Any]]:
        """Join all flattened redemptions with active member profiles."""
        members = self.get_consolidated_members()
        return join_redemptions_with_members(
            list(self.flattened_redemptions.values()),
            members,
        )

    def export_to_sqlite(self, db_path: str | Path) -> None:
        """Export current pipeline state to an analytical SQLite database for local query demonstration."""
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(db_file)
        cur = conn.cursor()

        # 1. Staging Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stg_member_profiles (
                member_id TEXT,
                member_name TEXT,
                country_code TEXT,
                tier_code TEXT,
                enrollment_date TEXT,
                last_flight_date TEXT,
                dob TEXT,
                age INTEGER,
                days_since_flight INTEGER,
                stale_member TEXT,
                is_active TEXT,
                batch_id TEXT,
                source_file TEXT
            )
        """)
        cur.execute("DELETE FROM stg_member_profiles")

        stg_rows = [
            (
                r.get("member_id"),
                r.get("member_name"),
                r.get("country_code"),
                r.get("tier_code"),
                str(r.get("enrollment_date")),
                str(r.get("last_flight_date")),
                str(r.get("dob")),
                r.get("age"),
                r.get("days_since_flight"),
                r.get("stale_member"),
                r.get("is_active"),
                r.get("batch_id"),
                r.get("source_file"),
            )
            for r in self.staged_valid_records
        ]
        cur.executemany("INSERT INTO stg_member_profiles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", stg_rows)

        # 2. Country Target Tables
        for tbl_name, recs in self.router.tables.items():
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {tbl_name} (
                    member_id TEXT PRIMARY KEY,
                    member_name TEXT,
                    country_code TEXT,
                    tier_code TEXT,
                    enrollment_date TEXT,
                    last_flight_date TEXT,
                    dob TEXT,
                    age INTEGER,
                    days_since_flight INTEGER,
                    stale_member TEXT,
                    is_active TEXT,
                    source_file TEXT
                )
            """)
            cur.execute(f"DELETE FROM {tbl_name}")
            tbl_rows = [
                (
                    r.get("member_id"),
                    r.get("member_name"),
                    r.get("country_code"),
                    r.get("tier_code"),
                    str(r.get("enrollment_date")),
                    str(r.get("last_flight_date")),
                    str(r.get("dob")),
                    r.get("age"),
                    r.get("days_since_flight"),
                    r.get("stale_member"),
                    r.get("is_active"),
                    r.get("source_file"),
                )
                for r in recs.values()
            ]
            cur.executemany(f"INSERT INTO {tbl_name} VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", tbl_rows)

        # 3. Fact Redemptions Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fact_mileage_redemption (
                redemption_pk TEXT PRIMARY KEY,
                member_id TEXT,
                txn_id TEXT,
                partner_name TEXT,
                txn_date TEXT,
                feed_date TEXT,
                miles_redeemed INTEGER,
                status TEXT,
                source_file TEXT
            )
        """)
        cur.execute("DELETE FROM fact_mileage_redemption")
        red_rows = [
            (
                r.get("redemption_pk"),
                r.get("member_id"),
                r.get("txn_id"),
                r.get("partner_name"),
                str(r.get("txn_date")),
                str(r.get("feed_date")),
                r.get("miles_redeemed"),
                r.get("status"),
                r.get("source_file"),
            )
            for r in self.flattened_redemptions.values()
        ]
        cur.executemany("INSERT INTO fact_mileage_redemption VALUES (?,?,?,?,?,?,?,?,?)", red_rows)

        # 4. Data Quality Quarantine Log
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dq_quarantine_log (
                quarantine_id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id TEXT,
                reason TEXT,
                field_name TEXT,
                source_file TEXT,
                raw_payload TEXT
            )
        """)
        cur.execute("DELETE FROM dq_quarantine_log")
        dq_rows = [
            (
                r.get("dq_rule_id"),
                r.get("dq_reason"),
                r.get("dq_field"),
                r.get("source_file"),
                str(r.get("raw_payload")),
            )
            for r in self.quarantined_records
        ]
        cur.executemany(
            "INSERT INTO dq_quarantine_log (rule_id, reason, field_name, source_file, raw_payload) VALUES (?,?,?,?,?)",
            dq_rows,
        )

        conn.commit()
        conn.close()
