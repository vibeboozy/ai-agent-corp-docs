# Corporate RAG AI-Agent — `server/`

Корпоративный RAG-агент (прототип). Архитектура, правила, план и код API живут здесь. Реализация — по фазам в `dev_plan.xml`.

**Real clients only:** the app always wires LLM, embeddings, Qdrant, Docling, LibreOffice, escalation, and Postgres adapters from env.

## What works (this vertical slice)

| Criterion | Behavior |
|-----------|----------|
| 1 Grounded answers | LangGraph retrieve→ground→answer with citations from Qdrant KB |
| 2 Clarifying dialogue | Underspecified/ambiguous → `clarification` + status `clarifying` |
| 3 Continuous learning | Escalate → `officer-reply` → ingest → later answers |
| REST | Appeals/messages/officer-reply/stats per `CLIENT_INFO.md` |
| Persistence | `SqlAlchemyPersistence` + Alembic (Postgres) |
| Logging | JSON logs + `X-Request-Id`; `audit_events` with LLM/retrieval latency, rerank scores, chunk_ids, clarify/escalate reasons |
| Connectivity | `rag-server check` + `GET /health/dependencies` |

## Workflow & run commands

All commands from the `server/` directory.

### 1. Install

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev,persistence,vector]"
```

### 2. Environment

```bash
cp .env.example .env
# Set real LLM_BASE_URL / EMBEDDINGS_* / QDRANT_* / DOCLING_* / DATABASE_URL
```

**Qdrant URL:** local REST is `http://127.0.0.1:6333`; Qdrant Cloud uses `https://…cloud.qdrant.io:443` (port **443**, not 6333).

**Docs corpus (local only):** set `DOCS_CORPUS_PATH` (default `docs`) or `DOCS_DIR`. The folder is **gitignored** — create it locally for ingest (`mkdir -p docs`); do not commit regulation files.

**Ingest / retrieval knobs:** `DOCLING_*` (OCR, HybridChunker window sizes, concurrency) and `RERANK_MODE=none|llm` (with `RERANK_CANDIDATES` / `RERANK_TOP_K`) — see `.env.example`.

### 3. Run API

```bash
set -a && source .env && set +a
alembic upgrade head
uvicorn app.main:app --reload --host "${APP_HOST}" --port "${APP_PORT}"
```

- Liveness: `GET /health` and `GET /api/v1/health`
- Dependencies: `GET /health/dependencies` (also under `/api/v1/…`) — per-service ok/fail
- OpenAPI: `/docs` (FastAPI UI; unrelated to corpus path)
- Contract: [`CLIENT_INFO.md`](CLIENT_INFO.md)
- Scripted demo: [`DEMO.md`](DEMO.md)

### 4. Connectivity check (CLI)

After `pip install -e ".[dev,…]"`, the `rag-server` console script is available:

```bash
rag-server check
# equivalent:
python3 -m app.cli check
```

Prints `overall` plus lines for `llm`, `embeddings`, `qdrant`, `docling`, `postgres`. Exit `0` when all OK.

Optional Docling file ingest:

```bash
rag-server ingest-docx /path/to/reg.docx --title "Procurement"
# or: python3 -m app.cli ingest-docx /path/to/reg.docx
```

### 5. Tests

```bash
pytest
```

Default CI runs unit/contract tests (mocked HTTP where needed). Integration/e2e
tests run when dependencies answer ping via normal `.env` / Settings config;
they **skip** when infra is unreachable — no `RUN_LIVE_*` env flags.

### 6. Optional live suites

```bash
pytest -m integration   # per-service smoke when reachable
pytest -m e2e            # full appeal path when core stack is up
rag-server check
```

### 7. Alembic (Postgres)

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
  adapters/            # llm, embeddings, vectorstore, docling, libreoffice, escalation, persistence
  config/
  logging/
server/alembic/        # migrations skeleton
server/tests/
```

## Gaps vs full `dev_plan.xml`

- **Phase 4:** Real Http*/Qdrant/Soffice adapters are the only path; live smoke is gated, not fully proven in CI.
- **Phase 5:** Full `docs/*.docx` CLI/blue-green alias swap not polished.
- **Phase 7:** Stats + request_id logging present; cache (`CACHE_*`) and deeper redaction polish still thin.
- **Postgres durability** needs a migrated `DATABASE_URL` (adapter + Alembic ready).
