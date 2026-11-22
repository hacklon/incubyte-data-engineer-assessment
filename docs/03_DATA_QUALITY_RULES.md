# Data Quality Rule Catalogue

The SkyPoints Data Engine enforces strict data hygiene. Violations are logged into the `DQ_QUARANTINE_LOG` with standardized rule identifiers, categorization, and severity.

## Severity Levels:
- **BLOCKING (E_*)**: Row is rejected from staging and target tables; saved to quarantine for triage.
- **WARNING (W_*)**: Row is allowed into staging with default/null values; logged for monitoring.
- **BATCH (B_*)**: File/batch level integrity check.

---

## 1. Row-Level Rules (Member Profiles)

| Rule ID | Category | Severity | Description | Action / Recovery |
| :--- | :--- | :--- | :--- | :--- |
| `E_MANDATORY_NULL` | Completeness | BLOCKING | Mandatory field (`MEMBER_ID`, `MEMBER_NAME`, `ENROLLMENT_DATE`) is NULL or blank. | Reject row to quarantine. |
| `E_INVALID_DATE` | Validity | BLOCKING | Date field contains invalid format, impossible calendar day (e.g. `2021-13-13`), or unparseable text. | Reject row to quarantine. |
| `E_INVALID_COUNTRY` | Validity | BLOCKING | Country code cannot be mapped to a known ISO country standard. | Reject row to quarantine. |
| `E_FUTURE_DATE` | Consistency | BLOCKING | Enrollment Date or Last Flight Date is in the future relative to batch timestamp. | Reject row to quarantine. |
| `E_DOB_AFTER_ENROLL` | Consistency | BLOCKING | Date of Birth is chronologically after Enrollment Date. | Reject row to quarantine. |
| `W_MISSING_OPTIONAL`| Completeness | WARNING | Optional field (`TIER_CODE`, `AGENT_NAME`, `STATE`, `POST_CODE`) is missing. | Default to NULL; allow processing. |
| `W_SCHEMA_DRIFT` | Schema | WARNING | Incoming row token count differs from design specification (e.g., 10 tokens vs 11). | Fill missing with NULL; log warning. |
| `W_STALE_FLIGHT` | Business | WARNING | Last Flight Date > 90 days from evaluation date (`STALE_MEMBER = 'Y'`). | Analytical flag set; allow processing. |
| `W_NEGATIVE_AGE` | Validity | WARNING | Calculated age evaluates to negative (invalid DOB). | Set Age to NULL; log warning. |

---

## 2. Row-Level Rules (Redemption JSON Feed)

| Rule ID | Category | Severity | Description | Action / Recovery |
| :--- | :--- | :--- | :--- | :--- |
| `E_REDEMPTION_NO_TXN` | Completeness | BLOCKING | Missing `txn_id` or transaction payload in JSON array. | Reject transaction. |
| `E_REDEMPTION_NO_MEMBER`| Referential | BLOCKING | Missing or null `member_id` in parent JSON object. | Reject entire document. |
| `E_REDEMPTION_NEG_MILES`| Validity | BLOCKING | `miles_redeemed` is negative or non-numeric. | Reject transaction. |
| `E_REDEMPTION_BAD_STATUS`| Validity | WARNING | Status is not in `['COMPLETED', 'PENDING', 'CANCELLED']`. | Flag for operational review. |

---

## 3. Batch & Pipeline Integrity Rules

| Rule ID | Category | Severity | Description | Action / Recovery |
| :--- | :--- | :--- | :--- | :--- |
| `B_EMPTY_FILE` | Ingestion | BLOCKING | Input file contains 0 bytes or header only. | Alert on empty batch. |
| `B_DUPLICATE_BATCH` | Ingestion | BLOCKING | File hash has already been processed (idempotency guard). | Skip duplicate processing. |
| `B_MEMBER_ORPHANED` | Referential | WARNING | Redemption points to a member ID not yet present in member profile tables. | Log for late-arriving dimension join. |
