"""Country routing and atomic 'Latest Record Wins' migration engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .config import COUNTRY_TARGET_TABLES, DEFAULT_TARGET_TABLE


@dataclass
class MemberRegistryEntry:
    member_id: str
    current_country: str
    target_table: str
    version_timestamp: datetime
    source_row_number: int


def get_target_table_name(country_code: str) -> str:
    """Resolve country code to physical target table identifier."""
    return COUNTRY_TARGET_TABLES.get(country_code.upper(), DEFAULT_TARGET_TABLE)


class CountryRouter:
    """Manages country-partitioned target tables and deterministic latest-wins state."""

    def __init__(self):
        # Operational registry: member_id -> MemberRegistryEntry
        self.registry: dict[str, MemberRegistryEntry] = {}
        # Country target stores: table_name -> dict[member_id, record]
        self.tables: dict[str, dict[str, dict[str, Any]]] = {
            t: {} for t in set(COUNTRY_TARGET_TABLES.values())
        }
        self.tables[DEFAULT_TARGET_TABLE] = {}
        # Migration and audit history
        self.migration_events: list[dict[str, Any]] = []

    def route_batch(
        self,
        valid_records: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Route a batch of validated member records applying latest-record-wins.

        Returns summary counts of actions taken.
        """
        # Step 1: Intra-batch deduplication (latest version_timestamp + row_number wins)
        batch_deduped: dict[str, dict[str, Any]] = {}
        for rec in valid_records:
            mid = rec["member_id"]
            if mid not in batch_deduped:
                batch_deduped[mid] = rec
            else:
                existing = batch_deduped[mid]
                incoming_ver = (rec["batch_timestamp"], rec["source_row_number"])
                existing_ver = (existing["batch_timestamp"], existing["source_row_number"])
                if incoming_ver > existing_ver:
                    batch_deduped[mid] = rec

        counts = {
            "inserted": 0,
            "updated": 0,
            "migrated": 0,
            "discarded_outdated": 0,
        }

        # Step 2: Apply against persistent registry
        for mid, rec in batch_deduped.items():
            incoming_country = rec["country_code"]
            target_table = get_target_table_name(incoming_country)
            incoming_ts = rec["batch_timestamp"]
            incoming_row = rec["source_row_number"]
            incoming_ver = (incoming_ts, incoming_row)

            if mid not in self.registry:
                # Scenario A: New Member
                self.tables[target_table][mid] = rec
                self.registry[mid] = MemberRegistryEntry(
                    member_id=mid,
                    current_country=incoming_country,
                    target_table=target_table,
                    version_timestamp=incoming_ts,
                    source_row_number=incoming_row,
                )
                counts["inserted"] += 1

            else:
                current_entry = self.registry[mid]
                current_ver = (current_entry.version_timestamp, current_entry.source_row_number)

                if incoming_ver < current_ver:
                    # Scenario B: Out-of-order / replay file (older than current state)
                    counts["discarded_outdated"] += 1
                    continue

                if incoming_country != current_entry.current_country:
                    # Scenario C: Country Migration! Atomic relocation
                    old_table = current_entry.target_table
                    # Delete from old country table
                    if mid in self.tables[old_table]:
                        del self.tables[old_table][mid]

                    # Insert into new country table
                    self.tables[target_table][mid] = rec

                    # Update registry
                    self.registry[mid] = MemberRegistryEntry(
                        member_id=mid,
                        current_country=incoming_country,
                        target_table=target_table,
                        version_timestamp=incoming_ts,
                        source_row_number=incoming_row,
                    )

                    migration_event = {
                        "member_id": mid,
                        "member_name": rec.get("member_name"),
                        "from_country": current_entry.current_country,
                        "to_country": incoming_country,
                        "old_table": old_table,
                        "new_table": target_table,
                        "timestamp": incoming_ts,
                    }
                    self.migration_events.append(migration_event)
                    counts["migrated"] += 1

                else:
                    # Scenario D: Same Country Update
                    self.tables[target_table][mid] = rec
                    self.registry[mid].version_timestamp = incoming_ts
                    self.registry[mid].source_row_number = incoming_row
                    counts["updated"] += 1

        return counts
