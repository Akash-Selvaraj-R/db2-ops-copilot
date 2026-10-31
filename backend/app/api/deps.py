"""Dependency injection wiring.

Adapters live on ``app.state.registry`` (built once during startup lifespan);
services are constructed per request so tests can swap settings/registry
cleanly via ``app.dependency_overrides``.
"""

from __future__ import annotations

from fastapi import Request

from app.adapters.registry import AdapterRegistry
from app.core.config import Settings, get_settings
from app.services.chat_service import ChatService
from app.services.health_service import HealthService
from app.services.sql_guard_service import SqlGuardService
from app.services.status_service import StatusService


def get_app_settings() -> Settings:
    return get_settings()


def get_registry(request: Request) -> AdapterRegistry:
    return request.app.state.registry


def get_started_at(request: Request) -> float:
    return request.app.state.started_at


def build_health_service(request: Request) -> HealthService:
    return HealthService(get_settings(), get_registry(request))


def build_status_service(request: Request) -> StatusService:
    return StatusService(get_settings(), get_registry(request))


def build_chat_service(request: Request) -> ChatService:
    return ChatService(get_settings(), get_registry(request))


def build_sql_guard(request: Request) -> SqlGuardService:
    return SqlGuardService(get_registry(request).validator)
