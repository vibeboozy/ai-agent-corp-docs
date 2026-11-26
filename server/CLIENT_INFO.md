# Client API contract — Corporate RAG AI-Agent

> For a future **client-side AI agent** (or human frontend). Build against this contract without reading server source.  
> Base URL example: `http://localhost:8000` + prefix `/api/v1`.  
> Content-Type: `application/json; charset=utf-8`. Timestamps: ISO-8601 UTC (`...Z`).

Chat model: an **appeal** is a ticket; the conversation is its **ordered message list**. The client creates/opens an appeal, posts user messages, then **re-fetches or polls** the message list (and optionally the appeal) until a new assistant/officer/system message appears. No WebSocket required for the prototype.

---

## 1. Auth (prototype)

| `AUTH_MODE` | Client behavior |
|-------------|-----------------|
| `none` (default) | No auth headers. |
| `header` | Send `X-User-Id: <opaque-string>` on user actions. Officer actions also need `X-Officer-Token: <token>` matching server `AUTH_OFFICER_TOKEN`. |

Unauthorized → `401` with `code: UNAUTHORIZED`. Forbidden officer action → `403` with `code: FORBIDDEN`.

Optional correlation: echo `X-Request-Id` if provided; otherwise server may set one (also in logs).

---

## 2. Shared types

### AppealStatus

`open` | `clarifying` | `answered` | `escalated` | `resolved_by_officer` | `closed`

### MessageRole

`user` | `assistant` | `officer` | `system`

### MessageKind

`question` | `clarification` | `answer` | `refusal` | `escalation_notice` | `canonical_answer`

### Citation

```json
{
  "document_id": "uuid-or-str",
  "chunk_id": "uuid-or-str",
  "quote": "fragment from regulation",
  "score": 0.82,
  "document_title": "optional",
  "locator": "optional page/section"
}
```

### Appeal

```json
{
  "id": "uuid",
  "status": "open",
  "created_at": "2026-11-26T10:00:00Z",
  "updated_at": "2026-11-26T10:05:00Z",
  "user_id": "opaque-or-null",
  "user_label": "optional display",
  "topic": "optional",
  "summary": "optional",
  "escalation_id": "uuid-or-null",
  "message_count": 3
}
```

### Message

```json
{
  "id": "uuid",
  "appeal_id": "uuid",
  "role": "assistant",
  "message_kind": "answer",
  "content": "текст ответа…",
  "created_at": "2026-11-26T10:01:00Z",
  "citations": []
}
```

- `citations` required (possibly empty array). Non-empty when `message_kind` is `answer`.
- User-facing `content` may be Russian.

### Error body

```json
{
  "detail": "Human-readable explanation",
  "code": "SNAKE_CASE_CODE"
}
```

Common codes: `VALIDATION_ERROR`, `NOT_FOUND`, `CONFLICT_STATUS`, `UNAUTHORIZED`, `FORBIDDEN`, `UPSTREAM_TIMEOUT`, `INTERNAL_ERROR`.

---

## 3. Endpoints

### `GET /api/v1/health` (optional but expected)

**200**

```json
{ "status": "ok" }
```

---

### `GET /api/v1/appeals`

List appeals (newest first unless specified).

**Query**

| Param | Type | Notes |
|-------|------|-------|
| `status` | AppealStatus | optional filter |
| `user_id` | string | optional |
| `limit` | int | default 50, max 200 |
| `offset` | int | default 0 |
| `created_from` / `created_to` | ISO datetime | optional |

**200**

```json
{
  "items": [ /* Appeal */ ],
  "total": 42,
  "limit": 50,
  "offset": 0
}
```

---

### `POST /api/v1/appeals`

Create appeal; optionally send first user message (triggers agent turn).

**Request**

```json
{
  "user_id": "optional-opaque",
  "user_label": "optional",
  "topic": "optional",
  "message": {
    "content": "Кто подписывает договоры на закупку?"
  }
}
```

`message` optional. If present, server appends user message and runs dialogue graph before responding.

**201**

```json
{
  "appeal": { /* Appeal */ },
  "messages": [ /* Message[] chronologically if message was sent */ ]
}
```

---

### `GET /api/v1/appeals/{appeal_id}`

**200** — `Appeal`  
**404** — `NOT_FOUND`

---

