"""Shared fixtures — every test runs fully offline against mock adapters."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture()
def app():
    """Fresh app instance with mock mode and a cleared settings cache."""
    get_settings.cache_clear()
    application = create_app()
    yield application
    application.state.registry.close_all()
    get_settings.cache_clear()


@pytest.fixture()
def client(app) -> TestClient:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
