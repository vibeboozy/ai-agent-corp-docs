# Corporate RAG AI-Agent — `server/`

Корпоративный RAG-агент (прототип). Здесь же: архитектура, правила, план и будущий код API. Реализация — по фазам в `dev_plan.xml`. Пока без рантайма приложения (есть `.env.example` и документация).

## Artifacts (LLM / agents)

| Path | Purpose |
|------|---------|
| [project_context.md](project_context.md) | Goals, stack (LangGraph, PostgreSQL), architecture, REST, RAG, tests |
| [CLIENT_INFO.md](CLIENT_INFO.md) | REST contract for future client AI agent |
| [semantic_graph.xml](semantic_graph.xml) | Modules and relationships |
| [dev_plan.xml](dev_plan.xml) | Phased implementation plan |
| [rules/coding_standards.xml](rules/coding_standards.xml) | Python / layout / stubs / LangGraph / Postgres |
| [rules/security_rules.xml](rules/security_rules.xml) | Secrets, PII, SSRF, DB |
| [rules/testing_rules.xml](rules/testing_rules.xml) | Stub CI + live integration/e2e |
| [rules/anchor_standards.xml](rules/anchor_standards.xml) | Grounding, clarify, escalate, learn |
| [.env.example](.env.example) | All env keys (stubs by default; Postgres `DATABASE_URL`) |

## Success criteria

1. Answers **only** from regulation content; otherwise escalate — no invention.
2. Clarifying dialogue when underspecified or ambiguous.
3. Continuous learning: officer canonical answer → KB update; log all appeals.

## Orchestration & persistence

- **LangGraph: yes** for dialogue graph. **Full LangChain RAG: no** — see `project_context.md` §2.1.
- **PostgreSQL** (SQLAlchemy async + asyncpg) stores appeals/messages/history/stats; `StubPersistence` for unit tests. Must survive restarts when stubs are off.

## Tests (preview)

```bash
# Default CI / local — stubs only (no live providers)
cd server && USE_STUBS=true pytest

# Live integration / e2e when real services are configured (see testing_rules.xml)
cd server && USE_STUBS=false RUN_LIVE_TESTS=1 pytest -m integration
# or finer gates: RUN_LIVE_LLM=1 RUN_LIVE_EMBEDDINGS=1 RUN_LIVE_QDRANT=1 RUN_LIVE_DOCLING=1
```
