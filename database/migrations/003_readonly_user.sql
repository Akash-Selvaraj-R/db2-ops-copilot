-- ============================================================================
-- 003_readonly_user.sql — least-privilege application account.
-- Run after 001_app_schema.sql (and optionally 002). NOT executed during M1.
--
-- Replace :ro_user and :ro_password with locally generated values supplied via
-- the environment (DB2_RO_USER / DB2_RO_PASSWORD). Generate the password
-- programmatically (e.g. Python `secrets.token_urlsafe(24)`) and store it only
-- in the gitignored .env — never in a file, log, or commit.
--
-- Security model (defense in depth):
--   * The app connects as db2ro — SELECT-only on business tables, plus
--     INSERT on APP_AUDIT so every request can be traced.
--   * The SQL validation gate rejects DDL/DML before execution, but these
--     GRANTs are the independent enforcement layer if the gate is ever
--     bypassed. Database permissions, not static validation, are the
--     boundary.
--   * No GRANTs on system catalog write paths; SYSCAT read access is limited
--     to what Db2 grants PUBLIC by default and is additionally denied by the
--     application policy for generated SQL.
-- ============================================================================

-- (Run as the instance owner / db2inst1, connected to the target database.)
-- CREATE USER :ro_user USING PASSWORD :ro_password;   -- syntax depends on
--                                                      -- instance setup path;
--                                                      -- the VS Code extension
--                                                      -- flow may pre-create it.

GRANT CONNECT ON DATABASE TO :ro_user;

GRANT SELECT ON APP.DEMO_SERVERS  TO :ro_user;
GRANT SELECT ON APP.DEMO_INCIDENTS TO :ro_user;
GRANT SELECT ON APP.KB_CHUNKS     TO :ro_user;

-- Audit trail: the app must be able to append and read audit rows, nothing else.
GRANT SELECT, INSERT ON APP.APP_AUDIT TO :ro_user;

-- Explicitly NOT granted: UPDATE, DELETE, ALTER, DROP, CREATE, INDEX,
-- BINDADD, CONNECT administration, or any schema-level WRITE privilege.

COMMIT;
