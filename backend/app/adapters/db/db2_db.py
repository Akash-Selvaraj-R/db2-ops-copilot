"""REAL IBM Db2 database adapter (M2 — ``ibm_db`` / ``ibm_db_dbi``).

Contract (layering, see docs/DB2_INTEGRATION.md):
- This adapter is the EXECUTION layer. Callers MUST pass SQL that already
  passed the sqlglot validation gate (``app.services.sql_execution_service``
  enforces that order). The adapter does not re-parse SQL; it enforces the
  transport-level defenses: row cap (``fetchmany(max_rows + 1)``), query
  timeout (``SET CURRENT QUERY TIMEOUT`` on the same session), read-only
  account, and parameter binding (qmark markers only).
- Every failure is mapped to an actionable ``AdapterUnavailableError`` with
  an SQLSTATE classification — connectivity vs. permission vs. syntax are
  distinguishable, and credential material is stripped (``dsn.sanitize``).
- Connections are short-lived (one per operation, closed in ``finally``).
  This favors auditability and crash-isolation over pooled throughput, which
  is the right trade-off for a copilot serving low QPS; a ``transaction()``
  context manager groups multi-statement writes when needed.

NEVER executed against a live database on the development machine (no Db2
installation per the project constraint). Offline unit tests exercise the
code with a fake ``ibm_db_dbi`` module (backend/tests/test_db2_unit.py).
"""

from __future__ import annotations

import logging
import re
import socket
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from app.adapters.base import (
    ExecutionRecord,
    ProbeResult,
    QueryResult,
    SchemaColumn,
    SchemaSnapshot,
    SchemaTable,
)
from app.core.config import Settings
from app.core.errors import AdapterUnavailableError, UpstreamTimeoutError
from app.database.dsn import connect_args, sanitize

logger = logging.getLogger(__name__)

_READ_TABLES_SQL = (
    "SELECT DISTINCT TABNAME FROM SYSCAT.TABLES "
    "WHERE TABSCHEMA = ? AND TABTYPE IN ('T', 'V') ORDER BY TABNAME"
)

_READ_COLUMNS_SQL = (
    "SELECT TABNAME, COLNAME, TYPENAME, NULLS FROM SYSCAT.COLUMNS "
    "WHERE TABSCHEMA = ? ORDER BY TABNAME, COLNO"
)

# SQLSTATE classes mapped to operator-actionable categories.
_SQLSTATE_CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("08", "connectivity", "connection ended unexpectedly — is the database active?"),
    ("28", "authentication", "invalid credentials — check DB2_RO_USER / DB2_RO_PASSWORD"),
    ("425", "authorization", "user lacks the required privilege — check GRANTs (migration 003)"),
    ("427", "schema", "object does not exist — run database/migrations (see database/README.md)"),
    ("428", "sql-semantics", "the statement is not valid for this schema (type/column mismatch)"),
    ("570", "resource", "operation cancelled by the system (time/lock limit)"),
    ("571", "resource", "a SCAN lock escalation occurred — retry or reduce concurrency"),
    ("911", "transaction", "current transaction rolled back — retry the operation"),
)

# Well-known CLI message ids → SQLSTATE, for drivers that print only the
# message id (e.g. "SQL0204N ... is an undefined name").
_MESSAGE_ID_TO_SQLSTATE: dict[str, str] = {
    "0204": "42704",  # object name undefined
    "1013": "42704",  # cannot resolve qualified name
    "0206": "42703",  # column name invalid
    "0104": "42601",  # syntax error at token
    "0180": "42601",  # syntax error in use of tokens
    "0551": "42501",  # not authorized to object
    "0552": "42501",  # not authorized to object
    "0911": "911",    # lock timeout / rolled back
}

_SQLSTATE_RE = re.compile(r"SQLSTATE[=:\s]+([0-9A-Z]{5})", re.IGNORECASE)
_MESSAGE_ID_RE = re.compile(r"\bSQL(\d{4})N\b")


