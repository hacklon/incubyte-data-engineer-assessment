-- =============================================================================
-- SkyPoints Loyalty Data Engine — Staging Transformation Procedure
-- Deliverable 2: Compute Age (from DOB), Days Since Flight & Stale_Member (> 90 days)
-- Incorporates Row-Level Quality Checks into Quarantine
-- =============================================================================

USE DATABASE SKYPOINTS_DB;
USE SCHEMA OPS;

CREATE OR REPLACE PROCEDURE OPS.SP_LOAD_STAGING_MEMBERS(
    P_BATCH_ID VARCHAR,
    P_EVALUATION_DATE VARCHAR -- Parameterized 'YYYY-MM-DD' for reproducible replay
)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
    V_AS_OF_DATE DATE;
    V_TOTAL_PROCESSED NUMBER DEFAULT 0;
    V_VALID_LOADED NUMBER DEFAULT 0;
    V_QUARANTINED NUMBER DEFAULT 0;
BEGIN
    V_AS_OF_DATE := COALESCE(TRY_TO_DATE(:P_EVALUATION_DATE, 'YYYY-MM-DD'), CURRENT_DATE());

    -- Parse raw flat file landing lines (Record Type = 'D')
    -- Tokenize pipe-delimited payload using SPLIT()
    -- Sample token index layout:
    -- 0: Record_Type ('D')
    -- 1: Member_Name
    -- 2: Member_Id
    -- 3: Enrollment_Date (YYYYMMDD)
    -- 4: Last_Flight_Date (YYYYMMDD)
    -- 5: Tier_Code
    -- 6: Agent_Name
    -- 7: State
    -- 8: Country
    -- 9: DOB (MMDDYYYY or YYYYMMDD)
    -- 10: Is_Active
    
    INSERT ALL
        -- Valid Records Destination -> STG.MEMBER_PROFILES_ENRICHED
        WHEN RULE_ERROR IS NULL THEN
            INTO STG.MEMBER_PROFILES_ENRICHED (
                BATCH_ID,
                BATCH_TIMESTAMP,
                SOURCE_FILE_NAME,
                SOURCE_ROW_NUMBER,
                SOURCE_NAMESPACE,
                MEMBER_ID,
                MEMBER_NAME,
                ENROLLMENT_DATE,
                LAST_FLIGHT_DATE,
                TIER_CODE,
                AGENT_NAME,
                STATE_CODE,
                COUNTRY_CODE,
                POST_CODE,
                DATE_OF_BIRTH,
                IS_ACTIVE,
                AGE,
                DAYS_SINCE_FLIGHT,
                STALE_MEMBER,
                DQ_STATUS
            ) VALUES (
                BATCH_ID,
                BATCH_TS,
                SOURCE_FILE_NAME,
                SOURCE_ROW_NUMBER,
                'GLOBAL',
                MEMBER_ID,
                MEMBER_NAME,
                ENROLL_DT,
                FLIGHT_DT,
                TIER,
                AGENT,
                STATE_VAL,
                COUNTRY_NORM,
                POST_VAL,
                DOB_VAL,
                ACTIVE_VAL,
                CALCULATED_AGE,
                DAYS_SINCE_FLIGHT_VAL,
                STALE_FLAG,
                'VALID'
            )
        -- Invalid Records Destination -> DQ.QUARANTINE_RECORDS
        WHEN RULE_ERROR IS NOT NULL THEN
            INTO DQ.QUARANTINE_RECORDS (
                BATCH_ID,
                SOURCE_FILE_NAME,
                SOURCE_ROW_NUMBER,
                RULE_ID,
                SEVERITY,
                FIELD_NAME,
                INVALID_VALUE,
                REASON,
                RAW_PAYLOAD
            ) VALUES (
                BATCH_ID,
                SOURCE_FILE_NAME,
                SOURCE_ROW_NUMBER,
                RULE_ERROR,
                'BLOCKING',
                ERR_FIELD,
                ERR_VALUE,
                ERR_MSG,
                RAW_PAYLOAD
            )
    SELECT 
        l.BATCH_ID,
        TO_TIMESTAMP_NTZ(COALESCE(REGEXP_SUBSTR(l.SOURCE_FILE_NAME, '\\d{8}_\\d{6}'), '20240115_000000'), 'YYYYMMDD_HH24MISS') AS BATCH_TS,
        l.SOURCE_FILE_NAME,
        l.SOURCE_ROW_NUMBER,
        l.RAW_PAYLOAD,
        
        -- Token Extraction (Handling leading pipe if present)
        TRIM(SPLIT_PART(l.RAW_PAYLOAD, '|', 2)) AS MEMBER_NAME,
        TRIM(SPLIT_PART(l.RAW_PAYLOAD, '|', 3)) AS MEMBER_ID,
        
        -- Date Parsing with Fallbacks
        TRY_TO_DATE(TRIM(SPLIT_PART(l.RAW_PAYLOAD, '|', 4)), 'YYYYMMDD') AS ENROLL_DT,
        TRY_TO_DATE(TRIM(SPLIT_PART(l.RAW_PAYLOAD, '|', 5)), 'YYYYMMDD') AS FLIGHT_DT,
        
        UPPER(TRIM(SPLIT_PART(l.RAW_PAYLOAD, '|', 6))) AS TIER,
        TRIM(SPLIT_PART(l.RAW_PAYLOAD, '|', 7)) AS AGENT,
        UPPER(TRIM(SPLIT_PART(l.RAW_PAYLOAD, '|', 8))) AS STATE_VAL,
        
        -- Country Normalization (Mapping common variants)
        CASE UPPER(TRIM(SPLIT_PART(l.RAW_PAYLOAD, '|', 9)))
            WHEN 'USA' THEN 'USA'
            WHEN 'US' THEN 'USA'
            WHEN 'IND' THEN 'IND'
            WHEN 'INDIA' THEN 'IND'
            WHEN 'CAN' THEN 'CAN'
            WHEN 'CANADA' THEN 'CAN'
            WHEN 'AU' THEN 'AUS'
            WHEN 'AUS' THEN 'AUS'
            WHEN 'AUSTRALIA' THEN 'AUS'
            WHEN 'PHIL' THEN 'PHL'
            WHEN 'PHL' THEN 'PHL'
            WHEN 'PHILIPPINES' THEN 'PHL'
            ELSE UPPER(TRIM(SPLIT_PART(l.RAW_PAYLOAD, '|', 9)))
        END AS COUNTRY_NORM,
        
        -- Positional tolerance: If token 10 has 8 digits, it is DOB; if token 11 exists, token 10 may be Post Code
        NULL AS POST_VAL,
        
        -- Parse DOB (supports MMDDYYYY e.g., 03051985 or YYYYMMDD)
        COALESCE(
            TRY_TO_DATE(LPAD(TRIM(SPLIT_PART(l.RAW_PAYLOAD, '|', 10)), 8, '0'), 'MMDDYYYY'),
            TRY_TO_DATE(TRIM(SPLIT_PART(l.RAW_PAYLOAD, '|', 10)), 'YYYYMMDD')
        ) AS DOB_VAL,
        
        COALESCE(TRIM(SPLIT_PART(l.RAW_PAYLOAD, '|', 11)), 'A') AS ACTIVE_VAL,
        
        -- =====================================================================
        -- Deliverable 2 Calculations:
        -- Age = Completed calendar years as of V_AS_OF_DATE
        -- =====================================================================
        CASE 
            WHEN DOB_VAL IS NULL THEN NULL
            WHEN DOB_VAL > :V_AS_OF_DATE THEN NULL
            ELSE DATEDIFF('year', DOB_VAL, :V_AS_OF_DATE) - 
                 IFF(TO_CHAR(:V_AS_OF_DATE, 'MMDD') < TO_CHAR(DOB_VAL, 'MMDD'), 1, 0)
        END AS CALCULATED_AGE,
        
        -- Days Since Flight
        DATEDIFF('day', FLIGHT_DT, :V_AS_OF_DATE) AS DAYS_SINCE_FLIGHT_VAL,
        
        -- Stale Member Flag: 'Y' if Days > 90, otherwise 'N'
        CASE 
            WHEN FLIGHT_DT IS NULL THEN 'Y' -- Inactive flight history treated as stale
            WHEN DATEDIFF('day', FLIGHT_DT, :V_AS_OF_DATE) > 90 THEN 'Y'
            ELSE 'N'
        END AS STALE_FLAG,
        
        -- =====================================================================
        -- Deliverable 5 Quality Checks:
        -- =====================================================================
        CASE 
            WHEN MEMBER_ID IS NULL OR MEMBER_ID = '' 
                THEN 'E_MANDATORY_NULL'
            WHEN MEMBER_NAME IS NULL OR MEMBER_NAME = '' 
                THEN 'E_MANDATORY_NULL'
            WHEN ENROLL_DT IS NULL 
                THEN 'E_INVALID_ENROLLMENT_DATE'
            WHEN COUNTRY_NORM IS NULL OR COUNTRY_NORM = ''
                THEN 'E_MISSING_COUNTRY'
            WHEN DOB_VAL IS NOT NULL AND DOB_VAL > ENROLL_DT
                THEN 'E_DOB_AFTER_ENROLLMENT'
            ELSE NULL
        END AS RULE_ERROR,
        
        CASE 
            WHEN MEMBER_ID IS NULL OR MEMBER_ID = '' THEN 'MEMBER_ID'
            WHEN MEMBER_NAME IS NULL OR MEMBER_NAME = '' THEN 'MEMBER_NAME'
            WHEN ENROLL_DT IS NULL THEN 'ENROLLMENT_DATE'
            WHEN COUNTRY_NORM IS NULL OR COUNTRY_NORM = '' THEN 'COUNTRY'
            WHEN DOB_VAL IS NOT NULL AND DOB_VAL > ENROLL_DT THEN 'DATE_OF_BIRTH'
            ELSE NULL
        END AS ERR_FIELD,
        
        CASE 
            WHEN MEMBER_ID IS NULL OR MEMBER_ID = '' THEN 'NULL'
            WHEN MEMBER_NAME IS NULL OR MEMBER_NAME = '' THEN 'NULL'
            WHEN ENROLL_DT IS NULL THEN SPLIT_PART(l.RAW_PAYLOAD, '|', 4)
            WHEN COUNTRY_NORM IS NULL OR COUNTRY_NORM = '' THEN 'EMPTY'
            ELSE TO_CHAR(DOB_VAL)
        END AS ERR_VALUE,
        
        CASE 
            WHEN MEMBER_ID IS NULL OR MEMBER_ID = '' THEN 'Member ID is mandatory'
            WHEN MEMBER_NAME IS NULL OR MEMBER_NAME = '' THEN 'Member Name is mandatory'
            WHEN ENROLL_DT IS NULL THEN 'Enrollment date is missing or invalid'
            WHEN COUNTRY_NORM IS NULL OR COUNTRY_NORM = '' THEN 'Country code is mandatory'
            WHEN DOB_VAL IS NOT NULL AND DOB_VAL > ENROLL_DT THEN 'Date of birth cannot be after enrollment date'
            ELSE 'Valid'
        END AS ERR_MSG

    FROM RAW.MEMBER_PROFILE_LANDING l
    WHERE l.BATCH_ID = :P_BATCH_ID
      AND l.RECORD_TYPE = 'D';

    RETURN 'SUCCESS: Staging loaded and enriched for batch ' || :P_BATCH_ID;
END;
$$;
