-- =============================================================================
-- SkyPoints Loyalty Data Engine — Automated Data Quality Validations
-- Deliverable 5: Mandatory Field Checks, Key Uniqueness & Sample Anomaly Diagnostics
-- =============================================================================

USE DATABASE SKYPOINTS_DB;
USE SCHEMA DQ;

-- Diagnostic validation query suite.
-- Each query is designed to return ZERO rows in a healthy state. Any returned row indicates an anomaly.

-- 1. Check Mandatory Fields in Staging & Target Tables
SELECT 
    'CHECK_MANDATORY_FIELDS' AS VALIDATION_NAME,
    'BLOCKING' AS SEVERITY,
    MEMBER_ID,
    MEMBER_NAME,
    COUNTRY_CODE,
    'Missing mandatory field' AS FAILURE_REASON
FROM STG.MEMBER_PROFILES_ENRICHED
WHERE MEMBER_ID IS NULL OR TRIM(MEMBER_ID) = ''
   OR MEMBER_NAME IS NULL OR TRIM(MEMBER_NAME) = ''
   OR ENROLLMENT_DATE IS NULL
   OR COUNTRY_CODE IS NULL OR TRIM(COUNTRY_CODE) = '';

-- 2. Check Key-Column Uniqueness in Current Member Registry
SELECT 
    'CHECK_REGISTRY_KEY_UNIQUENESS' AS VALIDATION_NAME,
    'BLOCKING' AS SEVERITY,
    MEMBER_ID,
    COUNT(*) AS OCCURRENCE_COUNT,
    'Duplicate Member ID found in Global Registry' AS FAILURE_REASON
FROM CORE.CURRENT_MEMBER_REGISTRY
GROUP BY MEMBER_ID
HAVING COUNT(*) > 1;

-- 3. Check Cross-Country Table Exclusivity
-- A member must exist in EXACTLY ONE country table. This proves "latest record wins" country migration works.
WITH MemberCountryCounts AS (
    SELECT MEMBER_ID, COUNT(DISTINCT SOURCE_TABLE) AS COUNTRY_TABLE_COUNT
    FROM CORE.V_GLOBAL_MEMBERS_CONSOLIDATED
    GROUP BY MEMBER_ID
)
SELECT 
    'CHECK_COUNTRY_EXCLUSIVITY' AS VALIDATION_NAME,
    'BLOCKING' AS SEVERITY,
    MEMBER_ID,
    COUNTRY_TABLE_COUNT,
    'Member exists in multiple country tables simultaneously!' AS FAILURE_REASON
FROM MemberCountryCounts
WHERE COUNTRY_TABLE_COUNT > 1;

-- 4. Check Stale Member Flag Correctness (> 90 days rule)
SELECT 
    'CHECK_STALE_MEMBER_FLAG_PARITY' AS VALIDATION_NAME,
    'WARNING' AS SEVERITY,
    MEMBER_ID,
    LAST_FLIGHT_DATE,
    DAYS_SINCE_FLIGHT,
    STALE_MEMBER,
    'Flag does not match > 90 days threshold' AS FAILURE_REASON
FROM CORE.V_GLOBAL_MEMBERS_CONSOLIDATED
WHERE (DAYS_SINCE_FLIGHT > 90 AND STALE_MEMBER != 'Y')
   OR (DAYS_SINCE_FLIGHT <= 90 AND STALE_MEMBER != 'N');

-- 5. Check Age Calculation Sanity (Negative Age or Impossibly High Age)
SELECT 
    'CHECK_AGE_SANITY' AS VALIDATION_NAME,
    'BLOCKING' AS SEVERITY,
    MEMBER_ID,
    DATE_OF_BIRTH,
    AGE,
    'Age evaluates to negative or exceeds 120 years' AS FAILURE_REASON
FROM CORE.V_GLOBAL_MEMBERS_CONSOLIDATED
WHERE AGE < 0 OR AGE > 120;

-- 6. Check Date Consistency (DOB after Enrollment Date)
SELECT 
    'CHECK_DOB_PRIOR_TO_ENROLLMENT' AS VALIDATION_NAME,
    'BLOCKING' AS SEVERITY,
    MEMBER_ID,
    DATE_OF_BIRTH,
    ENROLLMENT_DATE,
    'Date of birth is chronologically after enrollment date' AS FAILURE_REASON
FROM CORE.V_GLOBAL_MEMBERS_CONSOLIDATED
WHERE DATE_OF_BIRTH > ENROLLMENT_DATE;

-- 7. Check Redemption Negative Miles or Blank Transaction ID
SELECT 
    'CHECK_REDEMPTION_ANOMALIES' AS VALIDATION_NAME,
    'BLOCKING' AS SEVERITY,
    REDEMPTION_PK,
    MEMBER_ID,
    TXN_ID,
    MILES_REDEEMED,
    'Invalid transaction ID or negative miles redeemed' AS FAILURE_REASON
FROM CORE.FACT_MILEAGE_REDEMPTION
WHERE TXN_ID IS NULL OR TRIM(TXN_ID) = ''
   OR MILES_REDEEMED < 0;

-- 8. Check Orphaned Redemptions (Late-arriving dimension audit)
SELECT 
    'CHECK_ORPHANED_REDEMPTIONS' AS VALIDATION_NAME,
    'WARNING' AS SEVERITY,
    r.MEMBER_ID,
    r.TXN_ID,
    r.PARTNER_NAME,
    'Redemption member does not exist in any country table' AS FAILURE_REASON
FROM CORE.FACT_MILEAGE_REDEMPTION r
LEFT JOIN CORE.CURRENT_MEMBER_REGISTRY m
    ON r.MEMBER_ID = m.MEMBER_ID
WHERE m.MEMBER_ID IS NULL;
