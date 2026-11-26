# Corporate RAG AI-Agent — `server/`

Корпоративный RAG-агент (прототип). Архитектура, правила, план и код API живут здесь. Реализация — по фазам в `dev_plan.xml`.

**Default is stubs-first:** `USE_STUBS=true` (and per-adapter `*_USE_STUB=true`). Local/CI must not need live LLM, embeddings, Qdrant, Docling, or Postgres.

## What works under stubs (this vertical slice)

| Criterion | Behavior |
|-----------|----------|
| 1 Grounded answers | Fixture KB + LangGraph retrieve→ground→answer with citations |
| 2 Clarifying dialogue | Underspecified/ambiguous → `clarification` + status `clarifying` |
| 3 Continuous learning | Escalate → `officer-reply` → ingest into stub KB → later answers |
| REST | Appeals/messages/officer-reply/stats per `CLIENT_INFO.md` |
| Persistence | `StubPersistence` (default); `SqlAlchemyPersistence` + Alembic when stubs off |
| Logging | JSON logs + `X-Request-Id` middleware; appeal audit events |
| Connectivity | `rag-server check` + `GET /health/dependencies` (stubs always OK) |

## Workflow & run commands

All commands from the `server/` directory.

### 1. Install

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev,persistence]"
# optional live Qdrant: pip install -e ".[dev,persistence,vector]"
```

### 2. Environment

```bash
cp .env.example .env
# Keep USE_STUBS=true and *_USE_STUB=true for local/CI.
```

**Docs corpus (local only):** set `DOCS_CORPUS_PATH` (default `docs`) or `DOCS_DIR`. The folder is **gitignored** — create it locally for ingest (`mkdir -p docs`); do not commit regulation files.

### 3. Run API

```bash
set -a && source .env && set +a
USE_STUBS=true uvicorn app.main:app --reload --host "${APP_HOST}" --port "${APP_PORT}"
```

- Liveness: `GET /health` and `GET /api/v1/health`
- Dependencies: `GET /health/dependencies` (also under `/api/v1/…`) — per-service ok/fail + stub|live
- OpenAPI: `/docs` (FastAPI UI; unrelated to corpus path)
- Contract: [`CLIENT_INFO.md`](CLIENT_INFO.md)
- Scripted demo: [`DEMO.md`](DEMO.md)

### 4. Connectivity check (CLI)

After `pip install -e ".[dev,…]"` the `rag-server` console script is on your environment’s script path (ensure that directory is on `PATH`, e.g. `~/.local/bin` for user installs).

```bash
USE_STUBS=true rag-server check
# equivalent without relying on PATH:
USE_STUBS=true python3 -m app.cli check
```

Prints `overall` plus lines for `llm`, `embeddings`, `qdrant`, `docling`, `postgres`. Exit `0` when all OK. With stubs, all should report `mode=stub` and `OK`. Live mode uses the same command after flipping the matching `*_USE_STUB=false` flags (and restarting any long-lived API process so DI cache picks up env).

Optional Docling file ingest (live Docling + embeddings + Qdrant):

```bash
rag-server ingest-docx /path/to/reg.docx --title "Procurement"
# or: python3 -m app.cli ingest-docx /path/to/reg.docx
```

### 5. Tests (default = stubs)

```bash
USE_STUBS=true pytest
```

Connectivity unit tests assert stub pings are healthy. Live pings: `RUN_LIVE_LLM`, `RUN_LIVE_EMBEDDINGS`, `RUN_LIVE_QDRANT`, `RUN_LIVE_DOCLING`, `RUN_LIVE_POSTGRES`.

### 6. Optional live flags

```bash
USE_STUBS=false PERSISTENCE_USE_STUB=false RUN_LIVE_POSTGRES=1 pytest -m integration
USE_STUBS=false LLM_USE_STUB=false RUN_LIVE_LLM=1 pytest -m integration
USE_STUBS=false RUN_LIVE_E2E=1 pytest -m integration
```

Live suites **skip** when flags/secrets are absent.

### 7. Alembic (when using Postgres)

```bash
# DATABASE_URL=postgresql+asyncpg://...
alembic upgrade head
```

## Artifacts

| Path | Purpose |
|------|---------|
| [project_context.md](project_context.md) | Goals, stack, architecture |
| [CLIENT_INFO.md](CLIENT_INFO.md) | REST contract |
| [dev_plan.xml](dev_plan.xml) | Phased plan |
| [DEMO.md](DEMO.md) | Three success-criteria scenarios |
| [rules/](rules/) | Coding / security / testing / anchors (`anchor_standards.xml`) |
| [.env.example](.env.example) | All env keys |

## Package layout

```text
server/app/
  api/                 # FastAPI routers + DTOs
  application/         # appeals, dialogue (LangGraph), grounding, retrieval, ingest, learning, quality_escalation
  domain/
  adapters/            # llm, embeddings, vectorstore, docling, libreoffice, escalation, persistence, stubs
  config/
  logging/
server/alembic/        # migrations skeleton
server/tests/
```

## Gaps vs full `dev_plan.xml`

Landed as a coherent stub vertical slice covering phases **1–3, 6–8** (core) and skeleton for **4–5, 7**:

- **Phase 4:** Real Http*/Qdrant/Soffice adapters exist and are factory-selectable; live smoke is gated, not fully proven in CI.
- **Phase 5:** Ingest works for officer learning text via stub Docling; full `docs/*.docx` CLI/blue-green alias swap not polished.
- **Phase 7:** Stats + request_id logging present; cache (`CACHE_*`) and deeper redaction polish still thin.
- **Postgres durability demo** needs `PERSISTENCE_USE_STUB=false` + migrated DB (adapter + Alembic ready).
