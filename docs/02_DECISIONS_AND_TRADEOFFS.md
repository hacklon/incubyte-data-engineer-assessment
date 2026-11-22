# Architectural Decisions & Engineering Trade-Offs

## 1. Primary Key Contract vs Business Reality
- **Observation**: The design specification marks `Member Name` as mandatory and key (`Key Column = Y`), while `Member ID` is marked `Key Column = N`.
- **Engineering Decision**: In production, `Member ID` (or a namespaced composite `source_namespace + member_id`) must serve as the true immutable primary key. Member names are not unique (thousands of people share the same name) and are mutable (marriage, name changes). 
- **Handling**: We enforce `MEMBER_ID` uniqueness in the current state registry while validating that `MEMBER_NAME` is strictly non-null.

## 2. The 10-Column vs 11-Column Schema Drift
- **Observation**: The field layout table defines 11 columns including `Post Code` (position 9). However, the sample header (`|H|...`) and detail records (`|D|...`) contain only 10 fields, omitting Post Code entirely.
- **Engineering Decision**: The parsing engine must be resilient to schema drift. We parse the tokens dynamically from the header layout. If `Post Code` is omitted in the file, it defaults gracefully to `NULL` with an informational audit warning (`W_SCHEMA_DRIFT_MISSING_POSTCODE`) instead of failing the pipeline.

## 3. Date Parsing & Formats
- **Observation**: The data exhibits heterogeneous date patterns:
  - Flat file: `20101012` (YYYYMMDD) and `03051985` (MMDDYYYY vs DDMMYYYY).
  - Regional feeds: `6152022` (M-DD-YYYY), `12/1/1998` (M/D/YYYY), and erroneous dates like `2021-13-13` (Month 13).
- **Engineering Decision**: Implement a multi-format date parser with strict validation. If month > 12 or day > 31 or the date fails calendar validation, the row is rejected to quarantine (`E_INVALID_DATE_FORMAT`) rather than corrupting analytics.

## 4. "Latest Record Wins" Disambiguation
- **Observation**: Multiple records for a member may arrive within the same daily feed, across feeds, or due to out-of-order replayed files.
- **Engineering Decision**: Record version priority is evaluated as a composite deterministic tuple:
  `version_tuple = (file_batch_timestamp, source_sequence_number)`
  When processing a batch:
  1. **Intra-batch deduplication**: `QUALIFY ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY batch_timestamp DESC, sequence_number DESC) = 1`.
  2. **Inter-batch comparison**: Incoming records are only merged if their `version_tuple` is strictly greater than or equal to the registered version.

## 5. Country Migration Mechanics
- **Observation**: When a member relocates (e.g. Elena moves from USA to IND), they must only exist in their current country table.
- **Engineering Decision**: In Snowflake, migration is handled inside an atomic transaction:
  1. Identify moving members where `incoming_country != current_registered_country`.
  2. `DELETE FROM <old_country_table> WHERE member_id IN (moved_ids)`.
  3. `MERGE INTO <new_country_table> ...`.
  4. Update `CURRENT_MEMBER_REGISTRY`.
  This guarantees zero window of duplication across country tables.

## 6. Multi-Source ID Namespacing
- **Observation**: Regional feeds (USA.csv, IND.csv, AUS.csv) utilize local surrogate sequences (e.g., `ID = 1`). Joining them with global flat file IDs would trigger catastrophic collision.
- **Engineering Decision**: Prefix regional identifiers with a canonical namespace:
  - Global flat file: `GLOBAL-<ID>` (or bare `<ID>` if preserved)
  - Regional USA: `USA-1`
  - Regional India: `IND-1`
  - Regional Australia: `AUS-1`
