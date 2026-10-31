"""SQL validation schemas (shared by the validator and the API)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import StrictModel

Severity = Literal["error", "warning"]


class Violation(StrictModel):
    code: str
    message: str
    severity: Severity = "error"


class SqlValidateRequest(StrictModel):
    sql: str = Field(min_length=1, max_length=5000)


class AppliedPolicy(StrictModel):
    max_rows: int
    timeout_ms: int
    enforce_row_limit: bool


class SqlValidateResponse(StrictModel):
    valid: bool
    statement_type: str | None = None
    dialect: str | None = None
    normalized_sql: str | None = None
    violations: list[Violation] = Field(default_factory=list)
    warnings: list[Violation] = Field(default_factory=list)
    policy: AppliedPolicy
