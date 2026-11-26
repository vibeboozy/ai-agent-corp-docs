# Project Context — Corporate RAG AI-Agent Server

> Prototype deliverable under `server/`. Follow `dev_plan.xml` phases. External AI/infra services use real adapters (LLM, embeddings, Qdrant, Docling, Postgres) wired from Settings.
>
> **Working directory:** everything for this product lives under `server/` (this file, `rules/`, `.env.example`, `app/`). Repo root only points here.

## 1. Goals / Non-goals / Acceptance

### 1.1 Business goal

Корпоративный RAG-агент для Q&A по внутренним процессам (регламенты, приказы, база знаний). Сотрудники тратят 30 мин–2 ч на поиск: кто подписывает договоры, какой регламент применяется, кто владелец шага. Информация разрознена; 100–300 запросов/мес; до 40% без ответа или с устаревшими данными.

### 1.2 Prototype success criteria (MUST)

| # | Criterion | Architectural implication |
|---|-----------|---------------------------|
| 1 | **Grounded answers only** — ответ строго из текста регламентов. Если нет в KB: не выдумывать; создать тикет quality service и/или направить к quality / email. Ненадёжно = не совпадает с регламентом или дополнено внешним знанием. | `grounding` + `quality_escalation`; refuse/escalate without unsupported generation |
| 2 | **Clarifying dialogue** — при недоопределённом вопросе или неоднозначном маппинге на регламент: уточняющие вопросы до однозначного ответа или явной невозможности ответить. | LangGraph dialogue graph; no forced final answer |
| 3 | **Continuous learning** — нет в KB → quality officer даёт канонический ответ → агент обновляет KB (ingest/index). Все обращения логируются. | `learning` + `ingest` + appeal audit trail |

### 1.3 Non-goals (prototype)

- Production multi-tenant auth/SSO (placeholder only).
- Client UI (separate later; parallel to `server/` at repo root when added).
- Fake/offline provider adapters (always use real services).
- Perfect legal compliance certification.
- Full LangChain RetrievalQA / LCEL-as-primary-RAG (see §2.1).

### 1.4 Product principles

1. **No hallucination** — unsupported claim → clarify or escalate.
2. **Real adapters only** — LLM/embeddings/Qdrant/Docling/Postgres via ports + DI factories.
3. **Appeal-centric chat** — conversation = message list on an appeal/ticket.
4. **Russian regulations domain** — corpus and UX language: Russian; technical identifiers: English.

---

## 2. Tech stack (recommendation)

| Layer | Choice | Notes |
|-------|--------|-------|
| Language | Python 3.12+ (prefer latest stable 3.13 if env allows) | Modern typing |
| API | FastAPI (ASGI) + Uvicorn | OpenAPI for LLM/agents |
| Agent orchestration | **LangGraph** (latest stable) | Dialogue graph: clarify / retrieve / ground / answer / escalate |
| LLM messages (optional) | `langchain-core` only | Shared message types if useful; not required for adapters |
| Validation | Pydantic v2 | Settings via `pydantic-settings` |
| HTTP client | httpx (async) | LLM, embeddings, Docling, email webhooks |
| Vector DB | qdrant-client | Dense + sparse (bge-m3); collection alias + blue/green `*_v1`/`*_v2` |
| Doc convert | Docling (HTTP) + LibreOffice/`soffice` for docx when needed | Live HTTP / soffice |
| Persistence | **PostgreSQL** via SQLAlchemy 2.x async + asyncpg | Appeals, messages, escalations, audit, stats; must survive restarts. Optional SQLite only as emergency local fallback |
| Logging | structlog or stdlib `logging` + JSON formatter | Correlation IDs |
| Tests | pytest + pytest-asyncio + httpx ASGITransport | Unit/mocked HTTP in CI; live when services reachable via Settings |
| Packaging | `pyproject.toml`, ruff, mypy (strict-ish) | See `rules/coding_standards.xml` |

### 2.1 LangGraph / LangChain decision

