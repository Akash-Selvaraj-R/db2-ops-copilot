# Database setup — IBM Db2 Community Edition

> **M1 status:** scripts are authored and reviewed but **never executed** — no
> Db2 instance exists on the development machine (portable-first constraint).
> Real execution happens in M2; see `HANDOFF.md`.

## Contents

| File | Purpose |
|---|---|
| `migrations/001_app_schema.sql` | `APP` schema: demo tables, `APP_AUDIT`, `KB_CHUNKS` (VECTOR 768) |
| `migrations/002_indexes.sql` | Indexes for incidents + audit reads |
| `migrations/003_readonly_user.sql` | Least-privilege grants for the `db2ro` account |

## Prerequisites (M2)

1. Docker running with the official image: `icr.io/db2_community/db2` (tag ≥ 12.1.2 — `VECTOR` support required; verify with `db2level`).
2. Instance created with a locally generated password in the gitignored `.env` (`DB2_INSTANCE_PASSWORD`).
3. Port bound to `127.0.0.1` only. Never expose the Db2 port publicly.
4. Target database created (default `testdb`, see `DB2_DBNAME`).

## How to run (M2)

Connect as the instance owner (`db2inst1`) to the target database and apply
migrations **in numeric order**:

```
db2 -tvf database/migrations/001_app_schema.sql
db2 -tvf database/migrations/002_indexes.sql
db2 -tvf database/migrations/003_readonly_user.sql   # after substituting :ro_user / :ro_password
```

## Schema overview

```
APP
├── DEMO_SERVERS      synthetic fleet  (text-to-SQL demo target)
├── DEMO_INCIDENTS    synthetic incidents
├── APP_AUDIT         every copilot request: intent, question, SQL, status, latency
└── KB_CHUNKS         RAG knowledge base: CONTENT + VECTOR(768, FLOAT32) + JSON metadata
```

## Security notes

- The app runs as `db2ro`: SELECT on business tables, SELECT+INSERT on `APP_AUDIT`, nothing else. See `003_readonly_user.sql`.
- Generated SQL is validated by the sqlglot gate (`SELECT`-only, single statement, catalog deny-list) **and** executed under these grants — the grants are the real boundary.
- Passwords are generated locally and stored only in `.env` (gitignored). They never appear in source, scripts, logs, or commits.
- `KB_CHUNKS` mirrors the layout `langchain-db2` `DB2VS` is expected to manage; the final layout will be confirmed against the real `DB2VS` in M2.
