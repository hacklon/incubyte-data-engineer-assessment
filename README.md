# SkyPoints Airline Loyalty Data Engine

> **Incubyte Data Engineer Technical Assessment**  
> An enterprise-grade, high-throughput data engineering pipeline designed to ingest daily member profile feeds (pipe-delimited flat files and regional exports) and partner mileage redemptions (semi-structured JSON feeds), validate data quality at the row and batch level, compute analytical metrics (`Age`, `Stale_Member`), and partition members into per-country target tables under strict **"Latest Record Wins"** semantics at a design scale of billions of records daily.

---

## 1. Quick Start & Live Demonstration

The engine uses Python 3.9+ standard library with **zero external dependency installations required** for runtime or testing.

### Run the Interactive Live Demo:
```bash
python run_demo.py
```
*(Executes end-to-end ingestion, staging enrichment, country partitioning, country migration where Elena moves USA -> India, JSON flattening, and persists state to `output/skypoints.db`)*

### Run Automated Unit & Regression Tests (30 Tests):
```bash
python -m unittest discover -s tests -v
```
*(Or via `pytest -v` if installed)*

---

## 2. Assessment Deliverables Matrix

| # | Assessment Deliverable | Production Snowflake Path | Local Python Reference Path |
| :-: | :--- | :--- | :--- |
| **1** | **Table DDLs** (Raw/Landing, Staging, Country Targets) | [`sql/01_snowflake_ddl.sql`](sql/01_snowflake_ddl.sql) | [`skypoints_engine/pipeline.py`](skypoints_engine/pipeline.py) |
| **2** | **Staging Derived Columns** (`Age`, `Stale_Member` > 90d) | [`sql/02_load_staging.sql`](sql/02_load_staging.sql) | [`skypoints_engine/dates.py`](skypoints_engine/dates.py) |
| **3** | **Country Routing & "Latest Record Wins"** (Country Moves) | [`sql/03_split_by_country.sql`](sql/03_split_by_country.sql) | [`skypoints_engine/router.py`](skypoints_engine/router.py) |
| **4** | **JSON Redemption Flattening & Member Join** | [`sql/04_redemptions.sql`](sql/04_redemptions.sql) | [`skypoints_engine/redemptions.py`](skypoints_engine/redemptions.py) |
| **5** | **Data Quality & Validation Suite** | [`sql/05_data_quality_validations.sql`](sql/05_data_quality_validations.sql) | [`skypoints_engine/validator.py`](skypoints_engine/validator.py) |
| **6** | **Live Interview Demonstration** | [Interview Script](docs/05_LIVE_DEMO_SCRIPT.md) | [`run_demo.py`](run_demo.py) |

---

## 3. High-Level Architecture

```
                    +------------------------------------+
                    |    Daily Incoming Source Feeds     |
                    +------------------------------------+
                               |                  |
           +-------------------+                  |
           |                                      |
           v                                      v
  +------------------+                   +------------------+
  | Global Flat File |                   |  Redemption JSON |
  | & Regional Feeds |                   |  (Partner Feed)  |
  +------------------+                   +------------------+
           |                                      |
           v                                      v
  +------------------+                   +------------------+
  |  RAW_LANDING     |                   |  RAW_JSON        |
  |  (Lossless, Hash)|                   |  (Variant)       |
  +------------------+                   +------------------+
           |                                      |
           | (Age & Stale Derivation,             | (LATERAL FLATTEN,
           |  DQ Rule Evaluation)                 |  Key Hashing)
           v                                      v
  +------------------+                   +------------------+
  |  STG_ENRICHED    |                   |  FACT_REDEMPTION |
  +------------------+                   +------------------+
       |          |                                |
(Valid)|          |(Violations)                    |
       v          v                                |
+-------------+ +------------------+               |
| REGISTRY    | | QUARANTINE_LOG   |               |
| (Latest-Wins| | (E_INVALID_DATE, |               |
|  Atomic Move| |  E_MANDATORY_NULL|               |
+-------------+ +------------------+               |
       |                                           |
       v                                           v
+-------------------------------+        +----------------------+
| Country Partitioned Targets   | -----> | V_MEMBER_REDEMPTIONS |
| TABLE_INDIA, TABLE_USA, ...   | (Join) | 360 Analytical View  |
+-------------------------------+        +----------------------+
```

