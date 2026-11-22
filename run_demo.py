#!/usr/bin/env python3
"""Interactive Live Demonstration Script for SkyPoints Data Engine.

Incubyte Data Engineer Technical Assessment Live Demo.
Executes end-to-end ingestion, validation, country partitioning,
country relocation (Elena: USA -> IND), and JSON redemption joins.

Usage:
    python run_demo.py [--as-of YYYY-MM-DD] [--db output/skypoints.db]
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

from skypoints_engine.pipeline import SkyPointsPipeline

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data" / "raw"
DEFAULT_DB = ROOT_DIR / "output" / "skypoints.db"


def print_banner(text: str) -> None:
    line = "=" * 78
    print(f"\n{line}\n  {text}\n{line}")


def print_section(title: str) -> None:
    print(f"\n--- {title} ---")


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format and print an ASCII table with aligned columns."""
    if not rows:
        return "(No rows)"
    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, val in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(str(val)))

    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    sep_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    data_lines = [
        " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row))
        for row in rows
    ]
    return f"{header_line}\n{sep_line}\n" + "\n".join(data_lines)


def run_demonstration(as_of_str: str = "2024-01-15", db_path: Path = DEFAULT_DB) -> None:
    as_of = date.fromisoformat(as_of_str)
    pipeline = SkyPointsPipeline(as_of=as_of)

    print_banner("SKYPOINTS AIRLINE LOYALTY DATA ENGINE — LIVE DEMO")
    print(f"Target Database   : {db_path}")
    print(f"Evaluation As-Of  : {as_of}")

    # =========================================================================
    # STEP 1: Process Day 1 Global Flat File Feed
    # =========================================================================
    day1_file = DATA_DIR / "skypoints_members_20240115_060000.dat"
    print_section(f"STEP 1: Ingesting Global Flat File ({day1_file.name})")
    stats1 = pipeline.process_member_file(day1_file)
    print(f"  [+] Ingested Rows    : {stats1['total_raw']}")
    print(f"  [+] Staged Valid     : {stats1['valid_staged']}")
    print(f"  [+] Quarantined      : {stats1['quarantined']}")
    print(f"  [+] Target Inserts   : {stats1['inserted']}")

    # =========================================================================
    # STEP 2: Process Regional Feeds (USA, AUS, IND)
    # =========================================================================
    print_section("STEP 2: Ingesting Heterogeneous Regional Country Feeds")
    for fname, country in [("regional_usa.csv", "USA"), ("regional_aus.csv", "AUS"), ("regional_ind.csv", "IND")]:
        fpath = DATA_DIR / fname
        res = pipeline.process_regional_csv(fpath, country)
        print(f"  [+] {fname:16} ({country}): {res['valid_staged']} valid, {res['quarantined']} quarantined")

    # =========================================================================
    # STEP 3: Display Staging & Derived Metrics (Deliverable 2)
    # =========================================================================
    print_section("STEP 3: Staging Layer with Derived Columns (Age, Stale_Member)")
    stg_headers = ["Member ID", "Name", "Country", "Tier", "DOB", "Age", "Last Flight", "Days", "Stale?"]
    stg_rows = [
        [
            r.get("member_id"),
            r.get("member_name"),
            r.get("country_code"),
            r.get("tier_code") or "-",
            str(r.get("dob") or "-"),
            str(r.get("age") if r.get("age") is not None else "-"),
            str(r.get("last_flight_date") or "-"),
            str(r.get("days_since_flight") if r.get("days_since_flight") is not None else "-"),
            r.get("stale_member"),
        ]
        for r in pipeline.staged_valid_records[:8]
    ]
    print(format_table(stg_headers, stg_rows))
    print("  * Notice: Age computed from DOB; Stale_Member = 'Y' where days > 90.")

    # =========================================================================
    # STEP 4: Display Partitioned Country Tables (Deliverable 3)
    # =========================================================================
    print_section("STEP 4: Per-Country Target Partitioning")
    for tbl_name in ["table_usa", "table_india", "table_australia", "table_canada", "table_philippines"]:
        members = pipeline.router.tables[tbl_name]
        m_list = ", ".join(f"{m['member_name']} ({m['member_id']})" for m in members.values())
        print(f"  [Table: {tbl_name.upper():20}] {len(members)} members -> {m_list}")

    # =========================================================================
    # STEP 5: Ingest & Flatten Partner JSON Redemptions (Deliverable 4)
    # =========================================================================
    day1_json = DATA_DIR / "redemptions_20240115.json"
    print_section(f"STEP 5: Partner JSON Redemptions Ingestion ({day1_json.name})")
    json_stats = pipeline.process_redemptions_json(day1_json)
    print(f"  [+] Exploded Transactions : {json_stats['valid_txns']}")
    print(f"  [+] Active Stored Txns    : {json_stats['total_active_txns']}")

    # Display 360-degree joined view
    print("\n  Flattened Redemptions Joined to Member Profile:")
    joined_360 = pipeline.get_enriched_redemptions_360()
    j_headers = ["Txn ID", "Member Name", "Country", "Tier", "Partner", "Miles", "Status", "Txn Date"]
    j_rows = [
        [
            j["txn_id"],
            j["member_name"],
            j["country_code"],
            j["tier_code"],
            j["partner_name"],
            f"{j['miles_redeemed']:,}",
            j["status"],
            str(j["txn_date"]),
        ]
        for j in joined_360
    ]
    print(format_table(j_headers, j_rows))

    # =========================================================================
    # STEP 6: Country Migration Demonstration ("Latest Record Wins")
    # =========================================================================
    print_section("STEP 6: ATOMIC COUNTRY MIGRATION (Day 2 Feed: Elena moves USA -> IND)")
    print("  Before Day 2 Feed:")
    print(f"    - In TABLE_USA   : {'223457' in pipeline.router.tables['table_usa']} (Elena present)")
    print(f"    - In TABLE_INDIA : {'223457' in pipeline.router.tables['table_india']} (Elena absent)")

    day2_file = DATA_DIR / "skypoints_members_20240116_060000.dat"
    stats2 = pipeline.process_member_file(day2_file)
    print(f"\n  Processing {day2_file.name} (Elena updated with Country=IND, plus new member Hans)...")
    print(f"  [+] Migrations Applied   : {stats2['migrated']}")
    print(f"  [+] New Members Added    : {stats2['inserted']}")

    print("\n  After Day 2 Feed:")
    print(f"    - In TABLE_USA   : {'223457' in pipeline.router.tables['table_usa']} (Deleted from old country table!)")
    print(f"    - In TABLE_INDIA : {'223457' in pipeline.router.tables['table_india']} (Active in new country table!)")

    # Ingest Day 2 Redemptions (Status transition: PENDING -> COMPLETED)
    day2_json = DATA_DIR / "redemptions_20240116.json"
    pipeline.process_redemptions_json(day2_json)
    rx92 = pipeline.flattened_redemptions.get("223457:SkyPoints:RX10092")
    if rx92:
        print(f"  [+] Transaction RX10092 Status Transition: -> {rx92['status']}")

    # =========================================================================
    # STEP 7: Data Quality & Quarantine Audit Log (Deliverable 5)
    # =========================================================================
    print_section("STEP 7: Data Quality Quarantine Log (Rejections Caught)")
    dq_headers = ["Rule ID", "Reason", "Source File"]
    dq_rows = [
        [
            q.get("dq_rule_id") or "UNKNOWN",
            q.get("dq_reason") or "-",
            q.get("source_file") or "-",
        ]
        for q in pipeline.quarantined_records
    ]
    print(format_table(dq_headers, dq_rows))
    print("  * Notice: Jonnathan rejected for '2021-13-13' (month 13); pipeline integrity preserved.")

    # =========================================================================
    # STEP 8: Export Database
    # =========================================================================
    pipeline.export_to_sqlite(db_path)
    print_section(f"STEP 8: State Persisted to SQLite Database -> {db_path}")
    print("  Tables Created: stg_member_profiles, table_india, table_usa, table_australia,")
    print("                 table_canada, table_philippines, fact_mileage_redemption, dq_quarantine_log")

    print_banner("DEMONSTRATION COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SkyPoints ETL Interactive Live Demo")
    parser.add_argument("--as-of", default="2024-01-15", help="Evaluation as-of date (YYYY-MM-DD)")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Output SQLite DB path")
    args = parser.parse_args()

    run_demonstration(as_of_str=args.as_of, db_path=Path(args.db))