@dataclass(slots=True)
class SqlErrorInfo:
    """Sanitized classification of a driver error."""

    sqlstate: str
    category: str
    hint: str


def classify_db_error(exc: BaseException) -> SqlErrorInfo:
    """Map a driver exception to a sanitized, actionable classification.

    ibm_db raises ``DatabaseError`` whose text embeds both a CLI message id
    (``SQL0204N``) and a SQLSTATE (``42704``). We surface neither raw driver
    text nor connection details — only the SQLSTATE plus a curated hint.
    """
    text = str(exc)
    sqlstate = "unknown"
    match = _SQLSTATE_RE.search(text)
    if match:
        sqlstate = match.group(1).upper()
    else:
        message_id = _MESSAGE_ID_RE.search(text)
        if message_id:
            sqlstate = _MESSAGE_ID_TO_SQLSTATE.get(
                message_id.group(1), "unknown"
            )
    for class_prefix, category, hint in _SQLSTATE_CATEGORIES:
        if sqlstate != "unknown" and sqlstate.startswith(class_prefix):
            if sqlstate == "57014":
                category, hint = (
                    "timeout",
                    "statement cancelled by the query timeout — simplify the "
                    "query or raise SQL_QUERY_TIMEOUT_MS",
                )
            return SqlErrorInfo(sqlstate=sqlstate, category=category, hint=hint)
    return SqlErrorInfo(
        sqlstate=sqlstate, category="unknown", hint="see the Db2 message catalog"
    )


