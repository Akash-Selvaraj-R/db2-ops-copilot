"""REAL audit adapter — persists audit rows into the Db2 ``APP_AUDIT`` table.

Status (M1): implemented against ``ibm_db_dbi`` (qmark parameter binding,
connections per call) but NEVER executed against a live database — the driver
is not installed and no database exists during M1.

Least-privilege note: audit writes use the application's Db2 account. The
planned grants (database/migrations/003_readonly_user.sql) are:

    GRANT SELECT, INSERT ON APP_AUDIT TO <ro_user>

so the same read-only account used for query execution can append audit rows
and nothing else.

``ping()`` checks TCP reachability + driver availability without logging in,
so health stays cheap and never leaks credentials.
"""

from __future__ import annotations

import importlib.util
import socket
import time
from datetime import datetime

from app.adapters.base import AuditRecord, ProbeResult
from app.core.config import Settings
from app.core.errors import AdapterUnavailableError
from app.database.dsn import connect_args, sanitize

_INSERT_SQL = (
    "INSERT INTO APP_AUDIT (INTENT, QUESTION, SQL_TEXT, STATUS, LATENCY_MS, "
    "CLIENT_REQ_ID) VALUES (?, ?, ?, ?, ?, ?)"
)


class Db2AuditAdapter:
    """Audit persistence backed by the Db2 APP_AUDIT table."""

    probe_name = "audit"
    provider_id = "db2"
    mode = "real"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._closed = False

    # -- probes -------------------------------------------------------------
    def ping(self) -> ProbeResult:
        start = time.perf_counter()
        if self._closed:
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=0.0,
                detail="audit adapter closed",
            )
        elapsed = lambda: (time.perf_counter() - start) * 1000  # noqa: E731

        has_driver = importlib.util.find_spec("ibm_db_dbi") is not None
        if not has_driver:
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=elapsed(),
                detail="ibm_db driver missing — audit writes disabled "
                "(install requirements-integration.txt, M2).",
            )
        timeout = max(self._settings.db2_connect_timeout_ms / 1000, 0.2)
        try:
            with socket.create_connection(
                (self._settings.db2_host, self._settings.db2_port), timeout=timeout
            ):
                pass
        except OSError as exc:
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=elapsed(),
                detail=f"Db2 not reachable — audit writes disabled "
                f"({exc.strerror or exc}).",
            )
        return ProbeResult(
            name=self.probe_name,
            status="ok",
            mode=self.mode,
            latency_ms=elapsed(),
            detail=f"Audit writes enabled (APP_AUDIT @ {self._settings.db2_host})",
        )

    # -- writes / reads ------------------------------------------------------
    def _connect(self):
        try:
            import ibm_db_dbi
        except ImportError as exc:
            raise AdapterUnavailableError(
                "ibm_db driver is not installed — audit persistence unavailable "
                "(pip install -r requirements-integration.txt, M2)."
            ) from exc
        dsn, user, password = connect_args(self._settings)
        try:
            return ibm_db_dbi.connect(dsn, user, password)
        except Exception as exc:
            raise AdapterUnavailableError(
                f"Cannot connect to Db2 for audit write: "
                f"{sanitize(str(exc), self._settings)}"
            ) from exc

    def record(self, entry: AuditRecord) -> int:
        if self._closed:
            raise AdapterUnavailableError("audit adapter closed")
        conn = self._connect()
        try:
            cursor = conn.cursor()
            # sql_text is not carried on AuditRecord in M1 (question only);
            # M2 extends the record with generated SQL.
            cursor.execute(
                _INSERT_SQL,
                (
                    entry.intent,
                    entry.question,
                    None,
                    entry.status,
                    entry.latency_ms,
                    entry.request_id,
                ),
            )
            conn.commit()
            new_id = getattr(cursor, "lastrowid", None)
            return int(new_id) if isinstance(new_id, int) else 0
        except AdapterUnavailableError:
            raise
        except Exception as exc:
            raise AdapterUnavailableError(
                f"Audit write failed: {sanitize(str(exc), self._settings)}",
                detail={"error_type": type(exc).__name__},
            ) from exc
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def list_recent(self, limit: int = 50) -> list[AuditRecord]:
        if self._closed:
            raise AdapterUnavailableError("audit adapter closed")
        conn = self._connect()
        try:
            cursor = conn.cursor()
            # Db2 does not allow parameter markers in FETCH FIRST — cap in Python.
            safe_limit = max(1, min(limit, 500))
            cursor.execute(
                "SELECT AUDIT_ID, REQ_TS, INTENT, QUESTION, STATUS, LATENCY_MS "
                "FROM APP_AUDIT ORDER BY AUDIT_ID DESC "
                f"FETCH FIRST {safe_limit} ROWS ONLY"
            )
            entries: list[AuditRecord] = []
            for audit_id, req_ts, intent, question, status, latency_ms in cursor.fetchall():
                if isinstance(req_ts, datetime):
                    ts = req_ts.isoformat()
                else:
                    ts = str(req_ts)
                entries.append(
                    AuditRecord(
                        id=int(audit_id),
                        timestamp=ts,
                        intent=str(intent or ""),
                        question=str(question or ""),
                        status=str(status or ""),
                        latency_ms=int(latency_ms or 0),
                    )
                )
            return entries
        except AdapterUnavailableError:
            raise
        except Exception as exc:
            raise AdapterUnavailableError(
                f"Audit read failed: {sanitize(str(exc), self._settings)}",
                detail={"error_type": type(exc).__name__},
            ) from exc
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def close(self) -> None:
        self._closed = True
