# SkyPoints Loyalty Data Engine — Architecture & Technical Design

## 1. Executive Summary

SkyPoints operates a global airline loyalty program with millions of members worldwide across partner airlines and airport lounges. This repository implements an enterprise-grade, high-throughput data pipeline designed to ingest daily member profile feeds (pipe-delimited flat files and regional exports) and partner mileage redemption streams (semi-structured JSON feeds), validate data quality at the row and batch level, compute analytical metrics (`Age`, `Stale_Member`), and route members into dedicated per-country target tables under strict **"Latest Record Wins"** semantics.

The architecture provides two complementary implementations:
1. **Cloud Production Path (Snowflake)**: Fully set-based, declarative SQL leveraging Snowflake Streams, Tasks, Multi-Table Inserts, and atomic Transactions capable of scaling to billions of records daily.
2. **Local Reference Engine (Python + SQLite)**: An autonomous, zero-external-dependency execution engine and CLI tool designed for reproducible local testing, continuous integration, and live technical interview demonstrations.

---

## 2. End-to-End Pipeline Data Flow

```
                      +---------------------------------------+
                      |       Daily Incoming Data Sources     |
                      +---------------------------------------+
                             |                         |
              +--------------+--------------+          |
              |                             |          |
              v                             v          v
   +-----------------------+     +-------------------+ +---------------------+
   | Global Pipe Flat File |     | Regional Feeds    | | Partner Redemptions |
   | (|H|... |D|...)       |     | (USA, IND, AUS)   | | (Semi-structured    |
   +-----------------------+     +-------------------+ |  JSON Feed)         |
              |                             |          +---------------------+
              | (File Format Validator)     | (Adapters)       |
              +--------------+--------------+                  |
                             |                                 |
                             v                                 v
              +-----------------------------+       +---------------------+
              |      RAW_MEMBER_LANDING     |       | RAW_REDEMPTIONS_JSON|
              |  (Lossless, SHA-256 hash,   |       |  (Payload VARIANT,  |
              |   Audit tracking metadata)  |       |   Batch metadata)   |
              +-----------------------------+       +---------------------+
                             |                                 |
                             | (Type Casting,                  | (JSON Flattening,
                             |  Age / Stale Derivation,        |  Field Parsing)
                             |  DQ Rules Evaluation)           |
                             v                                 v
              +-----------------------------+       +---------------------+
              |     STG_MEMBER_ENRICHED     |       |  STG_REDEMPTIONS    |
              |   - Age (DOB -> Years)      |       |  (One row per txn)  |
              |   - Stale_Member (>90 days) |       +---------------------+
              +-----------------------------+                  |
                     |               |                         |
         (Valid)     |               | (Violations)            |
        +------------+               +------------+            |
        |                                         |            |
        v                                         v            |
+--------------------------------+      +------------------+   |
| CURRENT_MEMBER_REGISTRY        |      | DQ_QUARANTINE_LOG|   |
| (Deterministic Latest-Wins:    |      | (Rule ID, Field, |   |
|  batch_ts + seq_no ordering)   |      |  Severity, Raw)  |   |
+--------------------------------+      +------------------+   |
        |                                                      |
        | (Atomic Upsert / Migration Delete)                   |
        v                                                      |
+------------------------------------------------------+       |
|              Country-Specific Target Tables          |       |
|   +---------------+  +---------------+  +--------+   |       |
|   |  TABLE_INDIA  |  |   TABLE_USA   |  |  ...   |   |       |
|   +---------------+  +---------------+  +--------+   |       |
+------------------------------------------------------+       |
                           |                                   |
                           +-----------------+-----------------+
                                             |
                                             v
                             +-------------------------------+
                             |    ANALYTICS ENRICHED JOIN    |
                             | (Profile + Flattened Txns)    |
                             +-------------------------------+
```

---

## 3. Storage Layering & Responsibilities

| Layer | Snowflake Schema | Primary Purpose | Scalability Technique |
| :--- | :--- | :--- | :--- |
| **RAW / LANDING** | `SKYPOINTS.RAW` | Lossless capture of raw files. Immutability, audit provenance, SHA-256 payload hashing. | Zero transformations; uses external stages & binary COPY. |
| **STAGING** | `SKYPOINTS.STG` | Schema normalization, data cleansing, type conversions, derived attributes (`Age`, `Stale_Member`). | Snowflake Streams tracking CDC; micro-partition pruning. |
| **CURRENT STATE** | `SKYPOINTS.REGISTRY` | Global single source of truth for member identity and latest country location. | Clustered on `MEMBER_ID`; stores `LAST_UPDATED_AT` and `SOURCE_ROW_HASH`. |
| **TARGETS** | `SKYPOINTS.TARGETS` | Physical per-country tables (`TABLE_INDIA`, `TABLE_USA`, etc.) queried by local operational teams. | Filtered physical tables loaded via atomic multi-statement transaction. |
| **REDEMPTIONS** | `SKYPOINTS.CORE` | Queryable flattened redemption transactions (`FACT_REDEMPTION`) joined with member dimensions. | `LATERAL FLATTEN` on JSON arrays with idempotent merge. |
| **DATA QUALITY** | `SKYPOINTS.DQ` | Centralized audit log capturing rejected records, rule IDs, and data drift diagnostics. | Append-only quarantine table. |

---

## 4. Handling Billions of Records Daily

At a scale of billions of records:
1. **Set-Based Transformations**: Eliminates cursor loops or row-by-row iteration in SQL. Every operation uses columnar set logic (`QUALIFY ROW_NUMBER() OVER (...)`).
2. **Deterministic Clustering Keys**: Tables are clustered on `(COUNTRY_CODE, ENROLLMENT_DATE)` or `MEMBER_ID` to optimize partition pruning.
3. **Change Data Capture (CDC)**: Snowflake Streams on Staging tables capture delta changes without re-scanning historical data.
4. **Isolated Country Loading**: Atomic `MERGE` and transactional migrations guarantee that members moving countries are never duplicated or orphaned.
