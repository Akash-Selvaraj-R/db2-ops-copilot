# HANDOFF — Db2Hack Project (M1 — PAUSED)

**Current milestone:** **M1 — Infrastructure & Environment Setup — ⏸️ PAUSED by operator** (30 October 2026 IST). M1.1 inspection ✅ complete; M1.2 Docker migration attempted then **cancelled by operator** (deviation documented in `M1_ENVIRONMENT_REPORT.md` §2.4); **M1.3 Ollama / M1.4 Db2 / M1.5 venv / M1.6 PoC NOT started.**
**Implementation status:** ❗ **No application code, no dependencies installed, no database provisioned, no Ollama installed, no repo forked, nothing submitted.** Docker is fully stopped; all pre-existing data intact and backed up. See `M1_ENVIRONMENT_REPORT.md` for everything done and the exact resume plan.

---

## Completed research tasks (M0)

1. ✅ Inspected all mandatory official sources in full:
   - Summit website `https://ibmdb2techxsummit.glbajajgroup.ac.in/` (+ `/resources`, `/submit`) — a React SPA; content extracted from its production JS bundle (`/assets/index-D1oV8j9W.js`).
   - Official submission repo `https://github.com/KunalGolaIBM/IBM_Db2_TechX_Project_Submission` — README, CONTRIBUTING, PR template, `docs/submission-guide.md`, `docs/judging-criteria.md`, `docs/db2-setup-guide.md`, `docs/faq.md`, `submissions/README.md`, `submissions/_template/submission.json`, `scripts/validate_submission.py`, CI workflow.
   - IBM Db2 AI Cookbook `https://github.com/IBM/db2-ai-cookbook` — archived 3 Oct 2026, read-only, fully readable (8 modules: tabular search, multimodal embedding, hybrid search, RAG, agentic RAG, recommendation, in-DB ML, in-DB LLM calls).
2. ✅ Extracted and verified the **nine official Db2 toolkit packages** (names, install commands, doc URLs) — see `REQUIREMENTS_MATRIX.md` §3.
3. ✅ Verified all mandated AI frameworks and their local Python compatibility on PyPI (LangChain/Haystack/Langflow OK on 3.14; CrewAI/LlamaIndex/dbt blocked by version caps).
4. ✅ Audited the local Windows environment (`ENVIRONMENT_AUDIT.md`) — nothing modified.
5. ✅ Verified both Ollama model identifiers (`granite4.2:3b`, `nomic-embed-text:v1.5`) against ollama.com; neither installed locally.
6. ✅ Confirmed `ibm_db 3.3.0` ships a cp314 Windows wheel → Python 3.14.2 is viable for the Db2 driver + `langchain-db2`.
7. ✅ Developed and rubric-ranked **six** project concepts; recommended one (`PROJECT_CONCEPTS.md`).
8. ✅ Produced full architecture proposal with Mermaid diagrams, schema, API, security, error handling, demo workflow (`PROPOSED_ARCHITECTURE.md`).
9. ✅ Documented the exact GitHub submission workflow and drafted `submission.json` content (`SUBMISSION_GUIDE.md`).

## Verified technical decisions

