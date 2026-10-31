"""SQL guard service — validation now; execution scaffolding for M2.

``validate()`` is the public gate used by ``POST /api/v1/sql/validate`` and the
chat pipeline. The M2 execution path (``prepare_for_execution``) will add:
EXPLAIN dry-run, row-limit wrapping, timeout application and execution under
the read-only Db2 account — the policy object already carries those limits.
"""

from __future__ import annotations

from app.adapters.sql_validator.sqlglot_validator import SqlGlotValidator
from app.schemas.sql import SqlValidateResponse
from app.security.sql_policy import SqlPolicy


class SqlGuardService:
    def __init__(self, validator: SqlGlotValidator) -> None:
        self._validator = validator

    @property
    def policy(self) -> SqlPolicy:
        return self._validator.policy

    def validate(self, sql: str) -> SqlValidateResponse:
        return self._validator.validate(sql)