| Technology | Decision | Rationale |
|------------|----------|-----------|
| **LangGraph** | **YES — adopt** | Success criteria map cleanly to a typed state graph: underspecified → clarify loop; retrieve → ground → answer **or** escalate; officer path feeds learning. Conditional edges keep “no invention” enforceable in code, not prompt hope. Checkpointing can align with appeal/message persistence later. Modern versions; DI injects the same node callables. |
| **LangChain (full / RAG chains)** | **NO as primary stack** | Hybrid dense+sparse bge-m3, Qdrant alias blue/green, Docling HTTP, and strict citation grounding are first-class **our** ports. LangChain `RetrievalQA` / vectorstore wrappers add coupling and version churn without improving groundedness guarantees. |
| **langchain-core** | **Optional, thin** | Allowed for message schemas / runnable interfaces if it reduces boilerplate. Application services and adapters must not depend on LangChain vectorstores, document loaders, or remote tool ecosystems. |

**Implication:** implement `application/dialogue` as a LangGraph `StateGraph` whose nodes call our ports (`LLMClient`, `EmbeddingsClient`, `VectorStore`, etc.). Graph topology is the source of truth for agent behavior; prompts alone are not.

**Repo layout (target):**

```text
/
  README.md                 # pointer → server/
  server/
    README.md
    project_context.md
    semantic_graph.xml
    dev_plan.xml
    rules/
    .env.example
    pyproject.toml
    rules/anchor_standards.xml  # behavioral + module-docstring anchors (ANC-MARK-*)
    app/
      main.py               # FastAPI entry
      api/
      application/
        appeals/
        dialogue/           # LangGraph StateGraph lives here (graph.py, nodes, state)
        grounding/
        retrieval/
        ingest/
        learning/
        quality_escalation/
      domain/
      adapters/
        llm/
        embeddings/
        vectorstore/        # Qdrant
        docling/
        libreoffice/
        escalation/
        persistence/        # Postgres SQLAlchemy
      config/
      logging/
    docs/                   # LOCAL ONLY — RAG corpus (docx); path via DOCS_CORPUS_PATH / DOCS_DIR; gitignored
    tests/
      api/
      application/
      adapters/
      domain/
      integration/          # live-gated
    CLIENT_INFO.md          # REST contract for future client agent
```

Client will live parallel to `server/` at repo root later — do not put API code outside `server/`. Client builders: start from `CLIENT_INFO.md`.

---

## 3. Layered architecture

```text
API (FastAPI routers)
  → application / services
       dialogue LangGraph (clarify | retrieve | ground | answer | escalate)
       + learning, ingest, stats
    → domain (Appeal, Message, ChunkCitation, policies)
      → adapters (ports: LLM, Embeddings, VectorStore, Docling, Email, Persistence)
```

### 3.1 Real provider pattern

- Each port has a Protocol/ABC and one production implementation: `HttpX` / `QdrantX` / `SqlAlchemyPersistence` / `SofficeLibreOffice` / `EmailEscalationNotifier`.
- Factory in `config` / DI always constructs real adapters from Settings (URLs, keys, timeouts).
- LangGraph nodes receive ports via DI — topology is independent of concrete clients.
- Unit tests mock ports or HTTP at the adapter boundary; product flows need live services (configured in `.env`).

### 3.2 Module map (see also `semantic_graph.xml`)

| Module | Responsibility |
|--------|----------------|
| `api` | REST resources, DTO mapping, status codes |
| `appeals` | Lifecycle of appeal/ticket |
| `dialogue` | LangGraph: clarify vs answer vs escalate |
| `grounding` | Citation check; refuse unsupported claims |
| `retrieval` | Hybrid dense+sparse, RRF, optional LLM rerank |
| `ingest` | docx → Docling → chunks → embed → Qdrant |
| `learning` | Officer canonical answer → KB update |
| `quality_escalation` | Ticket + email to quality service |
| `persistence` | PostgreSQL: appeals, messages, escalations, audit, stats inputs |
| `adapters` | External I/O (live clients) |
| `config` / `logging` | Settings, structured logs |

### 3.3 PostgreSQL persistence (required for durable history)

**Goal:** appeals, message history, escalations, learning/audit events, and stats inputs **survive process restarts**. Qdrant holds vectors; Postgres is the system of record for conversational state.

| Item | Choice |
|------|--------|
| Engine | PostgreSQL 16+ (prototype: any 14+ ok) |
| Access | SQLAlchemy 2.x async + **asyncpg** (`postgresql+asyncpg://...`) |
| Migrations | Alembic |
| Port | `AppealRepository` / `Persistence` Protocol |
| Real adapter | `SqlAlchemyPersistence` (or split repos under `adapters/persistence/`) |
| CI unit tests | Mocked ports; Postgres integration when DATABASE_URL answers ping |
| Fallback | `sqlite+aiosqlite` only if explicitly allowed for laptop smoke; production/prototype target remains Postgres |

