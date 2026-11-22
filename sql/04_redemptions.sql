-- =============================================================================
-- SkyPoints Loyalty Data Engine — Partner Redemption Processing Procedure
-- Deliverable 4: Parse semi-structured JSON into flattened, queryable table
-- Implements latest feed date status update & profile join semantics
-- =============================================================================

USE DATABASE SKYPOINTS_DB;
USE SCHEMA OPS;

CREATE OR REPLACE PROCEDURE OPS.SP_LOAD_REDEMPTIONS_FROM_JSON(P_BATCH_ID VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
BEGIN
    -- Flatten raw JSON array into individual transaction rows
    -- Semi-structured document format:
    -- [
    --   {
    --     "member_id": "223457",
    --     "feed_date": "20240115",
    --     "redemptions": [
    --       { "txn_id": "RX10091", "txn_date": "20240110", "partner": "AeroLink", "miles_redeemed": 12000, "status": "COMPLETED" },
    --       ...
    --     ]
    --   }
    -- ]

    CREATE OR REPLACE TEMPORARY TABLE _TMP_FLATTENED_REDEMPTIONS AS
    SELECT 
        -- Deterministic surrogate key per logical redemption transaction
        SHA2(CONCAT(TRIM(doc.value:member_id::VARCHAR), ':', TRIM(txn.value:partner::VARCHAR), ':', TRIM(txn.value:txn_id::VARCHAR)), 256) AS REDEMPTION_PK,
        TRIM(doc.value:member_id::VARCHAR) AS MEMBER_ID,
        TRIM(txn.value:txn_id::VARCHAR) AS TXN_ID,
        TRY_TO_DATE(TRIM(txn.value:txn_date::VARCHAR), 'YYYYMMDD') AS TXN_DATE,
        TRY_TO_DATE(TRIM(doc.value:feed_date::VARCHAR), 'YYYYMMDD') AS FEED_DATE,
        TRIM(txn.value:partner::VARCHAR) AS PARTNER_NAME,
        TRY_TO_NUMBER(txn.value:miles_redeemed::VARCHAR) AS MILES_REDEEMED,
        UPPER(TRIM(txn.value:status::VARCHAR)) AS STATUS,
        :P_BATCH_ID AS BATCH_ID
    FROM RAW.REDEMPTIONS_JSON_LANDING r,
         LATERAL FLATTEN(input => r.RAW_JSON) doc,
         LATERAL FLATTEN(input => doc.value:redemptions) txn
    WHERE r.BATCH_ID = :P_BATCH_ID
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY REDEMPTION_PK 
        ORDER BY FEED_DATE DESC
    ) = 1;

    -- Upsert into CORE.FACT_MILEAGE_REDEMPTION
    -- If a transaction re-appears on a subsequent feed with updated status (e.g. PENDING -> COMPLETED),
    -- latest feed_date updates status and mileage
    MERGE INTO CORE.FACT_MILEAGE_REDEMPTION target
    USING _TMP_FLATTENED_REDEMPTIONS source
    ON target.REDEMPTION_PK = source.REDEMPTION_PK
    WHEN MATCHED AND source.FEED_DATE >= target.FEED_DATE THEN UPDATE SET
        target.STATUS         = source.STATUS,
        target.MILES_REDEEMED = source.MILES_REDEEMED,
        target.FEED_DATE      = source.FEED_DATE,
        target.BATCH_ID       = source.BATCH_ID,
        target.LOADED_AT      = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT (
        REDEMPTION_PK,
        MEMBER_ID,
        TXN_ID,
        TXN_DATE,
        FEED_DATE,
        PARTNER_NAME,
        MILES_REDEEMED,
        STATUS,
        LOADED_AT,
        BATCH_ID
    ) VALUES (
        source.REDEMPTION_PK,
        source.MEMBER_ID,
        source.TXN_ID,
        source.TXN_DATE,
        source.FEED_DATE,
        source.PARTNER_NAME,
        source.MILES_REDEEMED,
        source.STATUS,
        CURRENT_TIMESTAMP(),
        source.BATCH_ID
    );

    RETURN 'SUCCESS: Partner redemptions flattened and loaded for batch ' || :P_BATCH_ID;
END;
$$;

-- =============================================================================
-- Deliverable 4 (Part 2): Joining Redemptions back to Member Profiles
-- =============================================================================
-- Because members are physically partitioned across country tables, the join
-- leverages CORE.V_GLOBAL_MEMBERS_CONSOLIDATED (or queries specific country tables)
-- =============================================================================

CREATE OR REPLACE VIEW CORE.V_MEMBER_REDEMPTION_SUMMARY AS
SELECT 
    m.MEMBER_ID,
    m.MEMBER_NAME,
    m.COUNTRY_CODE,
    m.TIER_CODE,
    m.AGE,
    m.STALE_MEMBER,
    COUNT(r.TXN_ID) AS TOTAL_REDEMPTIONS_COUNT,
    COALESCE(SUM(r.MILES_REDEEMED), 0) AS TOTAL_MILES_REDEEMED,
    MAX(r.TXN_DATE) AS LATEST_REDEMPTION_DATE
FROM CORE.V_GLOBAL_MEMBERS_CONSOLIDATED m
LEFT JOIN CORE.FACT_MILEAGE_REDEMPTION r
    ON m.MEMBER_ID = r.MEMBER_ID
GROUP BY 
    m.MEMBER_ID,
    m.MEMBER_NAME,
    m.COUNTRY_CODE,
    m.TIER_CODE,
    m.AGE,
    m.STALE_MEMBER;
