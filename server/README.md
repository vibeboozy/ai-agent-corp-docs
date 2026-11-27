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

**Large PDFs:** local files above `DOCLING_PDF_SPLIT_PAGES` (default **40**) are converted in page-range chunks via Docling `options.page_range`, then merged with absolute page markers (avoids Docling Serve timeouts on ~hundreds of pages). Optional part cache: `DOCLING_PDF_PART_CACHE_DIR=.cache/docling/parts`. This is separate from `DOCLING_SPLIT_PAGES` (boolean markdown page-break placeholders).

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

Optional Docling file ingest (docx/pdf/…; aliases: `ingest`, `ingest-docx`):

```bash
rag-server ingest-file /path/to/reg.docx --title "Procurement"
# or: python3 -m app.cli ingest-file /path/to/reg.pdf
```

### 5. Abbreviation glossary

Built-in corporate abbreviations (РП, АМ, ТЗ, …) expand queries before hybrid
search and, on ingest, append expansions into chunk **text** (e.g.
`РП (Руководитель проекта)`) before dense/sparse embed, plus optional
`metadata.abbreviations`. Configure via `ABBREVIATION_*` in `.env.example`
(`ABBREVIATION_GLOSSARY`, `ABBREVIATION_GLOSSARY_PATH`,
`ABBREVIATION_EXPAND_QUERY`, `ABBREVIATION_ENRICH_INGEST`).

### 5b. Allowed topics (domain gate)

Corporate regulations are always in-domain. To also answer from other ingested
corpora (e.g. Конституция РФ, Трудовой кодекс РФ), set `ALLOWED_TOPICS` in
`.env` (labels / optional descriptions; see `.env.example`). That list feeds the
off-topic heuristic, LLM classify prompt, refusal text, and answer prompts.
Weather/time/jokes stay refused. Ingest the matching files into Qdrant first.

### 6. Tests

```bash
pytest
```

Default CI runs unit/contract tests (mocked HTTP where needed). Integration/e2e
tests run when dependencies answer ping via normal `.env` / Settings config;
they **skip** when infra is unreachable.

### 7. Optional live suites

```bash
pytest -m integration   # per-service smoke when reachable
pytest -m e2e            # full appeal path when core stack is up
rag-server check
```

### 7b. Local golden scenario runner (paste log)

Live read-only dialogue against your `.env` stack (LLM + embeddings + existing
Qdrant collection). Does **not** upsert Qdrant or create Postgres appeals.

```bash
cd server
# .env configured; corpus already ingested
python scripts/run_golden_scenarios.py
# optional: --only GS-01,GS-02  --out artifacts/golden-run.log
```

Scenarios: `scenarios/golden-set.yaml` (GS-01…16).  
**Paste back:** `artifacts/golden-run.log` (expected vs actual, citations, gates).

### 8. Alembic (Postgres)

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
