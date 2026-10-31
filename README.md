# Db2 Ops Copilot

**Hybrid RAG + guardrailed text-to-SQL copilot over IBM Db2** — built for the
IBM Db2 TechX Summit 2026.

Ask questions in natural language. The copilot either retrieves grounded
answers from a knowledge base stored *inside* Db2 (RAG via `DB2VS` vector
search) or generates **validated, read-only** Db2 SQL — every statement must
pass an AST-based safety gate before it is even shown, and every request is
audited into a Db2 table.

> **M1 status — portable foundation complete.** The app runs fully offline
> with deterministic mock adapters. Genuine Db2 + Ollama integrations are
> implemented but unvalidated (M2 — pending infrastructure bring-up on an
> approved machine). See `HANDOFF.md` for the M2 plan.

## Quick start (offline — zero services required)

```bash
# 1. Backend (mock mode is the default)
python -m venv .venv && .venv\Scripts\pip install -r requirements-dev.txt
cd backend
python -m uvicorn app.main:app --reload --port 8000

# 2. Frontend (dev server with /api proxy → :8000)
cd frontend
npm install
npm run dev            # http://127.0.0.1:5173
```

Or run the backend only and open **http://127.0.0.1:8000** — it serves the
built frontend automatically when `frontend/dist` exists (`npm run build`).

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/health` | Liveness + per-adapter probes (200 even when services are down) |
| `GET /api/v1/status` | Dashboard: database, vector store, LLM, embeddings |
| `GET /api/v1/config` | Effective **non-secret** configuration |
| `POST /api/v1/chat` | Copilot flow (RAG / text-to-SQL, auto-routed) |
| `POST /api/v1/sql/validate` | The SQL safety gate, exposed for the UI |
| `GET /api/v1/audit` | Recent audit entries |

Interactive docs: http://127.0.0.1:8000/docs · Full contract: [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md)

## Architecture at a glance

```
UI (React SPA) → FastAPI /api/v1 → Services → Adapter registry
                                                 ├── mock adapters  (offline, deterministic)
                                                 └── real adapters  (Db2 · Ollama · LangChain)
 every generated SQL ──▶ sqlglot/db2 AST gate (SELECT-only, fail-closed) ──▶ read-only DB account
 every request        ──▶ APP_AUDIT (Db2) / in-memory audit (mock)
```

Details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · Security defaults documented there too.

## Configuration

Copy `.env.example` to `.env` and fill in locally — **never commit `.env`**
(gitignored and CI-verified). Every variable is documented inline. Key switch:

| Variable | Values | Effect |
|---|---|---|
| `ADAPTER_MODE` | `mock` (default) / `real` | Mock = fully offline. Real = genuine Db2 + Ollama adapters |

## Going real (M2 — on an infrastructure-enabled machine)

1. Install IBM Db2 Community Edition (Docker, `icr.io/db2_community/db2`, ≥ 12.1.2) — see [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).
2. Install Ollama + pull `granite4.2:3b` and `nomic-embed-text:v1.5`.
3. `pip install -r requirements-integration.txt` (pinned `ibm_db`, LangChain stack).
4. Apply `database/migrations/` in order (see [`database/README.md`](database/README.md)).
5. Set `ADAPTER_MODE=real` in `.env`.

## Testing

```bash
.venv\Scripts\python -m pytest backend/tests -q   # 100 offline tests
cd frontend && npm run build                      # strict TS + production bundle
```

See [`docs/TESTING.md`](docs/TESTING.md) for the test taxonomy — real-service
integration tests are **pending** and clearly separated from offline/mock tests.

## Repository layout

```
backend/app/          FastAPI app: api/ core/ services/ adapters/ security/ schemas/
backend/tests/        Offline test suite (pytest)
frontend/             React 19 + TypeScript + Vite SPA
database/migrations/  Db2 SQL scripts (authored, not yet executed — M2)
docs/                 Architecture, API contract, development, testing, deployment
```

## License

MIT — see [LICENSE](LICENSE).
