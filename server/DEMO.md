# Demo scenarios (stubs)

All scenarios run offline with `USE_STUBS=true` (default). From `server/`:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,persistence]"
cp .env.example .env
USE_STUBS=true uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 1. Grounded answer

```bash
curl -s http://127.0.0.1:8000/api/v1/appeals -H 'Content-Type: application/json' \
  -d '{"message":{"content":"Кто подписывает договоры на закупку?"}}' | python3 -m json.tool
```

Expect: `status=answered`, assistant `message_kind=answer` with non-empty `citations`.

## 2. Clarify then answer

```bash
# ambiguous
curl -s http://127.0.0.1:8000/api/v1/appeals -H 'Content-Type: application/json' \
  -d '{"message":{"content":"Кто подписывает договоры?"}}' | python3 -m json.tool
# then POST /appeals/{id}/messages with: "Это про договоры на закупку товаров."
```

Expect: first turn `clarifying`; after clarification `answered` + citations.

## 3. Escalate + officer learning

```bash
# unknown topic → escalated
# POST officer-reply with canonical brandbook text
# create a new appeal asking the logo color again → answered from learned KB
```

Automated: `USE_STUBS=true pytest tests/api/test_appeals_stub_flows.py tests/application/test_dialogue_flows.py`

## Live path (optional)

Flip stubs off and set `RUN_LIVE_E2E=1` plus provider secrets — see `.env.example` and `rules/testing_rules.xml`. Live suites skip cleanly when flags are unset.
