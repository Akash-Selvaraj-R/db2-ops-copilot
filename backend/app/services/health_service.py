"""Business services — thin orchestration over adapters (adapter-agnostic)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.adapters.registry import AdapterRegistry
from app.core.config import Settings
from app.schemas.common import HealthResponse, Probe

logger = logging.getLogger(__name__)


class HealthService:
    """Aggregates adapter probes into the /api/v1/health payload."""

    def __init__(self, settings: Settings, registry: AdapterRegistry) -> None:
        self._settings = settings
        self._registry = registry

    def health(self, started_at: float) -> HealthResponse:
        probes = self._registry.probes()
        checks = [
            Probe(
                name=p.name,
                status=p.status,
                mode=p.mode,
                latency_ms=round(p.latency_ms, 2),
                detail=p.detail,
            )
            for p in probes
        ]
        overall = "ok" if all(c.status == "ok" for c in checks) else "degraded"
        return HealthResponse(
            status=overall,
            version=self._settings.app_version,
            api_version="v1",
            mode=self._settings.adapter_mode,
            uptime_seconds=round(max(time.time() - started_at, 0.0), 3),
            timestamp=datetime.now(timezone.utc).isoformat(),
            checks=checks,
        )
