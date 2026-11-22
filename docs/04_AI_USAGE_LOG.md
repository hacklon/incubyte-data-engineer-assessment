# AI-Assisted Engineering Log & Decision Record

Incubyte Data Engineer Technical Assessment:
> *"You are required to use AI tools to accelerate your work. We care about how you use them, the clarity of your thinking, and the quality of your engineering decisions."*

This document transparently records how AI acceleration was leveraged, where human critical thinking intervened, and how key engineering decisions were shaped.

---

## 1. Where AI Accelerated Execution

| Workflow Stage | AI Capability Used | Acceleration Impact |
| :--- | :--- | :--- |
| **Boilerplate SQL DDL** | Prompted AI to draft Snowflake DDL structures with standard column definitions across multiple schemas (`RAW`, `STG`, `CORE`, `DQ`, `OPS`). | Reduced repetitive DDL drafting time from ~45 minutes to < 5 minutes. |
| **Test Fixture Generation** | Generated parameterized test cases for diverse date formats (`YYYYMMDD`, `MMDDYYYY`, `YYYY-MM-DD`, `M/D/YYYY`). | Ensured comprehensive boundary condition coverage (leap years, birthday anniversaries, month 13). |
| **Mermaid Flowcharting** | Generated ASCII and Mermaid diagrams illustrating the pipeline stages and country routing flow. | Fast, clean visualization for architecture documentation. |
| **CLI Formatting** | Generated ASCII table formatting logic for console demonstration. | Allowed clean, legible terminal presentation without external third-party formatting dependencies. |

---

## 2. Where Human Engineering Judgment Overruled or Guided AI

| Observation / Trap | Naive AI Output | Human Craftsperson Decision & Fix |
| :--- | :--- | :--- |
| **Primary Key Selection** | Naive AI marked `Member Name` as the primary key because the specification PDF marked `Key Column = Y` for Member Name. | **Rejected**: Member names are non-unique and mutable. Identified that `Member ID` (or namespaced composite key) must be the true immutable primary key. |
| **Schema Drift (10 vs 11 columns)** | Standard AI parsers crashed with `IndexError` when splitting rows because the schema defined 11 columns (with Post Code) but sample detail rows had only 10 columns. | **Engineered**: Designed a schema-drift-tolerant parser that dynamically accommodates missing optional columns, defaulting `post_code` to `NULL` without aborting ingestion. |
| **Billions-Scale Processing** | Naive AI generated full-table replacement queries (`CREATE OR REPLACE TABLE Table_India AS SELECT * FROM Staging WHERE Country = 'IND'`). | **Rejected**: Full table replacement cannot scale to billions of rows. Engineered **set-based incremental loading** via Snowflake Streams, `MERGE INTO`, and micro-batch partitioning. |
| **Country Migration Atomicity** | Naive AI proposed inserting members into the new country table without deleting them from the old table, creating duplication. | **Engineered**: Designed an atomic transaction where relocated members are deleted from their former country table and merged into the active country table within the same transaction scope. |
| **Regional ID Collisions** | Naive AI merged `ID = 1` from USA, Australia, and India CSVs directly, causing catastrophic primary key overwrites. | **Engineered**: Applied source namespacing (`USA-1`, `AUS-1`, `IND-1`) to isolate regional identities from global flat file identifiers. |
| **Dirty Data Handling** | Naive AI threw unhandled exceptions on invalid dates like `2021-13-13`. | **Engineered**: Implemented resilient parsing that catches calendar impossibilities and routes them to a dedicated `DQ_QUARANTINE_LOG` with explicit error codes (`E_INVALID_ENROLLMENT_DATE`). |

---

## 3. Engineering Philosophy & Takeaways

AI is an exceptional multiplier for boilerplate creation, syntax lookups, and test suite expansion. However, **data craftspersonship** requires human vigilance: verifying contracts against dirty data realities, preserving lineage, ensuring idempotent set-based operations, and guaranteeing that zero data is silently lost or corrupted.
