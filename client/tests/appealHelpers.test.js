/**
 * Node built-in test runner: `node --test tests/appealHelpers.test.js`
 * (run from client/)
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  APPEALS_LIST_LIMIT,
  areChatMessagesRenderEqual,
  attachEscalationEmailDrafts,
  buildEscalationEmailDraft,
  canSendInAppeal,
  createLocalSessionId,
  firstUserQuestionFromMessages,
  isServerAppealId,
  mapAppealStatusToTicketStatus,
  mergeLocalEscalationState,
  resolveEmployeeQuestion,
  shouldShowEscalationPreviewForm,
  ticketStatusLabel
} from '../src/utils/appealHelpers.js';

describe('createLocalSessionId / isServerAppealId', () => {
  it('local session ids never look like server UUIDs', () => {
    for (let i = 0; i < 20; i++) {
      const id = createLocalSessionId();
      assert.match(id, /^sess-/);
      assert.equal(isServerAppealId(id), false);
    }
  });

  it('recognizes real server UUIDs', () => {
    assert.equal(isServerAppealId('a1b2c3d4-e5f6-7890-abcd-ef1234567890'), true);
    assert.equal(isServerAppealId('not-a-uuid'), false);
    assert.equal(isServerAppealId(''), false);
    assert.equal(isServerAppealId(null), false);
  });
});

describe('mapAppealStatusToTicketStatus', () => {
  it('maps answered away from awaiting-officer', () => {
    assert.equal(mapAppealStatusToTicketStatus('answered'), 'answered');
    assert.equal(ticketStatusLabel('answered'), 'Отвечено агентом');
  });

  it('maps escalated to open (awaiting officer)', () => {
    assert.equal(mapAppealStatusToTicketStatus('escalated'), 'open');
    assert.equal(ticketStatusLabel('open'), 'Ожидает ответа');
  });

  it('maps resolved/closed to resolved', () => {
    assert.equal(mapAppealStatusToTicketStatus('resolved_by_officer'), 'resolved');
    assert.equal(mapAppealStatusToTicketStatus('closed'), 'resolved');
  });

  it('maps clarifying/open to in_progress', () => {
    assert.equal(mapAppealStatusToTicketStatus('clarifying'), 'in_progress');
    assert.equal(mapAppealStatusToTicketStatus('open'), 'in_progress');
  });
});

describe('resolveEmployeeQuestion', () => {
  it('never falls back to AI summary', () => {
    // Callers must not pass summary as question — helper prefers user fields only.
    const q = resolveEmployeeQuestion({
      topic: null,
      question: null,
      firstUserMessage: null
    });
    assert.equal(q, 'Вопрос сотрудника');
  });

  it('prefers first user message over topic', () => {
    assert.equal(
      resolveEmployeeQuestion({
        firstUserMessage: 'Сколько времени в Москве?',
        topic: 'Сколько времени',
        question: null
      }),
      'Сколько времени в Москве?'
    );
  });

  it('uses API question field before topic (list without click)', () => {
    assert.equal(
      resolveEmployeeQuestion({
        question: 'Сколько времени в Москве?',
        topic: 'Сколько времени'
      }),
      'Сколько времени в Москве?'
    );
  });

  it('uses topic when messages missing', () => {
    assert.equal(
      resolveEmployeeQuestion({ topic: 'Кто подписывает договоры?' }),
      'Кто подписывает договоры?'
    );
  });
});

describe('firstUserQuestionFromMessages', () => {
  it('extracts first user role content', () => {
    const messages = [
      { role: 'assistant', content: 'refuse text' },
      { role: 'user', content: 'Сколько времени в Москве?' },
      { role: 'assistant', content: 'Этот вопрос не поддерживается.' }
    ];
    // First user in list order — here assistant is first, then user
    assert.equal(
      firstUserQuestionFromMessages(messages),
      'Сколько времени в Москве?'
    );
  });
});

describe('canSendInAppeal', () => {
  it('allows answered / clarifying / escalated; blocks closed', () => {
    assert.equal(canSendInAppeal('answered'), true);
    assert.equal(canSendInAppeal('clarifying'), true);
    assert.equal(canSendInAppeal('escalated'), true);
    assert.equal(canSendInAppeal(null), true);
    assert.equal(canSendInAppeal('closed'), false);
  });
});

describe('APPEALS_LIST_LIMIT', () => {
  it('requests more than the old felt limit of 50', () => {
    assert.ok(APPEALS_LIST_LIMIT > 50);
    assert.ok(APPEALS_LIST_LIMIT <= 200);
  });
});

describe('buildEscalationEmailDraft / attachEscalationEmailDrafts', () => {
  it('builds preview fields from the employee question', () => {
    const draft = buildEscalationEmailDraft('Какая пороговая маржа?');
    assert.equal(draft.to, 'quality@company.ru');
    assert.match(draft.subject, /Какая пороговая маржа/);
    assert.match(draft.body, /Какая пороговая маржа\?/);
  });

  it('recomputes email_draft on escalate history without a stored draft', () => {
    const messages = [
      { id: 1, role: 'user', content: 'Какая пороговая маржа?' },
      {
        id: 2,
        role: 'assistant',
        content: 'Нет в регламентах',
        status: 'escalate',
        message_kind: 'escalation_notice'
      }
    ];
    const out = attachEscalationEmailDrafts(messages);
    assert.equal(out[1].status, 'escalate');
    assert.ok(out[1].email_draft);
    assert.match(out[1].email_draft.body, /Какая пороговая маржа\?/);
    assert.equal(out[1].ticketCreated, false);
  });

  it('keeps an existing draft and ticketCreated flag', () => {
    const messages = [
      { id: 1, role: 'user', content: 'Q' },
      {
        id: 2,
        role: 'assistant',
        status: 'escalate',
        email_draft: { to: 'a@b.c', subject: 'S', body: 'B' },
        ticketCreated: true,
        ticketId: 'uuid-1'
      }
    ];
    const out = attachEscalationEmailDrafts(messages);
    assert.equal(out[1].email_draft.subject, 'S');
    assert.equal(out[1].ticketCreated, true);
    assert.equal(out[1].ticketId, 'uuid-1');
  });
});

describe('shouldShowEscalationPreviewForm', () => {
  const msg = {
    status: 'escalate',
    email_draft: { to: 'quality@company.ru', subject: 'S', body: 'B' },
    ticketCreated: false
  };

  it('shows form for escalated / unknown appeal status', () => {
    assert.equal(shouldShowEscalationPreviewForm(msg, 'escalated'), true);
    assert.equal(shouldShowEscalationPreviewForm(msg, null), true);
  });

  it('hides form after send or when appeal is no longer awaiting quality', () => {
    assert.equal(
      shouldShowEscalationPreviewForm({ ...msg, ticketCreated: true }, 'escalated'),
      false
    );
    assert.equal(shouldShowEscalationPreviewForm(msg, 'resolved_by_officer'), false);
    assert.equal(shouldShowEscalationPreviewForm(msg, 'closed'), false);
    assert.equal(shouldShowEscalationPreviewForm(msg, 'answered'), false);
  });
});

describe('mergeLocalEscalationState', () => {
  it('preserves local ticketCreated across server reload', () => {
    const server = [
      { id: 'u1', role: 'user', content: 'Вопрос без ответа в БЗ' },
      {
        id: 'a1',
        role: 'assistant',
        content: 'Эскалация',
        status: 'escalate',
        message_kind: 'escalation_notice'
      }
    ];
    const local = [
      { id: 'u1', role: 'user', content: 'Вопрос без ответа в БЗ' },
      {
        id: 'a1',
        role: 'assistant',
        status: 'escalate',
        email_draft: { to: 'quality@company.ru', subject: 'edited', body: 'edited body' },
        ticketCreated: true,
        ticketId: 'a1'
      }
    ];
    const merged = mergeLocalEscalationState(server, local);
    assert.equal(merged[1].ticketCreated, true);
    assert.equal(merged[1].ticketId, 'a1');
    assert.equal(merged[1].email_draft.subject, 'edited');
  });

  it('still attaches a fresh draft when local cache has none', () => {
    const server = [
      { id: 'u1', role: 'user', content: 'Маржа?' },
      { id: 'a1', role: 'assistant', status: 'escalate', message_kind: 'escalation_notice' }
    ];
    const merged = mergeLocalEscalationState(server, []);
    assert.ok(merged[1].email_draft);
    assert.equal(merged[1].ticketCreated, false);
  });
});

describe('areChatMessagesRenderEqual', () => {
  const base = [
    { id: 'u1', role: 'user', content: 'Q' },
    {
      id: 'a1',
      role: 'assistant',
      content: 'Escalate',
      status: 'escalate',
      email_draft: { to: 'quality@company.ru', subject: 'S', body: 'B' },
      ticketCreated: false,
      citations: [{ doc_name: 'Doc', section: '1', quote: 'q' }]
    }
  ];

  it('treats structurally identical lists as equal', () => {
    const copy = JSON.parse(JSON.stringify(base));
    assert.equal(areChatMessagesRenderEqual(base, copy), true);
  });

  it('detects id / draft / citation differences', () => {
    assert.equal(
      areChatMessagesRenderEqual(base, [
        base[0],
        { ...base[1], id: 'a2' }
      ]),
      false
    );
    assert.equal(
      areChatMessagesRenderEqual(base, [
        base[0],
        { ...base[1], email_draft: { ...base[1].email_draft, body: 'edited' } }
      ]),
      false
    );
    assert.equal(
      areChatMessagesRenderEqual(base, [
        base[0],
        { ...base[1], citations: [] }
      ]),
      false
    );
  });
});