**Env:** `DATABASE_URL`, pool knobs (`DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`, `DATABASE_POOL_TIMEOUT_S`), optional `DATABASE_ECHO`. See `.env.example`.

**Tables (logical):** `appeals`, `messages` (FK appeal, ordered history), `escalations`, `audit_events`, `documents` / `chunk_refs` metadata, `canonical_answers` / learning jobs. Stats endpoints aggregate from these tables — not from volatile memory.

---

## 4. Data model sketch

### Appeal

- `id`, `status` (`open` | `clarifying` | `answered` | `escalated` | `resolved_by_officer` | `closed`)
- `created_at`, `updated_at`
- `user_id` / `user_label` (opaque; minimize PII)
- `topic` / `summary` (optional, derived)
- `escalation_id` (nullable)
- Optional: LangGraph thread/checkpoint id keyed by `appeal_id`

### Message

- `id`, `appeal_id`, `role` (`user` | `assistant` | `officer` | `system`)
- `content`, `created_at`
- `citations[]` — `{ document_id, chunk_id, quote, score }` (assistant only when grounded)
- `message_kind` — `question` | `clarification` | `answer` | `refusal` | `escalation_notice` | `canonical_answer`

### Escalation

- `id`, `appeal_id`, `reason`, `status` (`pending` | `answered` | `closed`)
- `quality_notified_at`, `officer_reply_at`
- `channel` — email / internal queue

### Document / Chunk metadata

- Document: `id`, `source_path`, `title`, `version`, `effective_date`, `ingested_at`, `checksum`
- Chunk: `id`, `document_id`, `text`, `token_count`, `page`/`section`, `embedding refs`

### Feedback / CanonicalAnswer (learning)

- Links `escalation_id` / `appeal_id` → officer text → ingest job → new/updated chunks
- Audit: who, when, which docs touched

---

## 5. REST resource design

