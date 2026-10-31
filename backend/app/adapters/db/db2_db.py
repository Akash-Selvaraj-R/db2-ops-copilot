"""REAL Db2 database adapter (M2 integration target).

Status (M1): fully implemented against the ``ibm_db`` / ``ibm_db_dbi`` API but
NEVER executed against a live database yet — the driver is intentionally not
installed during M1 (see requirements-integration.txt). ``ping()`` performs
safe, offline checks in this order:

1. TCP reachability of ``DB2_HOST:DB2_PORT`` (stdlib socket, short timeout).
2. ``ibm_db`` import availability.
3. Optional real login probe (only when the driver is present).

All failure modes return an actionable ``unavailable`` probe instead of
raising, so the health endpoint always renders. All methods raise
``AdapterUnavailableError`` when the service/driver is missing.
"""

from __future__ import annotations

import logging
import socket
import time
from typing import Any, Sequence

from app.adapters.base import (
    ProbeResult,
    QueryResult,
    SchemaColumn,
    SchemaSnapshot,
    SchemaTable,
)
from app.core.config import Settings
from app.core.errors import AdapterUnavailableError
from app.database.dsn import connect_args, sanitize

logger = logging.getLogger(__name__)

_READ_SCHEMA_SQL = (
    "SELECT TABNAME, COLNAME, TYPENAME, NULLS FROM SYSCAT.COLUMNS "
    "WHERE TABSCHEMA = ? ORDER BY TABNAME, COLNO"
)

_READ_TABLES_SQL = (
    "SELECT DISTINCT TABNAME FROM SYSCAT.TABLES "
    "WHERE TABSCHEMA = ? AND TABTYPE = 'T' ORDER BY TABNAME"
)


class Db2DatabaseAdapter:
    """Read-only Db2 connectivity for generated SQL and schema introspection."""

    probe_name = "database"
    provider_id = "db2"
    mode = "real"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._closed = False
        self._driver_available: bool | None = None

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
            import ibm_db_dbi  # noqa: F401
            import ibm_db  # noqa: F401

            self._driver_available = True
            return True, ""
        except ImportError as exc:
            self._driver_available = False
            return False, str(exc)

    def ping(self) -> ProbeResult:
        start = time.perf_counter()
        if self._closed:
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=0.0,
                detail="Db2 adapter closed",
            )

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
                    "Start the Db2 Community Edition container — see DEPLOYMENT.md."
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
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=(time.perf_counter() - start) * 1000,
                detail=f"Db2 login failed at {target}: {sanitize(str(exc), self._settings)}",
            )

    # -- queries -----------------------------------------------------------
    def _connect(self):
        try:
            import ibm_db_dbi
        except ImportError as exc:
            raise AdapterUnavailableError(
                "ibm_db driver is not installed. "
                "Install it with: pip install -r requirements-integration.txt (M2).",
                detail={"import_error": str(exc)},
            ) from exc

        dsn, user, password = connect_args(self._settings)
        try:
            return ibm_db_dbi.connect(dsn, user, password)
        except Exception as exc:
            raise AdapterUnavailableError(
                f"Cannot connect to Db2 at {self._settings.db2_host}: "
                f"{sanitize(str(exc), self._settings)}",
                detail={"host": self._settings.db2_host, "port": self._settings.db2_port},
            ) from exc

    def execute_readonly(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
        timeout_ms: int | None = None,
    ) -> QueryResult:
        if self._closed:
            raise AdapterUnavailableError("Db2 adapter is closed.")
        start = time.perf_counter()
        conn = self._connect()
        try:
            cursor = conn.cursor()
            timeout_s = int(
                (timeout_ms or self._settings.sql_query_timeout_ms) / 1000
            )
            try:  # best effort — not supported by every Db2 server
                cursor.execute(f"SET CURRENT QUERY TIMEOUT {max(timeout_s, 1)}")
            except Exception:  # noqa: BLE001
                pass
            cursor.execute(sql, tuple(params) if params else None)
            rows = cursor.fetchmany(self._settings.sql_max_rows + 1) or []
            columns = [d[0] for d in (cursor.description or [])]
            truncated = len(rows) > self._settings.sql_max_rows
            if truncated:
                rows = rows[: self._settings.sql_max_rows]
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
            raise AdapterUnavailableError(
                f"Query execution failed: {sanitize(str(exc), self._settings)}",
                detail={"error_type": type(exc).__name__},
            ) from exc
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def fetch_schema(self) -> SchemaSnapshot:
        if self._closed:
            raise AdapterUnavailableError("Db2 adapter is closed.")
        start = time.perf_counter()
        conn = self._connect()
        try:
            cursor = conn.cursor()
            schema = self._settings.db2_ro_user.upper()
            cursor.execute(_READ_TABLES_SQL, (schema,))
            table_names = [row[0] for row in cursor.fetchall()]
            cursor.execute(_READ_SCHEMA_SQL, (schema,))
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
            raise AdapterUnavailableError(
                f"Schema introspection failed: {sanitize(str(exc), self._settings)}",
                detail={"error_type": type(exc).__name__},
            ) from exc
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def close(self) -> None:
        self._closed = True
