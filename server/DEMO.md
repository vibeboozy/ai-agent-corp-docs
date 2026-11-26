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

## 1. Grounded answer

```bash
curl -s http://127.0.0.1:8000/api/v1/appeals -H 'Content-Type: application/json' \
  -d '{"message":{"content":"Кто подписывает договоры на закупку?"}}' | python3 -m json.tool
```

Expect: `status=answered`, assistant `message_kind=answer` with non-empty `citations`
(corpus must already contain matching regulation chunks).

## 2. Clarify then answer

```bash
# ambiguous first turn
curl -s http://127.0.0.1:8000/api/v1/appeals -H 'Content-Type: application/json' \
  -d '{"message":{"content":"Кто подписывает договоры?"}}' | python3 -m json.tool

# then POST /appeals/{id}/messages — body is {"content":"..."} (not nested)
curl -s http://127.0.0.1:8000/api/v1/appeals/APPEAL_ID/messages \
  -H 'Content-Type: application/json' \
  -d '{"content":"Это про договоры на закупку товаров."}' | python3 -m json.tool
```

Expect: first turn `clarifying`; after clarification `answered` + citations.

## 3. Escalate + officer learning

```bash
# unknown topic → escalated (POST /appeals with first message)
# POST /appeals/{id}/officer-reply with {"content":"<canonical brandbook text>"}
# create a new appeal asking the logo color again → answered from learned KB
```

Automated (skips without infra): `RUN_LIVE_E2E=1 pytest -m e2e`

## Live flags

Per-adapter smoke: `RUN_LIVE_LLM=1`, `RUN_LIVE_EMBEDDINGS=1`, `RUN_LIVE_QDRANT=1`,
`RUN_LIVE_DOCLING=1`, `RUN_LIVE_POSTGRES=1`. Full path: `RUN_LIVE_E2E=1`.
See `.env.example` and `rules/testing_rules.xml`. Live suites **skip** when flags are unset.
