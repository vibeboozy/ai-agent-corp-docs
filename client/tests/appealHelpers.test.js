/**
 * Node built-in test runner: `node --test tests/appealHelpers.test.js`
 * (run from client/)
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  APPEALS_LIST_LIMIT,
  canSendInAppeal,
  createLocalSessionId,
  firstUserQuestionFromMessages,
  isServerAppealId,
  mapAppealStatusToTicketStatus,
  resolveEmployeeQuestion,
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
