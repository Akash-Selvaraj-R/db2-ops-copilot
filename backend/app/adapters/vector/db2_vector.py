"""REAL Db2 vector-store adapter (langchain-db2 ``DB2VS`` integration point).

Status (M1): interface + availability probes are implemented; the DB2VS
wiring itself is explicitly deferred to M2 and raises an actionable
``AdapterUnavailableError`` — the ``langchain-db2`` package is intentionally
not installed during M1 and no Db2 VECTOR-capable server exists yet.

This class is the LangChain touchpoint of the architecture: in M2 it holds a
``DB2VS`` instance (official worked example pattern) and delegates
``similarity_search`` / ``upsert_documents`` to it.

References:
- https://docs.langchain.com/oss/python/integrations/vectorstores/db2
- https://github.com/IBM/db2-ai-cookbook
"""

from __future__ import annotations

import importlib.util
import time

from app.adapters.base import DocumentInput, ProbeResult, VectorHit
from app.core.config import Settings
from app.core.errors import AdapterUnavailableError

_M2_DETAIL = (
    "DB2VS wiring is scheduled for M2: install requirements-integration.txt "
    "(langchain-db2), provision Db2 CE >= 12.1.2 with VECTOR support, run "
    "database/migrations, then construct DB2VS here (docs: "
    "https://docs.langchain.com/oss/python/integrations/vectorstores/db2)."
)


class Db2VectorStoreAdapter:
    """Vector operations backed by Db2 (DB2VS) — the production vector store."""

    probe_name = "vector_store"
    provider_id = "db2"
    mode = "real"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._closed = False

    # -- availability ------------------------------------------------------
    def _tcp_reachable(self) -> tuple[bool, str]:
        import socket

        timeout = max(self._settings.db2_connect_timeout_ms / 1000, 0.2)
        try:
            with socket.create_connection(
                (self._settings.db2_host, self._settings.db2_port), timeout=timeout
            ):
                return True, ""
        except OSError as exc:
            return False, str(exc.strerror or exc)

    def ping(self) -> ProbeResult:
        start = time.perf_counter()
        if self._closed:
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=0.0,
                detail="vector adapter closed",
            )
        elapsed = lambda: (time.perf_counter() - start) * 1000  # noqa: E731

        has_driver = importlib.util.find_spec("ibm_db") is not None
        has_langchain_db2 = importlib.util.find_spec("langchain_db2") is not None
        reachable, sock_error = self._tcp_reachable()

        if not reachable:
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=elapsed(),
                detail=(
                    f"Db2 not reachable at {self._settings.db2_host}:"
                    f"{self._settings.db2_port} ({sock_error}) — vector store "
                    "depends on Db2 (see DEPLOYMENT.md)."
                ),
            )
        if not (has_driver and has_langchain_db2):
            missing = [
                name
                for name, present in (
                    ("ibm_db", has_driver),
                    ("langchain-db2", has_langchain_db2),
                )
                if not present
            ]
            return ProbeResult(
                name=self.probe_name,
                status="unavailable",
                mode=self.mode,
                latency_ms=elapsed(),
                detail=(
                    f"Db2 reachable but required packages missing: "
                    f"{', '.join(missing)} (install requirements-integration.txt, M2)."
                ),
            )
        return ProbeResult(
            name=self.probe_name,
            status="unavailable",
            mode=self.mode,
            latency_ms=elapsed(),
            detail=f"Db2 reachable and packages present; {_M2_DETAIL}",
        )

    # -- operations (M2: delegate to DB2VS) ---------------------------------
    def _unavailable(self) -> AdapterUnavailableError:
        return AdapterUnavailableError(
            "Db2 vector store is not wired yet (M1 defines the interface; "
            "real DB2VS integration lands in M2).",
            detail={"m2_action": _M2_DETAIL},
        )

    def similarity_search(
        self, query: str, k: int = 4, filters: dict | None = None
    ) -> list[VectorHit]:
        raise self._unavailable()

    def upsert_documents(self, documents: list[DocumentInput]) -> int:
        raise self._unavailable()

    def count(self) -> int:
        raise self._unavailable()

    def close(self) -> None:
        self._closed = True
