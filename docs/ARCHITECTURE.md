# Architecture — Db2 Ops Copilot

**Status:** M1 baseline (portable foundation). Design targets Db2 + Ollama as
first-class services; everything runs offline in mock mode meanwhile.

## 1. Goals

1. **Portable first** — develop and test with zero infrastructure; flip one
   env var (`ADAPTER_MODE=real`) to target genuine services.
2. **Defense in depth for text-to-SQL** — no single layer is "the" boundary.
3. **Honest mock/real separation** — mocks are visibly mock; production never
   silently falls back to canned data.

## 2. Layered view

```
┌─────────────────────────────────────────────────────────────────┐
│ Frontend  (React 19 + TS + Vite SPA, /frontend/dist served @ /) │
│   Dashboard · Chat workspace · Configuration                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP JSON (CORS allow-list)
┌──────────────────────────▼──────────────────────────────────────┐
│ API layer  (FastAPI, /api/v1)                                   │
│   health · status · config · chat · sql/validate · audit        │
│   request-id middleware · unified error envelope · CORS         │
├─────────────────────────────────────────────────────────────────┤
│ Services   ChatService · HealthService · StatusService          │
│            SqlGuardService                                      │
├─────────────────────────────────────────────────────────────────┤
│ Security   prompt-injection screening (block/flag/off)          │
│            sqlglot AST validation gate (fail-closed)            │
├─────────────────────────────────────────────────────────────────┤
│ Adapters   Protocols in adapters/base.py — selected by registry │
│   mock_*: offline & deterministic     real: Db2 · Ollama ·      │
│                                   LangChain (M2-validated)      │
├─────────────────────────────────────────────────────────────────┤
│ Db2 (M2)   APP_AUDIT · KB_CHUNKS (VECTOR 768) · demo tables     │
│            read-only account (db2ro) — grants are the boundary  │
└─────────────────────────────────────────────────────────────────┘
```

## 3. Key decisions (ADR-style)

| # | Decision | Rationale |
|---|---|---|
| 1 | **Adapter Protocols + registry** | The app core never imports a driver/SDK directly; mock↔real is a settings switch, not a code change. Runtime-checkable Protocols make contract tests possible. |
| 2 | **Mock is a separate class, never a fallback** | `ADAPTER_MODE=real` constructs only real classes. Real adapters return `unavailable` probes / raise `AdapterUnavailableError` when services are missing — never fake success. Prevents "mock disguised as production". |
| 3 | **sqlglot AST gate with IBM `db2` dialect** (`db2-sqlglot-dialect`) | Parse-level validation beats regex. Fail-closed: unparsable ⇒ rejected. Dialect-aware so Db2 syntax isn't falsely rejected in M2. |
| 4 | **Validation gate ≠ security boundary** | Independent enforcement: SELECT-only grants to `db2ro`, hard row cap + query timeout at execution (M2), parameterized app-owned queries, catalog deny-list, audit trail. Documented so static validation is never oversold. |
| 5 | **Health degrades, never dies** | `/health` returns 200 + `status: degraded` with per-probe detail when Db2/Ollama are absent. Startup must not depend on services (portable constraint). Probes run in parallel (loopback refusals cost ~2 s each). |
| 6 | **Secrets only as `SecretStr` + env** | Config dumps/logs/responses can never serialize a password; DSN excludes credentials by construction; error sanitizer strips password values. |
| 7 | **FastAPI serves the built SPA** | One origin in production (no CORS complexity); Vite dev server proxies `/api` during development. |
| 8 | **Services constructed per request, registry per app lifetime** | Tests can swap settings/registry cleanly via `dependency_overrides`; adapters keep their (future) connection state app-wide. |

## 4. Request lifecycle (chat)

