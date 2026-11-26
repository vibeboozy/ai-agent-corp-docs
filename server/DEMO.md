# Demo scenarios (live services)

All scenarios need real LLM, embeddings, Qdrant, Docling (for learning ingest), and Postgres.
Copy `.env.example` → `.env`, fill provider URLs/keys, migrate Postgres, then from `server/`:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,persistence,vector]"
cp .env.example .env
# edit .env with real LLM_BASE_URL, EMBEDDINGS_*, QDRANT_*, DOCLING_*, DATABASE_URL
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Connectivity: `rag-server check` (or `python -m app.cli check`) — expect `overall: ok`.

**Body shapes:** `POST /appeals` nests the first message as `{"message":{"content":"..."}}`.
`POST /appeals/{id}/messages` takes a **flat** body `{"content":"..."}` (not nested under `message`).

**Qdrant:** collection uses named vectors `dense` + `sparse` (hybrid RRF). On first
upsert/search the server recreates a collection that still has unnamed Default 1024.
Re-ingest corpus after schema recreate: `rag-server ingest-docx …`.

## 1. Grounded answer

```bash
curl -s http://127.0.0.1:8000/api/v1/appeals -H 'Content-Type: application/json' \
  -d '{"message":{"content":"Кто отвечает за организацию отчётности по проекту?"}}' | python3 -m json.tool
```

Expect: `status=answered`, assistant `message_kind=answer` with non-empty `citations`
(corpus must already contain matching regulation chunks).

## 2. Clarify then answer

```bash
# underspecified first turn
curl -s http://127.0.0.1:8000/api/v1/appeals -H 'Content-Type: application/json' \
  -d '{"message":{"content":"Кто отвечает за организацию?"}}' | python3 -m json.tool

# then POST /appeals/{id}/messages — body is {"content":"..."} (not nested)
curl -s http://127.0.0.1:8000/api/v1/appeals/APPEAL_ID/messages \
  -H 'Content-Type: application/json' \
  -d '{"content":"Это про отчётность по проекту."}' | python3 -m json.tool
```

Expect: first turn `clarifying` (LLM-generated clarification text); after clarification
`answered` + citations.

## 3. Escalate + officer learning

```bash
# unknown topic → escalated (POST /appeals with first message)
# POST /appeals/{id}/officer-reply with {"content":"<canonical brandbook text>"}
# create a new appeal asking the logo color again → answered from learned KB
```

Automated when infra is up: `pytest -m e2e` (skips if services unreachable).
Offline DEMO dialogue paths: `pytest tests/application/test_demo_scenarios.py`.

## Live checks

Configure `.env`, then `rag-server check` / `pytest -m integration`.
See `rules/testing_rules.xml`. Live suites **skip** when services do not answer ping.
