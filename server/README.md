# Corporate RAG AI-Agent — `server/`

Корпоративный RAG-агент (прототип). Здесь же: архитектура, правила, план и код API. Реализация — по фазам в `dev_plan.xml`. Phase 1 skeleton: FastAPI entry + stub handlers (`501`), ports/`Stub*`, LangGraph placeholders — **no** real RAG/DB wiring.

**Default is stubs-first:** `USE_STUBS=true` (and per-adapter `*_USE_STUB=true`). Local/CI must not need live LLM, embeddings, Qdrant, Docling, or Postgres.

## Workflow & run commands

All commands from the `server/` directory.

### 1. Install

```bash
cd server

# Option A — pip + venv
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -U pip
pip install -e ".[dev]"

# Option B — uv (faster)
# uv venv && source .venv/bin/activate
# uv pip install -e ".[dev]"
```

Optional extras (later phases / live adapters): `pip install -e ".[dev,persistence,vector]"`.

### 2. Environment

```bash
cp .env.example .env
# Keep USE_STUBS=true and *_USE_STUB=true for local/CI.
# Set real values in .env only when you intentionally flip stubs off
# (e.g. $LLM_BASE_URL, $EMBEDDINGS_BASE_URL, $QDRANT_URL, $DOCLING_BASE_URL,
#  $DATABASE_URL, $QUALITY_SERVICE_EMAIL — see .env.example).
```

Never commit `.env`. Hosts, ports, and provider URLs come from `.env` (not hardcoded below). Full key list: [.env.example](.env.example).

### 3. Run API (skeleton)

```bash
set -a && source .env && set +a   # load $APP_HOST, $APP_PORT, …
# Stubs on — no outbound AI/infra calls
USE_STUBS=true uvicorn app.main:app --reload --host "${APP_HOST}" --port "${APP_PORT}"
```

- Health: `GET http://${APP_HOST}:${APP_PORT}/health` → `{"status":"ok"}`  
  (use a client-reachable host when `${APP_HOST}` is a bind address)
- OpenAPI: `http://${APP_HOST}:${APP_PORT}/docs`
- Business routes under `${API_PREFIX}/...` exist but return **501** until later phases

### 4. Tests (default = stubs)

```bash
USE_STUBS=true pytest
# or: python -m pytest
```

### 5. Optional live flags (gated; skip if secrets/infra missing)

Live suites must not fail CI when infra is absent — see [rules/testing_rules.xml](rules/testing_rules.xml). Configure endpoints in `.env` first (`$LLM_BASE_URL`, `$EMBEDDINGS_BASE_URL`, `$QDRANT_URL`, `$DOCLING_BASE_URL`, `$DATABASE_URL`, keys, etc.).

```bash
# Broader live integration (requires real backends + secrets in .env)
USE_STUBS=false RUN_LIVE_TESTS=1 pytest -m integration

# Per-adapter smoke (flip matching stub off + set the RUN_LIVE_* gate)
USE_STUBS=false LLM_USE_STUB=false RUN_LIVE_LLM=1 pytest -m integration            # needs $LLM_BASE_URL
USE_STUBS=false EMBEDDINGS_USE_STUB=false RUN_LIVE_EMBEDDINGS=1 pytest -m integration  # $EMBEDDINGS_BASE_URL
USE_STUBS=false QDRANT_USE_STUB=false RUN_LIVE_QDRANT=1 pytest -m integration      # $QDRANT_URL
USE_STUBS=false DOCLING_USE_STUB=false RUN_LIVE_DOCLING=1 pytest -m integration    # $DOCLING_BASE_URL
USE_STUBS=false PERSISTENCE_USE_STUB=false RUN_LIVE_POSTGRES=1 pytest -m integration  # $DATABASE_URL

# Full appeal flows against real stack (when implemented)
USE_STUBS=false RUN_LIVE_E2E=1 pytest -m integration
```

## Artifacts (LLM / agents)

| Path | Purpose |
|------|---------|
| [project_context.md](project_context.md) | Goals, stack (LangGraph, PostgreSQL), architecture, REST, RAG, tests |
| [ANCHOR.md](ANCHOR.md) | How to write module `ANCHOR` / `PURPOSE` / `Dependencies` headers |
| [CLIENT_INFO.md](CLIENT_INFO.md) | REST contract for future client AI agent |
| [semantic_graph.xml](semantic_graph.xml) | Modules and relationships |
| [dev_plan.xml](dev_plan.xml) | Phased implementation plan |
| [rules/coding_standards.xml](rules/coding_standards.xml) | Python / layout / stubs / LangGraph / Postgres |
| [rules/security_rules.xml](rules/security_rules.xml) | Secrets, PII, SSRF, DB |
| [rules/testing_rules.xml](rules/testing_rules.xml) | Stub CI + live integration/e2e |
| [rules/anchor_standards.xml](rules/anchor_standards.xml) | Grounding, clarify, escalate, learn + module markup |
| [.env.example](.env.example) | All env keys (stubs by default; Postgres `DATABASE_URL`) |
| [pyproject.toml](pyproject.toml) | Packaging, deps, pytest/ruff/mypy |

## Package layout (mirrors `project_context` / `semantic_graph`)

```text
server/app/
  api/                 # FastAPI routers + DTOs
  application/         # appeals, dialogue (LangGraph), grounding, retrieval, ingest, learning, quality_escalation
  domain/              # enums + entity skeletons
  adapters/            # llm, embeddings, vectorstore, docling, libreoffice, escalation, persistence, stubs
  config/              # Settings + DI factories
  logging/             # structured logging setup
server/tests/          # api, application, adapters, domain, integration
```

## Success criteria

1. Answers **only** from regulation content; otherwise escalate — no invention.
2. Clarifying dialogue when underspecified or ambiguous.
3. Continuous learning: officer canonical answer → KB update; log all appeals.

## Orchestration & persistence

- **LangGraph: yes** for dialogue graph. **Full LangChain RAG: no** — see `project_context.md` §2.1.
- **PostgreSQL** (SQLAlchemy async + asyncpg) stores appeals/messages/history/stats; `StubPersistence` for unit tests. Must survive restarts when stubs are off.
