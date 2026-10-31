"""Shared response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

ProbeStatus = Literal["ok", "degraded", "unavailable"]


class StrictModel(BaseModel):
    """Base model: response payloads must match exactly (contract tests)."""

    model_config = ConfigDict(extra="forbid")


class ErrorBody(StrictModel):
    code: str
    message: str
    request_id: str
    detail: Any | None = None


class ErrorResponse(StrictModel):
    error: ErrorBody


class Probe(StrictModel):
    """Health probe result for one backing service."""

    name: str
    status: ProbeStatus
    mode: Literal["mock", "real"]
    latency_ms: float
    detail: str


class HealthResponse(StrictModel):
    status: Literal["ok", "degraded"]
    version: str
    api_version: str
    mode: Literal["mock", "real"]
    uptime_seconds: float
    timestamp: str
    checks: list[Probe]
