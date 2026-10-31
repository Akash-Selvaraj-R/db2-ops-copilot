"""POST /api/v1/sql/validate — the SQL safety gate, exposed for the UI.

Returns HTTP 200 for every well-formed *request*: an invalid SQL statement is
a successful validation outcome (``valid: false`` + violations), not an API
error. Malformed requests (missing/oversized body) yield the standard 422
error envelope.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import build_sql_guard
from app.schemas.sql import SqlValidateRequest, SqlValidateResponse

router = APIRouter(tags=["sql"])


@router.post("/sql/validate", response_model=SqlValidateResponse)
def post_sql_validate(
    payload: SqlValidateRequest, request: Request
) -> SqlValidateResponse:
    guard = build_sql_guard(request)
    return guard.validate(payload.sql)