- **Project:** "Db2 Ops Copilot" (working title) — hybrid **RAG + guardrailed text-to-SQL** where Db2 is both the vector store (`langchain-db2` `DB2VS`) and the live query target (SYSCAT introspection + sqlglot `db2-sqlglot-dialect` validation + EXPLAIN + read-only execution).
- **Framework:** LangChain (mandatory-listed; organizers' own worked example uses it). Haystack = fallback. CrewAI/LlamaIndex/Langflow not used (friction/reward).
- **Driver:** `ibm_db` (Python 3.14 wheel confirmed). Also using `db2-sqlglot-dialect` (official IBM SQLGlot plugin).
- **Models (local Ollama):** `granite4.2:3b` (generator) + `nomic-embed-text:v1.5` (embeddings, 768-dim). Fallbacks: sentence-transformers / watsonx.ai.
- **Database:** IBM Db2 Community Edition via Docker (`icr.io/db2_community/db2`) — provisioned via VS Code extension or `docker run` (decide in M1). Free, up to 4 cores/16 GB RAM.
- **App:** Python 3.14 + FastAPI + minimal web UI; zero API keys needed for demo.

## Unresolved questions (carry into M1)

1. ❓ **Rubric conflict:** website = 6 criteria incl. Security 15% (Db2 25/Inno 20/Arch 15/Sec 15/Repro 15/Docs 10) vs repo = 5 criteria (Db2 30/Inno 25/Arch 20/Repro 15/Docs 10). Design to the union; confirm with organisers.
2. ❓ **Deadline conflict:** repo says hard deadline 29 Oct 19:00 IST; live website (event day) says "no deadline today… not strict… closing time will be announced (WhatsApp)". Assume open but act fast; monitor WhatsApp.
3. ❓ Google Form link still a placeholder in the repo — obtain from the mandatory WhatsApp community / email.
4. ❓ Db2 Community Edition image version vs `VECTOR` type support (needs Db2 12.1.2+ per cookbook) — verify `db2level` after provisioning.
5. ❓ Measured inference latency of granite4.2:3b + nomic-embed-text on this CPU — unmeasured.
6. ❓ Whether DB2VS creates/uses vector indexes on CE, and its performance characteristics at demo scale.

## Local environment status (summary — details in `ENVIRONMENT_AUDIT.md`)

- ✅ Working: Git 2.52, Python 3.14.2, Node 24.14, npm 11.9, VS Code 1.143 (+ IBM Db2 ext 1.2.1), Java 25, Docker CLI 29.8, WSL2 Ubuntu, OpenCode; pip already has langchain 1.3.14 stack + SQLAlchemy.
- ⚠️ Docker Desktop 4.93 installed but **daemon not running**.
- ❌ Missing: Ollama (+ both models), `ibm_db`, `langchain-db2`, any Db2 server.
- 🔴 **C: drive only 3.4 GB free** → relocate Docker/Ollama/HF storage to **E:** (123.7 GB free) before provisioning. RAM 16 GB, ~4.5 GB free — co-residency test needed.

## Important official URLs

- Summit site: https://ibmdb2techxsummit.glbajajgroup.ac.in/ · /resources · /submit
- Submission repo: https://github.com/KunalGolaIBM/IBM_Db2_TechX_Project_Submission
- Db2 AI Cookbook: https://github.com/IBM/db2-ai-cookbook (archived, readable)
- langchain-db2: https://pypi.org/project/langchain-db2/ · docs: https://docs.langchain.com/oss/python/integrations/vectorstores/db2
- ibm_db: https://pypi.org/project/ibm_db/ · SQLGlot plugin: https://github.com/IBM/db2-sqlglot-plugin
- VS Code Db2 extension docs: https://ibm.github.io/db2developerextension-about/ (create-instance guide: …/docs/the-basics/creating-db2-instance)
- Db2 CE installer: https://www.ibm.com/db2/get-started · Docker image `icr.io/db2_community/db2`
- Ollama models: https://ollama.com/library/granite4.2 · https://ollama.com/library/nomic-embed-text
- Official tutorials: YouTube @IBMProductHub (Langflow NRo4ePT2MEE, Haystack T3it5_2JwIw, CrewAI qZnhCnwGttg)
- Organizers: Dhruv Chaturvedi (SPOC, IBM), Kunal Gola (repo maintainer, IBM)

## M1 progress so far (30 October 2026)

1. ✅ **M1.1 inspection complete** — drives (C: 11.4 GB / D: 141.2 GB / E: 123.6 GB free), Docker 4.93 + server 29.8.1, WSL2 (Ubuntu + docker-desktop), Python 3.14.2 / pip 26.2.1, no Ollama, Git repo `main` with **zero commits and no remote**. Full detail: `M1_ENVIRONMENT_REPORT.md` §1.
2. ⚠️ **M1.2 Docker→E: migration attempted, cancelled by operator.** Other projects' 6 containers stopped (approved; nothing removed). 3 volumes backed up to `E:\DockerBackups\` (23.8 MB). Three migration routes failed to trigger the move (config key `vm.resources.wslDataFolder` discovered in `app.asar`, but Docker Desktop only migrates via its own UI picker pipeline). Operator chose to cancel and close Docker. Docker fully stopped; data intact on C:. **Deviation: Docker workload storage is NOT on E: — re-decide at resume** (`M1_ENVIRONMENT_REPORT.md` §2).

## Exact next steps for M1 resume (upon explicit operator approval)

1. Decide Docker storage: retry the supported UI picker migration (Settings → Resources → pick `E:\Docker` → Apply & restart) **or** accept C: (11.4 GB free — re-check before the ~2–4 GB Db2 pull).
2. M1.3: Install Ollama to D: (`/VERYSILENT /DIR="D:\Ollama"`); `OLLAMA_MODELS=E:\future\ollama-models`; verify model dir on E: **before** pulling `granite4.2:3b` + `nomic-embed-text:v1.5`; test listing/chat/embedding.
3. M1.4: Provision Db2 CE (`icr.io/db2_community/db2`, tag ≥12.1.2); record `db2level`; 127.0.0.1-only port; passwords generated programmatically into gitignored env files (never echoed); persistent volume on E:; healthcheck; read-only account; verify VECTOR.
4. M1.5: `.venv` at `E:\future\Db2Hack\.venv`; pinned deps (`ibm_db==3.3.0`, `langchain==1.3.14`, `langchain-community==0.4.2`, `langchain-ollama==1.1.0`, `langchain-db2==1.0.0`, `sqlglot`, `db2-sqlglot-dialect==1.1.0`; confirm pins at install time); `PIP_CACHE_DIR=E:\future\pip-cache`; verify imports + connectivity.
5. M1.6: DB2VS round-trip PoC in `m1-poc/` (≥3 docs, similarity_search_with_score, metadata, reconnect persistence; real Db2 only — no FAISS/Chroma/in-memory).
6. Wrap-up: `.gitignore` review, `M1 completion report`, HANDOFF update. **⚠️ BLOCKED: the existing GitHub repository URL must be supplied by the operator — the repo has no remote and the brief forbids creating a new one.** Then commit + push.
7. Later milestones: build in stages — (a) RAG core, (b) text-to-SQL with sqlglot gate, (c) audit + UI + docs + tests. Parallel submission prep: fork repo → branch `submission/db2-ops-copilot` → copy template → draft docs; join WhatsApp; get Form link; confirm rubric + closing time.
8. Record demo video + screenshots; run official validator; open PR; submit Form; publish LinkedIn post.

**⚠️ M1 is NOT complete. Resume only on explicit operator approval. Do not auto-start M1. Do not restart Docker without asking — operator paused all Docker activity.**
