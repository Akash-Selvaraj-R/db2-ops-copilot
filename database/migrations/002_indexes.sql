-- ============================================================================
-- 002_indexes.sql — indexes for the application schema.
-- Run after 001_app_schema.sql. NOT executed during M1.
-- ============================================================================

CREATE INDEX APP.IDX_INCIDENTS_SERVER ON APP.DEMO_INCIDENTS (SERVER_ID);
CREATE INDEX APP.IDX_INCIDENTS_SEVERITY ON APP.DEMO_INCIDENTS (SEVERITY);

-- Audit reads are always "newest N entries".
CREATE INDEX APP.IDX_AUDIT_TS ON APP.APP_AUDIT (REQ_TS DESC);
CREATE INDEX APP.IDX_AUDIT_INTENT ON APP.APP_AUDIT (INTENT);

COMMIT;
