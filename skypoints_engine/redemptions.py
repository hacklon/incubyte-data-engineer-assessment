"""Semi-structured JSON redemption feed parser, flattener, and member profile joiner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .dates import parse_flexible_date


def compute_redemption_key(member_id: str, partner: str, txn_id: str) -> str:
    """Generate deterministic hash key for a redemption transaction."""
    raw = f"{member_id.strip()}:{partner.strip()}:{txn_id.strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def parse_and_flatten_redemptions(
    file_path: str | Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse semi-structured JSON feed and explode array into flattened rows.

    Returns:
      (valid_transactions, rejected_records)
    """
    path = Path(file_path)
    with open(path, mode="r", encoding="utf-8") as f:
        payload = json.load(f)

    # Wrap single dictionary in list if needed
    if isinstance(payload, dict):
        documents = [payload]
    elif isinstance(payload, list):
        documents = payload
    else:
        documents = []

    valid_txns: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for doc in documents:
        member_id = str(doc.get("member_id") or "").strip()
        feed_date_raw = str(doc.get("feed_date") or "").strip()
        feed_date = parse_flexible_date(feed_date_raw)

        if not member_id:
            rejected.append({
                "rule_id": "E_REDEMPTION_NO_MEMBER",
                "reason": "Missing member_id in redemption document",
                "payload": doc,
            })
            continue

        redemptions_list = doc.get("redemptions") or []
        for txn in redemptions_list:
            txn_id = str(txn.get("txn_id") or "").strip()
            partner = str(txn.get("partner") or "").strip()
            txn_date = parse_flexible_date(txn.get("txn_date"))
            miles = txn.get("miles_redeemed")
            status = str(txn.get("status") or "UNKNOWN").strip().upper()

            # Validation checks
            if not txn_id:
                rejected.append({
                    "rule_id": "E_REDEMPTION_NO_TXN",
                    "reason": "Missing txn_id in transaction item",
                    "payload": txn,
                })
                continue

            try:
                miles_int = int(miles)
                if miles_int < 0:
                    rejected.append({
                        "rule_id": "E_REDEMPTION_NEG_MILES",
                        "reason": f"Negative miles redeemed: {miles_int}",
                        "payload": txn,
                    })
                    continue
            except (ValueError, TypeError):
                rejected.append({
                    "rule_id": "E_REDEMPTION_INVALID_MILES",
                    "reason": f"Non-numeric miles redeemed: {miles}",
                    "payload": txn,
                })
                continue

            pk = compute_redemption_key(member_id, partner, txn_id)
            valid_txns.append({
                "redemption_pk": pk,
                "member_id": member_id,
                "txn_id": txn_id,
                "txn_date": txn_date,
                "feed_date": feed_date,
                "partner_name": partner,
                "miles_redeemed": miles_int,
                "status": status,
                "source_file": path.name,
            })

    return valid_txns, rejected


def join_redemptions_with_members(
    redemptions: list[dict[str, Any]],
    member_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Join flattened redemption transactions back to member profiles (Deliverable 4)."""
    joined = []
    for r in redemptions:
        mid = r["member_id"]
        member_profile = member_lookup.get(mid, {})

        joined_record = {
            "redemption_pk": r["redemption_pk"],
            "member_id": mid,
            "member_name": member_profile.get("member_name", "UNKNOWN"),
            "country_code": member_profile.get("country_code", "UNKNOWN"),
            "tier_code": member_profile.get("tier_code", "UNKNOWN"),
            "age": member_profile.get("age"),
            "stale_member": member_profile.get("stale_member", "UNKNOWN"),
            "txn_id": r["txn_id"],
            "txn_date": r["txn_date"],
            "partner_name": r["partner_name"],
            "miles_redeemed": r["miles_redeemed"],
            "status": r["status"],
            "feed_date": r["feed_date"],
        }
        joined.append(joined_record)
    return joined