class Db2DatabaseAdapter:
    """Read-only Db2 connectivity for generated SQL and schema introspection."""

    probe_name = "database"
    provider_id = "db2"
    mode = "real"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._closed = False

    # -- availability probes ---------------------------------------------
    def _tcp_reachable(self) -> tuple[bool, str]:
        timeout = max(self._settings.db2_connect_timeout_ms / 1000, 0.2)
        try:
            with socket.create_connection(
                (self._settings.db2_host, self._settings.db2_port), timeout=timeout
            ):
                return True, ""
        except OSError as exc:
            return False, str(exc.strerror or exc)

    def _import_driver(self) -> tuple[bool, str]:
        try:
            import ibm_db  # noqa: F401
            import ibm_db_dbi  # noqa: F401

            return True, ""
        except ImportError as exc:
            return False, str(exc)

    def ping(self) -> ProbeResult:
        if self._closed:
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=0.0,
                detail="Db2 adapter closed",
            )
        start = time.perf_counter()
        target = f"{self._settings.db2_host}:{self._settings.db2_port}"
        reachable, sock_error = self._tcp_reachable()
        driver_ok, driver_error = self._import_driver()

        if not reachable:
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=(time.perf_counter() - start) * 1000,
                detail=(
                    f"Db2 not reachable at {target} ({sock_error}). "
                    "Start the Db2 Community Edition container — see "
                    "docs/DB2_INTEGRATION.md."
                ),
            )
        if not driver_ok:
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=(time.perf_counter() - start) * 1000,
                detail=(
                    f"Db2 reachable at {target} but the ibm_db driver is missing "
                    f"({driver_error}). Install requirements-integration.txt."
                ),
            )

        # Driver present: attempt a real, short-lived login probe.
        try:
            import ibm_db_dbi

            dsn, user, password = connect_args(self._settings)
            conn = ibm_db_dbi.connect(dsn, user, password)
            conn.close()
            return ProbeResult(
                name=self.probe_name,
                status="ok",
                mode=self.mode,
                latency_ms=(time.perf_counter() - start) * 1000,
                detail=f"connected to Db2 at {target} as read-only user '{user}'",
            )
        except Exception as exc:  # driver raises many error classes
            info = classify_db_error(exc)
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=(time.perf_counter() - start) * 1000,
                detail=(
                    f"Db2 login failed at {target} "
                    f"[{info.category}, SQLSTATE {info.sqlstate}]: "
                    f"{sanitize(str(exc), self._settings)}"
                ),
            )

    # -- connection / transaction lifecycle --------------------------------
    def _connect(self):
        try:
            import ibm_db_dbi
        except ImportError as exc:
            raise AdapterUnavailableError(
                "ibm_db driver is not installed. Install it with: "
                "pip install -r requirements-integration.txt (M2).",
                detail={"import_error": str(exc)},
            ) from exc

        dsn, user, password = connect_args(self._settings)
        try:
            return ibm_db_dbi.connect(dsn, user, password)
        except Exception as exc:
            info = classify_db_error(exc)
            raise AdapterUnavailableError(
                f"Cannot connect to Db2 at {self._settings.db2_host} "
                f"[{info.category}, SQLSTATE {info.sqlstate}]: "
                f"{sanitize(str(exc), self._settings)}",
                detail={
                    "host": self._settings.db2_host,
                    "port": self._settings.db2_port,
                    "sqlstate": info.sqlstate,
                    "hint": info.hint,
                },
            ) from exc

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        """Group writes in one connection with commit/rollback semantics.

        Usage::

            with adapter.transaction() as conn:
                cur = conn.cursor()
                cur.execute(insert_sql, params)
            # committed on success, rolled back on exception

        The read-only account limits what writes can actually do
        (APP_AUDIT / QUERY_EXECUTIONS INSERT only — see migration 003).
        """
        if self._closed:
            raise AdapterUnavailableError("Db2 adapter is closed.")
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001 — rollback is best-effort
                logger.warning("rollback failed", exc_info=True)
            raise
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — close is best-effort
                pass

    @staticmethod
    def _apply_timeout(cursor: Any, timeout_ms: int) -> bool:
        """Set Db2's session query timeout; report whether it was applied."""
        timeout_s = max(int(timeout_ms / 1000), 1)
        try:
            cursor.execute(f"SET CURRENT QUERY TIMEOUT {timeout_s}")
            return True
        except Exception:  # noqa: BLE001 — not supported on every server/setup
            return False

    # -- queries -----------------------------------------------------------
    def execute_readonly(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
        timeout_ms: int | None = None,
    ) -> QueryResult:
        """Execute an already-validated read-only statement with hard caps.

        Defenses applied here (independent of the validation gate):
        - row cap: fetches ``sql_max_rows + 1`` rows and marks truncation;
        - query timeout: ``SET CURRENT QUERY TIMEOUT`` on the same session
          (warning logged when unsupported — the Python-side fetch bound is
          still the last line of defense against unbounded fetches);
        - parameter binding: qmark markers only, never string interpolation;
        - the connection is read via the ``db2ro`` account whose GRANTs
          forbid DML/DDL (defense in depth).
        """
        if self._closed:
            raise AdapterUnavailableError("Db2 adapter is closed.")
        start = time.perf_counter()
        conn = self._connect()
        try:
            cursor = conn.cursor()
            timeout = timeout_ms or self._settings.sql_query_timeout_ms
            if not self._apply_timeout(cursor, timeout):
                logger.warning(
                    "SET CURRENT QUERY TIMEOUT not applied (unsupported on "
                    "this server/setup); relying on fetch cap + client timeout"
                )
            cursor.execute(sql, tuple(params) if params else None)
            max_rows = self._settings.sql_max_rows
            rows = cursor.fetchmany(max_rows + 1) or []
            columns = [d[0] for d in (cursor.description or [])]
            truncated = len(rows) > max_rows
            if truncated:
                rows = rows[:max_rows]
            return QueryResult(
                columns=columns,
                rows=[list(r) for r in rows],
                row_count=len(rows),
                truncated=truncated,
                latency_ms=(time.perf_counter() - start) * 1000,
            )
        except AdapterUnavailableError:
            raise
        except Exception as exc:
            info = classify_db_error(exc)
            if info.category == "timeout":
                raise UpstreamTimeoutError(
                    "Query exceeded the configured timeout "
                    f"[SQLSTATE {info.sqlstate}].",
                    detail={"sqlstate": info.sqlstate, "hint": info.hint},
                ) from exc
            raise AdapterUnavailableError(
                f"Query execution failed [{info.category}, "
                f"SQLSTATE {info.sqlstate}]: {sanitize(str(exc), self._settings)}",
                detail={
                    "error_type": type(exc).__name__,
                    "sqlstate": info.sqlstate,
                    "hint": info.hint,
                },
            ) from exc
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — close is best-effort
                pass

    # -- schema introspection ------------------------------------------------
    def fetch_schema(self) -> SchemaSnapshot:
        """Read tables/columns of the application schema from SYSCAT.

        Uses parameterized queries against SYSCAT (read-only catalog views
        granted to PUBLIC by Db2) — no DDL, no dynamic SQL. The schema read
        is ``DB2_APP_SCHEMA`` (default APP), NOT the login user's schema.
        """
        if self._closed:
            raise AdapterUnavailableError("Db2 adapter is closed.")
        start = time.perf_counter()
        schema = self._settings.app_schema
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(_READ_TABLES_SQL, (schema,))
            table_names = [row[0] for row in cursor.fetchall()]
            cursor.execute(_READ_COLUMNS_SQL, (schema,))
            columns_by_table: dict[str, list[SchemaColumn]] = {}
            for tabname, colname, typename, nulls in cursor.fetchall():
                columns_by_table.setdefault(tabname, []).append(
                    SchemaColumn(
                        name=colname,
                        data_type=typename,
                        nullable=str(nulls).upper() in {"Y", "YES", "1"},
                    )
                )
            tables = [
                SchemaTable(
                    name=name,
                    schema_name=schema,
                    columns=columns_by_table.get(name, []),
                )
                for name in table_names
            ]
            return SchemaSnapshot(
                tables=tables,
                source="SYSCAT",
                latency_ms=(time.perf_counter() - start) * 1000,
            )
        except AdapterUnavailableError:
            raise
        except Exception as exc:
            info = classify_db_error(exc)
            raise AdapterUnavailableError(
                f"Schema introspection failed [{info.category}, "
                f"SQLSTATE {info.sqlstate}]: {sanitize(str(exc), self._settings)}",
                detail={"schema": schema, "sqlstate": info.sqlstate},
            ) from exc
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — close is best-effort
                pass

    # -- execution history (APP.QUERY_EXECUTIONS) ---------------------------
    def explain(self, sql: str, timeout_ms: int | None = None) -> bool:
        """Best-effort ``EXPLAIN`` dry-run — advisory, never raises.

        The read-only account usually lacks EXPLAIN privileges or plan-table
        access; failure is expected and simply reported as False so the
        caller records ``explain_status=FAILED`` and executes anyway
        (the validation gate + row/timeout caps are the real defenses).
        """
        if self._closed:
            return False
        conn = None
        try:
            conn = self._connect()
            cursor = conn.cursor()
            timeout = timeout_ms or self._settings.sql_query_timeout_ms
            self._apply_timeout(cursor, timeout)
            cursor.execute(f"EXPLAIN {sql}")
            conn.commit()
            return True
        except Exception as exc:  # noqa: BLE001 — advisory by contract
            info = classify_db_error(exc)
            logger.info(
                "EXPLAIN dry-run unavailable (SQLSTATE %s, %s): %s — continuing "
                "without plan check",
                info.sqlstate,
                info.category,
                sanitize(str(exc), self._settings)[:200],
            )
            return False
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001 — close is best-effort
                    pass

    _INSERT_EXECUTION_SQL = (
        "INSERT INTO {schema}.QUERY_EXECUTIONS ("
        "CLIENT_REQ_ID, SQL_TEXT, VALIDATION_STATUS, EXPLAIN_STATUS, "
        "EXECUTION_STATUS, ROW_COUNT, TRUNCATED, LATENCY_MS, SQLSTATE_CODE, "
        "METADATA) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )

    _SELECT_EXECUTIONS_SQL = (
        "SELECT EXECUTION_ID, REQ_TS, CLIENT_REQ_ID, SQL_TEXT, "
        "VALIDATION_STATUS, EXPLAIN_STATUS, EXECUTION_STATUS, ROW_COUNT, "
        "TRUNCATED, LATENCY_MS, SQLSTATE_CODE, METADATA "
        "FROM {schema}.QUERY_EXECUTIONS ORDER BY EXECUTION_ID DESC "
        "FETCH FIRST {limit} ROWS ONLY"
    )

    def record_execution(self, record: ExecutionRecord) -> int:
        """Append one row to APP.QUERY_EXECUTIONS (best-effort by contract).

        The read-only account has GRANT SELECT, INSERT on this table
        (migration 003). METADATA passes through the sanitizer first.
        """
        if self._closed:
            raise AdapterUnavailableError("Db2 adapter is closed.")
        from app.security.sanitize import sanitize_metadata

        sql = self._INSERT_EXECUTION_SQL.format(schema=self._settings.app_schema)
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                sql,
                (
                    record.request_id,
                    record.sql,
                    record.validation_status,
                    record.explain_status,
                    record.execution_status,
                    record.row_count,
                    "Y" if record.truncated else "N",
                    int(record.latency_ms),
                    record.sqlstate,
                    sanitize_metadata(record.detail),
                ),
            )
            conn.commit()
            new_id = getattr(cursor, "lastrowid", None)
            execution_id = int(new_id) if isinstance(new_id, int) else 0
            logger.debug(
                "execution row written id=%d status=%s rows=%s request_id=%s",
                execution_id,
                record.execution_status,
                record.row_count,
                record.request_id or "-",
            )
            return execution_id
        except Exception as exc:
            info = classify_db_error(exc)
            raise AdapterUnavailableError(
                f"Execution-history write failed [{info.category}, "
                f"SQLSTATE {info.sqlstate}]",
                detail={"hint": info.hint, "table": "QUERY_EXECUTIONS"},
            ) from exc
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — close is best-effort
                pass

    def list_executions(self, limit: int = 20) -> list[ExecutionRecord]:
        """Read the most recent execution-history rows (newest first)."""
        if self._closed:
            raise AdapterUnavailableError("Db2 adapter is closed.")
        sql = self._SELECT_EXECUTIONS_SQL.format(
            schema=self._settings.app_schema,
            limit=max(1, min(int(limit), 500)),  # Db2 forbids markers in FETCH FIRST
        )
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            records: list[ExecutionRecord] = []
            for (
                execution_id,
                req_ts,
                client_req_id,
                sql_text,
                validation_status,
                explain_status,
                execution_status,
                row_count,
                truncated,
                latency_ms,
                sqlstate_code,
                metadata,
            ) in cursor.fetchall():
                ts = (
                    req_ts.isoformat()
                    if hasattr(req_ts, "isoformat")
                    else str(req_ts or "")
                )
                records.append(
                    ExecutionRecord(
                        id=int(execution_id),
                        timestamp=ts,
                        request_id=str(client_req_id) if client_req_id else None,
                        sql=str(sql_text or ""),
                        validation_status=str(validation_status or ""),
                        explain_status=str(explain_status) if explain_status else None,
                        execution_status=str(execution_status or ""),
                        row_count=int(row_count) if row_count is not None else None,
                        truncated=str(truncated or "N").upper() == "Y",
                        latency_ms=int(latency_ms or 0),
                        sqlstate=str(sqlstate_code) if sqlstate_code else None,
                        detail=str(metadata) if metadata else None,
                    )
                )
            return records
        except AdapterUnavailableError:
            raise
        except Exception as exc:
            info = classify_db_error(exc)
            raise AdapterUnavailableError(
                f"Execution-history read failed [{info.category}, "
                f"SQLSTATE {info.sqlstate}]",
                detail={"hint": info.hint, "table": "QUERY_EXECUTIONS"},
            ) from exc
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — close is best-effort
                pass

    def close(self) -> None:
        self._closed = True