Base prefix: `/api/v1`. Chat = updating message list on an appeal.  
**Full request/response shapes for client agents:** [`CLIENT_INFO.md`](CLIENT_INFO.md).

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/appeals` | List appeals (filters: status, date) |
| `GET` | `/appeals/{appeal_id}` | Get appeal + summary |
| `POST` | `/appeals` | New appeal (optional first message) |
| `POST` | `/appeals/{appeal_id}/messages` | Send user (or system) message → agent turn (invokes LangGraph) |
| `GET` | `/appeals/{appeal_id}/messages` | List messages (pollable history) |
| `POST` | `/appeals/{appeal_id}/officer-reply` | Canonical answer + trigger retrain/KB update |
| `GET` | `/stats` | Aggregate: volume, answered, escalated, clarify rate, etc. |

**Design notes (deviations from minimal TZ naming — intentional):**

- Nested `/appeals/{id}/messages` instead of flat “list messages” — clearer resource ownership for LLM agents and OpenAPI.
- `officer-reply` as dedicated action (not a generic message) — triggers learning side-effects explicitly.
- Versioned `/api/v1` for prototype forward-compat.

All mutating endpoints append to appeal audit/log trail in PostgreSQL.

---

## 6. RAG pipeline overview

### 6.1 Ingest

Corpus path is **local-only** (not in git): `DOCS_CORPUS_PATH` (default `docs`) or override `DOCS_DIR`. Create the folder on the machine that runs ingest.

```text
$DOCS_CORPUS_PATH/*.docx   # local corpus; gitignored
  → LibreOffice (if needed) / Docling convert
  → HybridChunker (tokenizer BAAI/bge-m3; max/overlap/min tokens from env)
  → dense + sparse embeddings (bge-m3)
  → Qdrant upsert (batch); blue/green collections; alias QDRANT_COLLECTION
```

### 6.2 Query (LangGraph)

```text
user message on appeal
  → dialogue graph:
       assess_specificity (prefer_specific_label; log raw classify)
         → retrieve (hybrid dense+sparse RRF; prefer latest)  # always before clarify
         → optional rerank
         → ground (specific / role+topic) → answer + citations
              → escalate (quality ticket + user notice; no invention)
         → clarify (LLM-generated; loop, max DIALOGUE_MAX_CLARIFY_TURNS)
```

### 6.3 Learn

```text
officer-reply (canonical)
  → persist Message(role=officer)
  → close/resolve escalation
  → ingest canonical text / linked regulation update into KB
  → log learning event
```

---

## 7. Observability

- **Request logging:** method, path, status, latency, `request_id`, `appeal_id` when present (stdout; see `LOG_*`).
- **Appeal audit trail** (`audit_events` JSONB payload): durable in Postgres.
  - `dialogue_turn`: `outcome`, `node_trace`, `specificity`, `clarify_reason` / `escalation_reason`, `chunk_ids` + citation scores, `rerank.mode` + `rerank.scores`, `latency_ms` (`llm_assess_ms`, `llm_complete_ms`, `retrieval_total_ms` / `embed_ms` / `search_ms` / `rerank_ms`, `turn_total_ms`), `hit_count`.
  - Also: status transitions, `escalation_created` (with `reason`), officer/learning/ingest events.
- **LOG_*** env for level, JSON format, redaction flags.
- **CACHE_*** for optional response/embedding cache (disable across learning updates as needed).

Never log full secrets or unnecessary PII (see `rules/security_rules.xml`).

---

## 8. Infra & configuration

Documented in `.env.example` (this directory). Groups:

- **PostgreSQL** — `DATABASE_URL` (`postgresql+asyncpg://...`), pool settings
- **LLM** — OpenAI-compatible chat completions (`LLM_BASE_URL` without `/chat/completions`)
- **Embeddings** — dense + sparse bge-m3
- **Qdrant** — URL, key, collection alias, timeouts, upsert batch (local `:6333` vs Cloud `:443`)
- **Docling** — base URL, OCR langs, split pages, HybridChunker max/overlap/min tokens, concurrency/timeouts
- **Rerank / Retrieval** — `RERANK_MODE=none|llm`, candidates, top_k, max_per_doc, min_score; prefetch, prefer latest
- **Quality** — `QUALITY_SERVICE_EMAIL`, escalation toggles
- **Cache / Log** — operational knobs
- **Abbreviation glossary** — built-in corporate abbr list; `ABBREVIATION_*` for query expand + ingest metadata
- **Tests** — integration/e2e skip unless services answer ping

**CRITICAL:** Runtime always uses real providers. Configure URLs/keys in `.env`. Unit tests may mock HTTP; product demos need live infra (`rag-server check`).

---

## 9. Testing strategy (summary)

Details: `rules/testing_rules.xml`.

| Mode | Gate | What runs |
|------|------|-----------|
| Default CI / local | (none) | Unit/contract (mocked HTTP) |
| Per-adapter smoke | service ping via Settings | Connectivity + one round-trip |
| Integration | `-m integration` + reachable deps | Broader adapter + retrieval checks |
| E2E scenarios | `-m e2e` + core stack up | Full appeal flows: grounded answer, clarify, escalate, learn |

Live suites must **skip** when infra is unreachable — never fail CI for missing services. Assert structure, citations, statuses, and policy outcomes — not exact live LLM wording.

---

## 10. Constraints for agents implementing later

1. Follow `rules/anchor_standards.xml` for every assistant answer.
2. Follow `rules/coding_standards.xml` for layout, adapter naming, and LangGraph placement.
3. Follow `rules/testing_rules.xml` — CI unit tests must not call live providers; integration/e2e skip when unreachable.
4. Follow `rules/security_rules.xml` for secrets and SSRF.
5. Prefer extending adapters over scattering HTTP calls in services or LangGraph nodes.
6. Russian business copy in user-facing messages is OK; code identifiers stay English.
7. Keep working under `server/` — do not reintroduce project artifacts at repo root.

---

## 11. Related artifacts (all under `server/`)

| File | Role |
|------|------|
| `semantic_graph.xml` | Modules and edges for navigation |
| `dev_plan.xml` | Phased implementation plan |
| `rules/coding_standards.xml` | Code style and layout |
| `rules/security_rules.xml` | Secrets, PII, SSRF |
| `rules/testing_rules.xml` | Unit + live test policy |
| `rules/anchor_standards.xml` | Grounding / clarify / escalate |
| `.env.example` | All configuration keys (incl. `DOCS_CORPUS_PATH` / `DOCS_DIR`) |
| `CLIENT_INFO.md` | REST contract for future client AI agent |
| `README.md` | Index, connectivity `check`, and test command cheat sheet |
