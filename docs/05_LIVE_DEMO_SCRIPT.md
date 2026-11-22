# SkyPoints Live Interview Demonstration Script

This script provides a step-by-step walkthrough to present this technical assessment during the Incubyte technical interview.

---

## 1. Opening Statement (1 Minute Pitch)

> *"Hi everyone. For the SkyPoints assessment, I focused on three pillars: **billions-scale set-based architecture**, **data quality resilience**, and **atomic country migration**.*
>
> *I built two parallel implementations: a production-grade **Snowflake SQL suite** utilizing Streams, Tasks, and transactional MERGE operations for cloud scale, and a zero-dependency **Python reference engine** with an automated CLI demo and 30 unit tests for local verification.*
>
> *Let's run the interactive live demo to see the end-to-end pipeline in action."*

---

## 2. Command to Run

Open your terminal in `F:\Incubyte` and execute:

```bash
python run_demo.py
```

*(Alternatively, to run the automated unit test suite: `python -m unittest discover -s tests -v`)*

---

## 3. Step-by-Step Talking Points during the Demo

### Step 1 & 2: Ingestion & Regional Schema Adaptation
- **What is happening**: Ingesting the global pipe-delimited flat file and three heterogeneous regional CSV files (USA, Australia, India).
- **Key Talking Point**: 
  - *"Notice that the regional feeds use different column headers (e.g., `Unique ID` vs `ID`, `Date of Birth` vs `DOB`) and local surrogate IDs. To avoid primary key collision, our adapter namespaces local keys (e.g. `USA-1`, `AUS-1`, `IND-1`)."*

### Step 3: Staging Layer & Derived Metrics (Deliverable 2)
- **What is happening**: Computing `Age` from Date of Birth and `Stale_Member` flag.
- **Key Talking Point**:
  - *"In Step 3, you can see our staging table. We calculate `Age` in completed calendar years with full leap-year support. For `Stale_Member`, we calculate days since the last flight: if days > 90, the flag evaluates to `Y`; otherwise `N`."*

### Step 4: Per-Country Target Partitioning (Deliverable 3)
- **What is happening**: Distributing members into physical country tables (`TABLE_USA`, `TABLE_INDIA`, `TABLE_AUSTRALIA`, etc.).
- **Key Talking Point**:
  - *"Members are partitioned into dedicated country target tables. For example, Elena is currently living in the USA, so she is registered in `TABLE_USA`."*

### Step 5: Semi-Structured JSON Redemptions & Profile Join (Deliverable 4)
- **What is happening**: Parsing the nested partner redemption feed and flattening the array into individual transaction rows.
- **Key Talking Point**:
  - *"We ingest the semi-structured partner JSON feed. In Snowflake, this is handled via `LATERAL FLATTEN`; in Python, our flattener generates a deterministic composite key `(member_id + partner + txn_id)`. We join redemptions back to member profiles to form a unified 360-degree analytical view."*

### Step 6: Atomic Country Migration ("Latest Record Wins")
- **What is happening**: Ingesting Day 2 feed where Elena moves from USA to India!
- **Key Talking Point**:
  - *"This is one of the most critical requirements in the brief. On Day 2, Elena relocates from the USA to India. Look at the before and after state: Elena is deleted from `TABLE_USA` and inserted into `TABLE_INDIA` atomically. She never exists in two country tables at the same time."*
  - *"Additionally, transaction `RX10092` transitioned from `PENDING` to `COMPLETED`, demonstrating how latest feed timestamps update transaction state idempotently."*

### Step 7: Data Quality Quarantine Log (Deliverable 5)
- **What is happening**: Displaying quarantined records that violated quality checks.
- **Key Talking Point**:
  - *"We never lose data silently. In `regional_aus.csv`, Jonnathan's enrollment date was `2021-13-13` — an invalid month 13. Rather than failing the pipeline or corrupting target tables, the record was quarantined with rule ID `E_INVALID_ENROLLMENT_DATE` for operational triage."*

### Step 8: Persistence & SQLite Verification
- **What is happening**: Exporting pipeline state to `output/skypoints.db`.
- **Key Talking Point**:
  - *"All tables are persisted to SQLite so interviewers can run ad-hoc verification queries directly."*
