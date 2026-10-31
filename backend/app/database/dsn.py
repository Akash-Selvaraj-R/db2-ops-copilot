"""DSN / connection helpers for the real Db2 adapters.

Security notes:
- The DSN NEVER contains credentials; uid/pwd are passed separately so DSN
  strings can appear in logs without leaking secrets.
- Error messages are sanitized (password value stripped) before surfacing.
"""

from __future__ import annotations

from app.core.config import Settings


def build_dsn(settings: Settings) -> str:
    """Build an ibm_db DSN (no credentials inside)."""
    return (
        f"DATABASE={settings.db2_dbname};"
        f"HOSTNAME={settings.db2_host};"
        f"PORT={settings.db2_port};"
        f"PROTOCOL=TCPIP;"
    )


def connect_args(settings: Settings) -> tuple[str, str, str]:
    """Return ``(dsn, user, password)`` for ``ibm_db_dbi.connect``."""
    return (
        build_dsn(settings),
        settings.db2_ro_user,
        settings.db2_ro_password.get_secret_value(),
    )


def sanitize(message: str, settings: Settings) -> str:
    """Strip any credential material from an error message."""
    password = settings.db2_ro_password.get_secret_value()
    cleaned = message
    if password:
        cleaned = cleaned.replace(password, "***")
    return cleaned[:300]
