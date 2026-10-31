"""GET /api/v1/health — liveness + dependency probes (never requires services)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import build_health_service, get_started_at
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health(request: Request, started_at: float = Depends(get_started_at)) -> HealthResponse:
    """Probe every configured adapter and report overall status.

    Returns HTTP 200 with ``status: degraded`` when services are unreachable
    (actionable per-check details), because the application itself is healthy.
    """
    service = build_health_service(request)
    return service.health(started_at)
