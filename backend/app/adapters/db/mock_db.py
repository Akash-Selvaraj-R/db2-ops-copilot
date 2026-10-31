"""Mock database adapter — deterministic, offline, in-memory.

Used for development and automated tests. NOT the production implementation:
``ADAPTER_MODE=real`` selects :class:`app.adapters.db.db2_db.Db2DatabaseAdapter`.
"""

from __future__ import annotations

import re
import time
from typing import Any

from app.adapters.base import (
    ProbeResult,
    QueryResult,
    SchemaColumn,
    SchemaSnapshot,
    SchemaTable,
)
from app.core.config import Settings

_FETCH_RE = re.compile(r"FETCH\s+FIRST\s+(\d+)\s+ROW", re.IGNORECASE)

_SERVER_ROWS: list[list[Any]] = [
    [1, "db2-prod-01", "prod", "platform", 99.95],
    [2, "db2-prod-02", "prod", "platform", 99.87],
    [3, "db2-stage-01", "staging", "data-eng", 98.40],
    [4, "db2-dev-01", "dev", "data-eng", 92.10],
]

_INCIDENT_ROWS: list[list[Any]] = [
    [101, 1, 2, "2026-10-28 09:15:00", "2026-10-28 11:02:00"],
    [102, 3, 3, "2026-10-29 14:40:00", None],
    [103, 4, 1, "2026-10-30 08:05:00", "2026-10-30 08:31:00"],
    [104, 2, 4, "2026-10-30 10:22:00", None],
]


class MockDatabaseAdapter:
    """Simulated read-only Db2 session with canned demo data."""

    probe_name = "database"
    provider_id = "mock"
    mode = "mock"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()
        self._closed = False

    # -- lifecycle ------------------------------------------------------
    def ping(self) -> ProbeResult:
        if self._closed:
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=0.0,
                detail="mock adapter closed",
            )
        return ProbeResult(
            name=self.probe_name,
            status="ok",
            mode=self.mode,
            latency_ms=0.0,
            detail="mock Db2 adapter ready (no real connection)",
        )

    def close(self) -> None:
        self._closed = True

    # -- queries --------------------------------------------------------
    def execute_readonly(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
        timeout_ms: int | None = None,
    ) -> QueryResult:
        if self._closed:
            raise RuntimeError("mock adapter closed")
        start = time.perf_counter()
        upper = sql.upper()
        # Defense in depth: even the mock refuses anything that is not a read.
        first_word = sql.lstrip()[:6].upper()
        if not first_word.startswith(("SELECT", "WITH")):
            raise ValueError("mock database only executes SELECT/WITH statements")
        if params is not None and not isinstance(params, (list, tuple)):
            raise ValueError("params must be a positional sequence (qmark binding)")

        if "DEMO_INCIDENTS" in upper:
            columns = ["INCIDENT_ID", "SERVER_ID", "SEVERITY", "OPENED_AT", "RESOLVED_AT"]
            rows = [list(r) for r in _INCIDENT_ROWS]
        elif "DEMO_SERVERS" in upper:
            columns = ["SERVER_ID", "HOSTNAME", "ENVIRONMENT", "OWNER_TEAM", "UPTIME_PCT"]
            rows = [list(r) for r in _SERVER_ROWS]
        elif "COUNT(" in upper:
            columns = ["VALUE"]
            rows = [[len(_SERVER_ROWS)]]
        else:
            columns = ["RESULT"]
            rows = [["mock-row-1"], ["mock-row-2"]]

        # Apply FETCH FIRST n ROWS ONLY if present (mirrors Db2 behaviour).
        match = _FETCH_RE.search(sql)
        truncated = False
        if match:
            cap = int(match.group(1))
            if len(rows) > cap:
                rows = rows[:cap]
                truncated = True

        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    def fetch_schema(self) -> SchemaSnapshot:
        return SchemaSnapshot(
            source="mock",
            tables=[
                SchemaTable(
                    name="DEMO_SERVERS",
                    schema_name="APP",
                    columns=[
                        SchemaColumn("SERVER_ID", "INTEGER", False),
                        SchemaColumn("HOSTNAME", "VARCHAR(64)"),
                        SchemaColumn("ENVIRONMENT", "VARCHAR(16)"),
                        SchemaColumn("OWNER_TEAM", "VARCHAR(32)"),
                        SchemaColumn("UPTIME_PCT", "DECIMAL(5,2)"),
                    ],
                ),
                SchemaTable(
                    name="DEMO_INCIDENTS",
                    schema_name="APP",
                    columns=[
                        SchemaColumn("INCIDENT_ID", "INTEGER", False),
                        SchemaColumn("SERVER_ID", "INTEGER"),
                        SchemaColumn("SEVERITY", "INTEGER"),
                        SchemaColumn("OPENED_AT", "TIMESTAMP"),
                        SchemaColumn("RESOLVED_AT", "TIMESTAMP"),
                    ],
                ),
                SchemaTable(
                    name="KB_CHUNKS",
                    schema_name="APP",
                    columns=[
                        SchemaColumn("ID", "INTEGER", False),
                        SchemaColumn("CONTENT", "CLOB"),
                        SchemaColumn("EMBEDDING", "VECTOR(768, FLOAT32)", False),
                        SchemaColumn("METADATA", "JSON"),
                        SchemaColumn("CREATED_AT", "TIMESTAMP"),
                    ],
                ),
                SchemaTable(
                    name="APP_AUDIT",
                    schema_name="APP",
                    columns=[
                        SchemaColumn("AUDIT_ID", "BIGINT", False),
                        SchemaColumn("REQ_TS", "TIMESTAMP"),
                        SchemaColumn("INTENT", "VARCHAR(16)"),
                        SchemaColumn("QUESTION", "CLOB"),
                        SchemaColumn("SQL_TEXT", "CLOB"),
                        SchemaColumn("STATUS", "VARCHAR(16)"),
                        SchemaColumn("LATENCY_MS", "INTEGER"),
                    ],
                ),
            ],
        )
