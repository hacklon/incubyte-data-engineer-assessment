-- =============================================================================
-- SkyPoints Loyalty Data Engine — Snowflake DDL Architecture
-- Deliverable 1: Raw/Landing, Staging, Target Country Tables, Redemptions & DQ
-- =============================================================================

CREATE DATABASE IF NOT EXISTS SKYPOINTS_DB;
USE DATABASE SKYPOINTS_DB;

-- Schema Segmentation for Governance & Isolation
CREATE SCHEMA IF NOT EXISTS RAW;       -- Immutable landing layer
CREATE SCHEMA IF NOT EXISTS STG;       -- Normalized & enriched staging layer
CREATE SCHEMA IF NOT EXISTS CORE;      -- Target country tables & dimensional models
CREATE SCHEMA IF NOT EXISTS DQ;        -- Data quality quarantine & audit logs
CREATE SCHEMA IF NOT EXISTS OPS;       -- Orchestration, metadata & pipeline registry

-- =============================================================================
-- 1. RAW / LANDING LAYER (Lossless, Audited)
-- =============================================================================

-- Global Pipe-Delimited Flat File Landing
CREATE OR REPLACE TABLE RAW.MEMBER_PROFILE_LANDING (
    INGESTION_ID        NUMBER AUTOINCREMENT START 1 INCREMENT 1,
    BATCH_ID            VARCHAR(100) NOT NULL,
    SOURCE_FILE_NAME    VARCHAR(500) NOT NULL,
    SOURCE_ROW_NUMBER   NUMBER NOT NULL,
    RECORD_TYPE         VARCHAR(5) NOT NULL, -- 'H' (Header), 'D' (Detail), 'T' (Trailer)
    RAW_PAYLOAD         VARCHAR(4000) NOT NULL,
    PAYLOAD_HASH_SHA256 VARCHAR(64) NOT NULL,
    LOADED_AT           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Semi-Structured Partner Redemption JSON Landing
CREATE OR REPLACE TABLE RAW.REDEMPTIONS_JSON_LANDING (
    INGESTION_ID        NUMBER AUTOINCREMENT START 1 INCREMENT 1,
    BATCH_ID            VARCHAR(100) NOT NULL,
    SOURCE_FILE_NAME    VARCHAR(500) NOT NULL,
    RAW_JSON            VARIANT NOT NULL,
    LOADED_AT           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- =============================================================================
-- 2. STAGING LAYER (Normalized, Typed, Derived Metrics & DQ Evaluated)
-- =============================================================================

CREATE OR REPLACE TABLE STG.MEMBER_PROFILES_ENRICHED (
    STG_ID              NUMBER AUTOINCREMENT START 1 INCREMENT 1,
    BATCH_ID            VARCHAR(100) NOT NULL,
    BATCH_TIMESTAMP     TIMESTAMP_NTZ NOT NULL,
    SOURCE_FILE_NAME    VARCHAR(500) NOT NULL,
    SOURCE_ROW_NUMBER   NUMBER NOT NULL,
    SOURCE_NAMESPACE    VARCHAR(50) DEFAULT 'GLOBAL',
    
    -- Canonical Business Attributes
    MEMBER_ID           VARCHAR(50) NOT NULL,
    MEMBER_NAME         VARCHAR(255) NOT NULL,
    ENROLLMENT_DATE     DATE NOT NULL,
    LAST_FLIGHT_DATE    DATE,
    TIER_CODE           VARCHAR(10),
    AGENT_NAME          VARCHAR(255),
    STATE_CODE          VARCHAR(10),
    COUNTRY_CODE        VARCHAR(10) NOT NULL,
    POST_CODE           VARCHAR(20),
    DATE_OF_BIRTH       DATE,
    IS_ACTIVE           VARCHAR(1) DEFAULT 'A',
    MEMBER_TYPE         VARCHAR(20) DEFAULT 'INDIVIDUAL',
    
    -- Deliverable 2 Derived Columns
    AGE                 NUMBER(3, 0),    -- Derived from DATE_OF_BIRTH
    DAYS_SINCE_FLIGHT   NUMBER(6, 0),    -- Evaluation date - LAST_FLIGHT_DATE
    STALE_MEMBER        VARCHAR(1),      -- 'Y' if DAYS_SINCE_FLIGHT > 90 else 'N'
    
    -- Audit & Quality Flags
    DQ_STATUS           VARCHAR(20) DEFAULT 'VALID', -- 'VALID', 'WARNING', 'QUARANTINED'
    STG_LOADED_AT       TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
CLUSTER BY (COUNTRY_CODE, ENROLLMENT_DATE);

-- Snowflake Stream on Staging for CDC / Delta Processing
CREATE OR REPLACE STREAM STG.MEMBER_PROFILES_STREAM ON TABLE STG.MEMBER_PROFILES_ENRICHED;

-- =============================================================================
-- 3. CORE REGISTRY & COUNTRY TARGET TABLES
-- =============================================================================

-- Global Operational Registry: Tracks active country location & version for latest-wins
CREATE OR REPLACE TABLE CORE.CURRENT_MEMBER_REGISTRY (
    MEMBER_ID           VARCHAR(50) PRIMARY KEY,
    CURRENT_COUNTRY     VARCHAR(10) NOT NULL,
    TARGET_TABLE_NAME   VARCHAR(100) NOT NULL,
    VERSION_TIMESTAMP   TIMESTAMP_NTZ NOT NULL,
    SOURCE_ROW_NUMBER   NUMBER NOT NULL,
    LAST_FLIGHT_DATE    DATE,
    TIER_CODE           VARCHAR(10),
    IS_ACTIVE           VARCHAR(1),
    STALE_MEMBER        VARCHAR(1),
    FIRST_ENROLLED_DATE DATE NOT NULL,
    UPDATED_AT          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
CLUSTER BY (CURRENT_COUNTRY);

-- Macro Template for Country-Specific Target Tables
-- Schema follows normalized staging format
CREATE OR REPLACE TABLE CORE.TABLE_INDIA (
    MEMBER_ID           VARCHAR(50) PRIMARY KEY,
    MEMBER_NAME         VARCHAR(255) NOT NULL,
    ENROLLMENT_DATE     DATE NOT NULL,
    LAST_FLIGHT_DATE    DATE,
    TIER_CODE           VARCHAR(10),
    AGENT_NAME          VARCHAR(255),
    STATE_CODE          VARCHAR(10),
    COUNTRY_CODE        VARCHAR(10) DEFAULT 'IND',
    POST_CODE           VARCHAR(20),
    DATE_OF_BIRTH       DATE,
    AGE                 NUMBER(3, 0),
    DAYS_SINCE_FLIGHT   NUMBER(6, 0),
    STALE_MEMBER        VARCHAR(1),
    IS_ACTIVE           VARCHAR(1),
    LAST_UPDATED_AT     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    SOURCE_BATCH_ID     VARCHAR(100)
);

CREATE OR REPLACE TABLE CORE.TABLE_USA LIKE CORE.TABLE_INDIA;
CREATE OR REPLACE TABLE CORE.TABLE_CANADA LIKE CORE.TABLE_INDIA;
CREATE OR REPLACE TABLE CORE.TABLE_AUSTRALIA LIKE CORE.TABLE_INDIA;
CREATE OR REPLACE TABLE CORE.TABLE_PHILIPPINES LIKE CORE.TABLE_INDIA;
CREATE OR REPLACE TABLE CORE.TABLE_OTHER_COUNTRIES LIKE CORE.TABLE_INDIA;

-- Unified Global View across Country Tables
CREATE OR REPLACE VIEW CORE.V_GLOBAL_MEMBERS_CONSOLIDATED AS
SELECT *, 'TABLE_INDIA' AS SOURCE_TABLE FROM CORE.TABLE_INDIA
UNION ALL
SELECT *, 'TABLE_USA' AS SOURCE_TABLE FROM CORE.TABLE_USA
UNION ALL
SELECT *, 'TABLE_CANADA' AS SOURCE_TABLE FROM CORE.TABLE_CANADA
UNION ALL
SELECT *, 'TABLE_AUSTRALIA' AS SOURCE_TABLE FROM CORE.TABLE_AUSTRALIA
UNION ALL
SELECT *, 'TABLE_PHILIPPINES' AS SOURCE_TABLE FROM CORE.TABLE_PHILIPPINES
UNION ALL
SELECT *, 'TABLE_OTHER_COUNTRIES' AS SOURCE_TABLE FROM CORE.TABLE_OTHER_COUNTRIES;

-- =============================================================================
-- 4. REDEMPTION TRANSACTION TABLES (Deliverable 4)
-- =============================================================================

CREATE OR REPLACE TABLE CORE.FACT_MILEAGE_REDEMPTION (
    REDEMPTION_PK       VARCHAR(100) PRIMARY KEY, -- Hash of (MEMBER_ID, PARTNER, TXN_ID)
    MEMBER_ID           VARCHAR(50) NOT NULL,
    TXN_ID              VARCHAR(50) NOT NULL,
    TXN_DATE            DATE NOT NULL,
    FEED_DATE           DATE NOT NULL,
    PARTNER_NAME        VARCHAR(100) NOT NULL,
    MILES_REDEEMED      NUMBER(12, 0) NOT NULL,
    STATUS              VARCHAR(30) NOT NULL,    -- 'COMPLETED', 'PENDING', 'CANCELLED'
    LOADED_AT           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    BATCH_ID            VARCHAR(100)
)
CLUSTER BY (MEMBER_ID, TXN_DATE);

-- 360-Degree Analytical View Joining Member Profiles with Redemptions
CREATE OR REPLACE VIEW CORE.V_MEMBER_REDEMPTIONS_360 AS
SELECT 
    m.MEMBER_ID,
    m.MEMBER_NAME,
    m.TIER_CODE,
    m.COUNTRY_CODE,
    m.AGE,
    m.STALE_MEMBER,
    r.TXN_ID,
    r.TXN_DATE,
    r.PARTNER_NAME,
    r.MILES_REDEEMED,
    r.STATUS AS REDEMPTION_STATUS,
    r.FEED_DATE
FROM CORE.V_GLOBAL_MEMBERS_CONSOLIDATED m
LEFT JOIN CORE.FACT_MILEAGE_REDEMPTION r
    ON m.MEMBER_ID = r.MEMBER_ID;

-- =============================================================================
-- 5. DATA QUALITY & QUARANTINE LOG (Deliverable 5)
-- =============================================================================

CREATE OR REPLACE TABLE DQ.QUARANTINE_RECORDS (
    QUARANTINE_ID       NUMBER AUTOINCREMENT START 1 INCREMENT 1,
    BATCH_ID            VARCHAR(100) NOT NULL,
    SOURCE_FILE_NAME    VARCHAR(500) NOT NULL,
    SOURCE_ROW_NUMBER   NUMBER,
    RULE_ID             VARCHAR(50) NOT NULL,
    SEVERITY            VARCHAR(20) NOT NULL,    -- 'BLOCKING', 'WARNING'
    FIELD_NAME          VARCHAR(50),
    INVALID_VALUE       VARCHAR(500),
    REASON              VARCHAR(1000) NOT NULL,
    RAW_PAYLOAD         VARCHAR(4000),
    DETECTED_AT         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