---

## 4. Key Architectural Decisions

1. **Billions-Scale Processing**: The Snowflake design utilizes **set-based incremental streams and tasks**, avoiding cursor-based or row-by-row iteration. Clustering keys on `(COUNTRY_CODE, ENROLLMENT_DATE)` optimize micro-partition pruning.
2. **Atomic Country Migration**: When a member relocates (e.g. Elena moves USA $\rightarrow$ India), an atomic multi-statement transaction deletes her record from `TABLE_USA` and merges her record into `TABLE_INDIA`. This guarantees zero window of duplication.
3. **Resilience to Schema Drift**: Accommodates discrepancies between the design specification (11 columns with Post Code) and sample flat file records (10 columns omitting Post Code) without aborting ingestion.
4. **Data Quality Quarantine**: Bad rows (such as Jonnathan's enrollment date with month 13 `2021-13-13` in `regional_aus.csv`) are safely routed to `DQ_QUARANTINE_LOG` with explicit error codes (`E_INVALID_ENROLLMENT_DATE`).
5. **Namespaced Identity Resolution**: Regional feeds (`USA.csv`, `IND.csv`, `AUS.csv`) use local surrogate sequences (`ID=1`). The engine namespaces regional keys (`USA-1`, `IND-1`, `AUS-1`) to prevent primary key collision.

---

## 5. Documentation Index

- [**01. Architecture & Design**](docs/01_ARCHITECTURE.md) — Multi-layer data lakehouse design, data flow, and scaling rationale.
- [**02. Decisions & Trade-Offs**](docs/02_DECISIONS_AND_TRADEOFFS.md) — Analysis of primary keys, schema drift, and migration mechanics.
- [**03. Data Quality Rule Catalogue**](docs/03_DATA_QUALITY_RULES.md) — Comprehensive index of `E_*` (blocking) and `W_*` (warning) data rules.
- [**04. AI Usage & Decision Record**](docs/04_AI_USAGE_LOG.md) — Transparent audit log of AI acceleration and human engineering decisions.
- [**05. Live Demo Script**](docs/05_LIVE_DEMO_SCRIPT.md) — Step-by-step interview presentation talking points.

---

## 6. Repository Structure

```text
F:\Incubyte\
├── README.md                          # Executive project summary & deliverables matrix
├── requirements.txt                   # Environment dependencies
├── run_demo.py                        # Interactive CLI live demonstration runner
├── docs/                              # Comprehensive documentation suite
│   ├── 01_ARCHITECTURE.md
│   ├── 02_DECISIONS_AND_TRADEOFFS.md
│   ├── 03_DATA_QUALITY_RULES.md
│   ├── 04_AI_USAGE_LOG.md
│   └── 05_LIVE_DEMO_SCRIPT.md
├── sql/                               # Production Snowflake Deliverables
│   ├── 01_snowflake_ddl.sql           # Landing, staging, targets, registry, fact DDL
│   ├── 02_load_staging.sql            # Age & Stale derivation procedure + quarantine
│   ├── 03_split_by_country.sql        # Atomic country target router & migration
│   ├── 04_redemptions.sql             # JSON LATERAL FLATTEN & member profile join view
│   └── 05_data_quality_validations.sql# Automated DQ validation & reconciliation queries
├── skypoints_engine/                  # Local Executable Reference Engine
│   ├── __init__.py
│   ├── config.py                      # Country mappings, tiers, threshold configs
│   ├── dates.py                       # Robust date parsing, age, and stale flags
│   ├── parsers.py                     # Pipe-delimited flat file parser (schema drift tolerant)
│   ├── validator.py                   # Data quality validation & enrichment engine
│   ├── router.py                      # Country target routing & atomic latest-wins state
│   ├── redemptions.py                 # JSON flattener & member 360 profile joiner
│   ├── adapters.py                    # Regional CSV feed adapters & ID namespacer
│   └── pipeline.py                    # End-to-end batch orchestrator & SQLite exporter
├── data/
│   └── raw/                           # Sample input feeds (flat files, JSON, regional CSVs)
└── tests/                             # Full Unit & Regression Test Suite (30 Tests)
    ├── test_dates.py
    ├── test_parsers.py
    ├── test_router.py
    ├── test_redemptions.py
    ├── test_adapters.py
    └── test_pipeline_e2e.py
```