1. ASGI middleware assigns/echoes `x-request-id` (logged on every line).
2. `ChatService.ask`:
   1. prompt-injection screen (`INJECTION_MODE=block` default → HTTP 400),
   2. orchestrator routes intent → RAG path (retrieve → grounded answer +
      citations) or text-to-SQL path (schema context → generate → **re-validate
      through the independent gate** — never trust the model's own claim),
   3. best-effort audit write (failures logged, response unaffected),
3. Response carries `mock`, intent, timings, warnings — UI shows honest badges.

## 5. SQL validation layers (fail-closed)

Implemented in `app/adapters/sql_validator/sqlglot_validator.py`:

1. Input hygiene — length cap, NUL/control characters, empty input
2. Parse gate — sqlglot `db2` dialect; unparsable ⇒ reject; **exactly one statement**
3. Statement allow-list — root must be `SELECT`
4. Forbidden nodes anywhere in the tree — Insert/Update/Delete/Merge/Create/Drop/Alter/Grant/…, `SELECT INTO`, `FOR UPDATE`
5. Catalog deny-list — SYSCAT, SYSIBM, SYSSTAT, SYSPROC, SYSIBMADM, SYSIBMSECURITY, SYSTOOLS
6. Function deny-list — `EXECUTEDIMMEDIATE`, `ADMIN_CMD`, `ADMIN_TASK`
7. Complexity limits — AST nodes, joins, subqueries, IN-list length
8. Row-limit advisory — warns when no `FETCH FIRST`/`LIMIT`; executor applies a hard cap anyway (M2)

**Beyond the gate (independent enforcement):** read-only Db2 account with
explicit GRANTs (`database/migrations/003_readonly_user.sql`), hard row cap +
`CURRENT QUERY TIMEOUT` at execution, parameterized qmark binding for all
app-owned queries, prompt-injection defense on the NL surface, audit trail.

**Honest limitation:** static validation cannot guarantee production security
by itself; it is one layer. The database permission model is the boundary.

## 6. Data model (Db2, authored — executed in M2)

| Table | Purpose |
|---|---|
| `APP.APP_AUDIT` | Every request: timestamp, intent, question, generated SQL, status, latency, client request id (identity PK) |
| `APP.KB_CHUNKS` | RAG knowledge base: `CONTENT CLOB`, `EMBEDDING VECTOR(768, FLOAT32)`, `METADATA JSON` (mirrors expected `DB2VS` layout) |
| `APP.DEMO_SERVERS`, `APP.DEMO_INCIDENTS` | Synthetic fleet for the text-to-SQL demo |
| Indexes | audit-by-time, intent, incident joins — `002_indexes.sql` |

## 7. Component map

```
backend/app/
├── main.py               app factory, lifespan, middleware, static mount
├── core/                 config (pydantic-settings), errors, logging
├── api/                  deps (DI), v1/ (health status config chat sql audit)
├── services/             chat · health · status · sql_guard
├── adapters/
│   ├── base.py           Protocols + value objects (the contracts)
│   ├── registry.py       mock/real selection + parallel probes
│   ├── db/               mock_db · db2_db (ibm_db, readonly exec + SYSCAT introspection)
│   ├── vector/           mock_vector · db2_vector (DB2VS wiring → M2)
│   ├── llm/              mock_llm · ollama_chat (/api/chat)
│   ├── embeddings/       mock_embeddings · ollama_embeddings (/api/embed)
│   ├── orchestration/    mock_orchestrator · langchain_orchestrator (RAG + text-to-SQL)
│   ├── audit/            mock_audit · db2_audit (APP_AUDIT)
│   └── sql_validator/    sqlglot gate (always "real" — local compute)
├── security/             sql_policy (rules) · injection (prompt defense)
├── schemas/              strict pydantic request/response models
└── database/             dsn builder + error sanitizer
```

## 8. Frontend

React 19 + TypeScript (strict) + React Router + Vite. No CSS framework —
design tokens in `styles.css`. The API client normalizes every failure into
`ApiClientError` (code/message from the backend envelope), which drives
consistent loading / error / empty states on all three pages.

## 9. Deferred to M2 (explicitly)

- `DB2VS` construction inside `Db2VectorStoreAdapter` (langchain-db2),
- real query execution path: EXPLAIN dry-run, row-cap wrapping, timeout,
  read-only account execution,
- LangChain prompt templates + bounded self-repair loop validation against a
  live model,
- `APP_AUDIT` write/read verification, vector round-trip PoC,
- Docker-based deployment (see DEPLOYMENT.md).
