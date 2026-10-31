# Testing

**Rule: every M1 test runs offline.** No Docker, no Db2, no Ollama, no model
downloads, no network beyond loopback (`127.0.0.1`).

## Commands

```powershell
# Backend — full offline suite
.venv\Scripts\python -m pytest backend/tests -q

# Frontend — strict type-check + production build
cd frontend; npm run build
```

## Test taxonomy — read this before trusting a green run

| # | Category | Status | What it proves |
|---|---|---|---|
| 1 | **Offline unit tests** | ✅ passing | Validation gate, injection rules, config validation, mock adapter behavior, error envelope |
| 2 | **Mock integration tests** | ✅ passing | Full HTTP request → service → mock adapter flows via FastAPI `TestClient` (no real services) |
| 3 | Real Db2 integration tests | ⏳ **pending (M2)** | Connection, readonly execution, SYSCAT introspection, `APP_AUDIT` writes against a live Db2 CE instance |
| 4 | Real Ollama inference tests | ⏳ **pending (M2)** | `granite4.2:3b` generation + `nomic-embed-text` embeddings against a live Ollama server |
| 5 | Real Db2 vector retrieval tests | ⏳ **pending (M2)** | `DB2VS` round trip: upsert → `similarity_search_with_score` → metadata filters → persistence after reconnect |

**A passing suite in categories 1–2 says NOTHING about real-service
behavior.** Never report mock tests as real integration tests. Categories 3–5
are written only once infrastructure exists and are marked `@pytest.mark.integration`.

## Backend coverage map (`backend/tests/`)

| File | Requirement §9 coverage |
|---|---|
| `test_app.py` | Application startup, root, request-id middleware, 404/422 envelopes, OpenAPI surface |
| `test_health_status.py` | Health endpoint, degraded-not-down probe behavior, status endpoint, no secret leakage |
| `test_config.py` | Config loading, env overrides, missing env vars → safe defaults, invalid config rejected (`environment`, `adapter_mode`, `injection_mode`, `log_level`, port range), `SecretStr` never serialized |
| `test_sql_security.py` | Valid SELECT · INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE/GRANT/MERGE rejection · `SELECT INTO` · multi-statement · malformed fail-closed · empty/NUL/control chars · over-length · catalog deny-list · denied functions · join/IN-list/subquery limits · row-limit advisory · policy echo |
| `test_injection.py` | Attack detection, benign pass-through, block raises, flag verdicts, `off` mode, **layering check**: SQL-payload phrasing belongs to the SQL gate |
| `test_adapters.py` | Mock DB (SELECT, `FETCH FIRST`, non-SELECT refusal, schema), mock vector (scoring, filters, upsert), mock LLM/embeddings determinism, mock audit, orchestrator intents + gate-passing SQL, **registry DI: mock mode vs real mode — real never instantiates mocks**, probes never raise, idempotent shutdown |
| `test_chat_api.py` | Chat docs/data flows, mode override, injection → 400, audit append (incl. `BLOCKED`), SQL validate outcomes, limits validation, no secret leakage |
| `test_repo_hygiene.py` | No credential-like literals in source, `.env.example` placeholders only, `.env` never git-tracked, `.gitignore` coverage |

Current run: **100 passed** (offline).

## Frontend checks

- `npm run build` = `tsc -b` (strict) **and** production bundle — a type-level
  contract check against `src/api/types.ts`, which mirrors the backend models.
- Behavior verified by the M1 smoke procedure below (manual, offline).

## Smoke test (end-to-end, offline)

1. `cd backend; python -m uvicorn app.main:app --port 8000`
2. `cd frontend; npm run build` (backend then serves the SPA at `/`)
3. `GET /api/v1/health` → `status: ok`, `mode: mock`, 6 checks
4. `GET /api/v1/status` → database/vector/llm/embeddings populated
5. `POST /api/v1/chat {"message":"What is DB2VS?"}` → `intent: docs`, citations, `mock: true`
6. `POST /api/v1/chat {"message":"List servers by uptime"}` → `sql` present; re-submit that SQL to `/api/v1/sql/validate` → `valid: true`
7. `POST /api/v1/chat` with an instruction-override message → 400 `PROMPT_INJECTION_BLOCKED`
8. UI at `/` renders Dashboard, sends a chat message, shows config — all without Docker/Db2/Ollama

## Notes

- Tests construct fresh apps and clear the settings cache per fixture, so env
  pollution between tests is impossible.
- `TestClient` is used with `raise_server_exceptions=False` so the global
  500-envelope handler itself is exercised where relevant.
