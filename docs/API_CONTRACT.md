# API Contract — v1

Base URL: `/api/v1` · Content type: `application/json` ·
Response models are **strict** (`extra=forbid`) — contract drift fails tests.

## Error envelope (all non-2xx)

```json
{ "error": { "code": "NOT_FOUND", "message": "…", "request_id": "…", "detail": null } }
```

| Code | HTTP | Source |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Pydantic request validation (`detail` = list) |
| `PROMPT_INJECTION_BLOCKED` | 400 | Chat message matched rules (`detail.matched_rules`) |
| `NOT_FOUND` / `METHOD_NOT_ALLOWED` / … | 404/405/… | Routing |
| `ADAPTER_UNAVAILABLE` | 503 | Real adapter cannot reach its service |
| `INTERNAL_ERROR` | 500 | Unhandled exception (logged with stack) |

Every response (success or error) carries `x-request-id`; an incoming
`X-Request-ID` header is echoed, otherwise one is generated and logged.

## GET /api/v1/health

Liveness + dependency probes. **Always 200** when the app itself runs — an
unreachable service is reported inside the payload, not as a failed request.

```json
{
  "status": "ok",                 // "ok" | "degraded"
  "version": "0.1.0", "api_version": "v1", "mode": "mock",
  "uptime_seconds": 12.5, "timestamp": "2026-10-31T…",
  "checks": [ { "name": "database", "status": "ok", "mode": "mock",
                "latency_ms": 0.0, "detail": "…" } ]
}
```
Checks: `database`, `vector_store`, `llm`, `embeddings`, `orchestrator`, `audit`.

## GET /api/v1/status

```json
{
  "timestamp": "…", "adapter_mode": "mock",
  "database":   { "provider", "connected", "host", "port", "database", "detail" },
  "vector_store": { "provider", "document_count", "detail" },
  "llm":        { "provider", "model", "available", "detail" },
  "embeddings": { "provider", "model", "available", "detail", "dimensions" }
}
```
**No passwords/tokens/credentials ever appear in this payload.**

## GET /api/v1/config

Effective non-secret configuration:

```json
{ "environment", "debug", "adapter_mode", "api_base", "cors_origins", "serve_frontend",
  "database": { "host", "port", "name", "read_only_user" },
  "models": { "llm", "embeddings", "ollama_base_url" },
  "sql_policy": { "allowed_statements", "max_sql_length", "max_ast_nodes",
                  "max_rows", "query_timeout_ms", "denied_schemas",
                  "enforce_row_limit" },
  "security": { "injection_mode", "max_message_length" } }
```

## POST /api/v1/chat

Request:
```json
{ "message": "…(1–4000 chars)", "mode": "auto|rag|sql", "session_id": null }
```
Response:
```json
{ "reply": "…", "intent": "docs|data|general",
  "citations": [ { "source", "title", "snippet", "score" } ],
  "sql": "SELECT …" | null,
  "mock": true, "request_id": "…",
  "timings": { "total_ms", "retrieval_ms", "generation_ms" },
  "warnings": ["missing_row_limit: …"] }
```
- `sql` is `null` unless it **passed the independent validation gate**.
- Injection matches with `INJECTION_MODE=block` → 400 `PROMPT_INJECTION_BLOCKED`.

## POST /api/v1/sql/validate

Request `{ "sql": "…" }` → **200 for every well-formed request** (invalid SQL
is a successful *validation outcome*, not an API error):

```json
{ "valid": false, "statement_type": "Delete", "dialect": "db2",
  "normalized_sql": null,
  "violations": [ { "code", "message", "severity" } ],
  "warnings": [],
  "policy": { "max_rows", "timeout_ms", "enforce_row_limit" } }
```
Key violation codes: `parse_error`, `multiple_statements`,
`statement_not_allowed`, `forbidden_construct`, `select_into`, `catalog_access`,
`denied_function`, `ast_too_large`, `too_many_joins`, `too_many_subqueries`,
`in_list_too_large`, `max_length_exceeded`, `empty_statement`, `null_byte`,
`control_characters`.

## GET /api/v1/audit?limit=50

`limit` ∈ [1, 500] (else 422).

```json
{ "entries": [ { "id", "timestamp", "intent", "question", "status",
                 "latency_ms", "detail", "request_id" } ],
  "total": 3, "mock": true }
```
`status` values: `OK`, `BLOCKED`, `ERROR`, `REJECTED_BY_GATE`.

## Other routes

`GET /` info · `GET /docs` Swagger UI · `GET /openapi.json` ·
static SPA at `/` when `frontend/dist` exists (`SERVE_FRONTEND=true`).