### `GET /api/v1/appeals/{appeal_id}/messages`

List messages (chat history). **Primary client read path for polling.**

**Query**

| Param | Type | Notes |
|-------|------|-------|
| `after_id` | uuid | optional: only messages strictly after this id (or after its `created_at`+id order) |
| `limit` | int | default 100 |

**200**

```json
{
  "appeal_id": "uuid",
  "items": [ /* Message[] ascending by created_at */ ]
}
```

---

### `POST /api/v1/appeals/{appeal_id}/messages`

Send a user (or allowed system) message; server runs one agent turn and returns new messages from that turn (at least the user message + assistant/system outcome).

**Request** — flat body (not nested under `message` like `POST /appeals`):

```json
{
  "content": "Это про договоры с подрядчиками, не закупку.",
  "role": "user"
}
```

`role` defaults to `user`. Clients must not send `officer` here — use officer-reply.

**201**

```json
{
  "appeal": { /* Appeal updated status */ },
  "messages": [ /* new Message[] for this turn, chronological */ ]
}
```

**Typical outcomes in `messages`**

| Situation | Assistant `message_kind` | Appeal `status` |
|-----------|--------------------------|-----------------|
| Need more info | `clarification` | `clarifying` |
| Grounded answer | `answer` (+ citations) | `answered` |
| Out of KB / unsupported | `escalation_notice` (and/or `refusal`) | `escalated` |

**404** unknown appeal · **409** `CONFLICT_STATUS` if appeal `closed` · **422** validation

---

### `POST /api/v1/appeals/{appeal_id}/officer-reply`

Quality officer canonical answer + learning (KB update). Not a normal chat message.

**Headers:** if `AUTH_MODE=header`, require officer token.

**Request**

```json
{
  "content": "Канонический ответ по регламенту…",
  "source_document_hint": "optional filename or doc id"
}
```

**201**

```json
{
  "appeal": { /* often resolved_by_officer or closed */ },
  "message": { /* Message role=officer, message_kind=canonical_answer */ },
  "learning": {
    "accepted": true,
    "ingest_job_id": "uuid-or-null",
    "escalation_id": "uuid-or-null"
  }
}
```

**403** if not officer · **404** · **409** if no pending escalation / illegal state (server may still accept learning — document exact policy in OpenAPI when implemented)

---

### `GET /api/v1/stats`

**Query (optional):** `from`, `to` ISO datetimes.

**200**

```json
{
  "appeals_total": 120,
  "by_status": {
    "open": 5,
    "clarifying": 8,
    "answered": 70,
    "escalated": 20,
    "resolved_by_officer": 12,
    "closed": 5
  },
  "messages_total": 900,
  "clarify_rate": 0.25,
  "escalation_rate": 0.18,
  "answered_rate": 0.58,
  "learning_updates": 12,
  "window": { "from": null, "to": null }
}
```

Rates are fractions 0..1 over the window (or all-time if unset).

---

## 4. Client UX / polling model

1. `POST /appeals` (± first message) → show returned `messages`.
2. User types → `POST /appeals/{id}/messages` → append returned `messages` to UI.
3. If the server later moves to async turns: poll `GET .../messages?after_id=<last>` every 1–2s until a new non-user message appears or timeout; also refresh `GET /appeals/{id}` for `status`.
4. When `status=escalated`, show quality-service copy (from assistant content) and optionally an officer UI that calls `officer-reply`.
5. After officer-reply, refresh messages + appeal; user may ask a follow-up via `POST .../messages`.

Do **not** invent answers client-side. Display citations when present; link/document_title if available.

---

## 5. Persistence note for clients

Appeals, messages, escalations, audit, and stats aggregates are stored in **PostgreSQL** (see server `project_context.md`). After a server restart, `GET` list/history/stats must return the same data. Clients can rely on durable IDs.

The server always uses live LLM/embeddings/Qdrant/Docling/Postgres (no stub mode). `GET /health/dependencies` reports per-service `mode=live`.

---

## 6. Out of scope for prototype client

- WebSocket / SSE (optional later)
- Multipart file upload to RAG corpus (ingest is server/admin)
- Editing/deleting messages
- Full SSO

When OpenAPI is generated from FastAPI, prefer the live schema if it diverges slightly — this doc is the design contract for implementation.
