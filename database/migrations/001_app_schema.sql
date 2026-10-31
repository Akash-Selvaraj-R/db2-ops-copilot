-- ============================================================================
-- 001_app_schema.sql — Db2 Ops Copilot application schema (IBM Db2 12.1.2+)
--
-- Target: IBM Db2 Community Edition (docker: icr.io/db2_community/db2).
-- NOT executed during M1 (no Db2 on the development machine). Run manually
-- in M2 after the instance exists — see database/README.md.
--
-- All application objects live in the dedicated APP schema so the denied
-- system schemas (SYSCAT, SYSIBM, ...) stay untouched and the read-only
-- account can be granted exactly what it needs.
-- ============================================================================

-- Dedicated application schema (owned by the instance owner, not db2ro).
CREATE SCHEMA APP;

-- ----------------------------------------------------------------------------
-- DEMO_SERVERS / DEMO_INCIDENTS — synthetic demo fleet for the text-to-SQL
-- path. Harmless sample data; no real systems are described.
-- ----------------------------------------------------------------------------
CREATE TABLE APP.DEMO_SERVERS (
    SERVER_ID   INTEGER       NOT NULL PRIMARY KEY,
    HOSTNAME    VARCHAR(64)   NOT NULL,
    ENVIRONMENT VARCHAR(16)   NOT NULL,
    OWNER_TEAM  VARCHAR(32),
    UPTIME_PCT  DECIMAL(5, 2)
);

CREATE TABLE APP.DEMO_INCIDENTS (
    INCIDENT_ID INTEGER     NOT NULL PRIMARY KEY,
    SERVER_ID   INTEGER     REFERENCES APP.DEMO_SERVERS (SERVER_ID),
    SEVERITY    INTEGER     NOT NULL,
    OPENED_AT   TIMESTAMP   NOT NULL,
    RESOLVED_AT TIMESTAMP
);

INSERT INTO APP.DEMO_SERVERS (SERVER_ID, HOSTNAME, ENVIRONMENT, OWNER_TEAM, UPTIME_PCT) VALUES
    (1, 'db2-prod-01',   'prod',    'platform',  99.95),
    (2, 'db2-prod-02',   'prod',    'platform',  99.87),
    (3, 'db2-stage-01',  'staging', 'data-eng',  98.40),
    (4, 'db2-dev-01',    'dev',     'data-eng',  92.10);

INSERT INTO APP.DEMO_INCIDENTS (INCIDENT_ID, SERVER_ID, SEVERITY, OPENED_AT, RESOLVED_AT) VALUES
    (101, 1, 2, '2026-10-28 09:15:00', '2026-10-28 11:02:00'),
    (102, 3, 3, '2026-10-29 14:40:00', NULL),
    (103, 4, 1, '2026-10-30 08:05:00', '2026-10-30 08:31:00'),
    (104, 2, 4, '2026-10-30 10:22:00', NULL);

-- ----------------------------------------------------------------------------
-- APP_AUDIT — every copilot request is recorded (intent, question, generated
-- SQL, status, latency, client request id) for enterprise traceability.
-- The read-only account receives INSERT + SELECT only (003_readonly_user.sql).
-- ----------------------------------------------------------------------------
CREATE TABLE APP.APP_AUDIT (
    AUDIT_ID      BIGINT      NOT NULL GENERATED ALWAYS AS IDENTITY
                    (START WITH 1, INCREMENT BY 1, CACHE 20) PRIMARY KEY,
    REQ_TS        TIMESTAMP   NOT NULL DEFAULT CURRENT TIMESTAMP,
    INTENT        VARCHAR(16) NOT NULL,
    QUESTION      CLOB,
    SQL_TEXT      CLOB,
    STATUS        VARCHAR(16) NOT NULL,
    LATENCY_MS    INTEGER,
    CLIENT_REQ_ID VARCHAR(64)
);

-- ----------------------------------------------------------------------------
-- KB_CHUNKS — the RAG knowledge base. VECTOR(768, FLOAT32) matches
-- nomic-embed-text:v1.5. Requires Db2 12.1.2+ (VECTOR support verified with
-- db2level before running this script — see M2 checklist).
--
-- NOTE: langchain-db2's DB2VS manages its own table layout; this table is the
-- documented fallback/inspection view and proves VECTOR support on the
-- provisioned server. Final layout is decided in M2 against the real DB2VS.
-- ----------------------------------------------------------------------------
CREATE TABLE APP.KB_CHUNKS (
    ID         INTEGER      NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    CONTENT    CLOB         NOT NULL,
    EMBEDDING  VECTOR(768, FLOAT32) NOT NULL,
    METADATA   JSON,
    CREATED_AT TIMESTAMP    NOT NULL DEFAULT CURRENT TIMESTAMP
);

COMMIT;
