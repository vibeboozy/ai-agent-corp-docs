/**
 * Node built-in test runner: `node --test tests/storePending.test.js`
 * (run from client/)
 */
import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { store } from '../src/state/store.js';

describe('per-session chat pending loader', () => {
  beforeEach(() => {
    store.setState({
      sessionId: 'sess-a',
      chatMessages: [],
      sessions: [
        {
          session_id: 'sess-a',
          title: 'A',
          messages: [],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        },
        {
          session_id: 'sess-b',
          title: 'B',
          messages: [{ id: 1, role: 'user', content: 'hi' }],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        }
      ],
      pendingSessionIds: [],
      chatLoading: false,
      appealStatus: null
    });
  });

  it('keeps pending when switching away and restores loader on return', () => {
    store.saveSessionMessages('sess-a', [
      { id: 1, role: 'user', content: 'Кто подписывает договоры?' }
    ]);
    store.markSessionPending('sess-a');
    assert.equal(store.getState().chatLoading, true);
    assert.equal(store.isSessionPending('sess-a'), true);

    store.switchSession('sess-b');
    assert.equal(store.getState().sessionId, 'sess-b');
    assert.equal(store.getState().chatLoading, false);
    assert.equal(store.isSessionPending('sess-a'), true);

    store.switchSession('sess-a');
    assert.equal(store.getState().sessionId, 'sess-a');
    assert.equal(store.getState().chatLoading, true);
    assert.equal(store.getState().chatMessages[0].content, 'Кто подписывает договоры?');
  });

  it('saves assistant reply to the requesting session while viewing another', () => {
    store.saveSessionMessages('sess-a', [
      { id: 1, role: 'user', content: 'Вопрос A' }
    ]);
    store.markSessionPending('sess-a');
    store.switchSession('sess-b');

    store.saveSessionMessages('sess-a', [
      { id: 1, role: 'user', content: 'Вопрос A' },
      { id: 2, role: 'assistant', content: 'Ответ: коротко.', status: 'answer' }
    ]);
    store.clearSessionPending('sess-a');

    assert.equal(store.getState().sessionId, 'sess-b');
    assert.equal(store.getState().chatLoading, false);
    const a = store.getState().sessions.find((s) => s.session_id === 'sess-a');
    assert.equal(a.messages.length, 2);
    assert.match(a.messages[1].content, /^Ответ:/);
  });

  it('remaps pending id when local session becomes server UUID', () => {
    store.markSessionPending('sess-a');
    store.updateSessionId('sess-a', 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'clarifying');
    assert.equal(store.isSessionPending('sess-a'), false);
    assert.equal(
      store.isSessionPending('a1b2c3d4-e5f6-7890-abcd-ef1234567890'),
      true
    );
    assert.equal(store.getState().chatLoading, true);
  });
});

describe('applyAppealHistoryReload', () => {
  const appealId = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';

  beforeEach(() => {
    const localMessages = [
      { id: 'u1', role: 'user', content: 'Маржа?' },
      {
        id: 'a1',
        role: 'assistant',
        content: 'Нет в регламентах',
        status: 'escalate',
        email_draft: { to: 'quality@company.ru', subject: 'S', body: 'B' },
        ticketCreated: false
      }
    ];
    store.setState({
      sessionId: appealId,
      chatMessages: localMessages,
      sessions: [
        {
          session_id: appealId,
          title: 'Маржа?',
          messages: localMessages,
          appeal_status: 'escalated',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        }
      ],
      pendingSessionIds: [],
      chatLoading: false,
      appealStatus: 'escalated'
    });
  });

  it('keeps the same chatMessages reference when reload is render-equal', () => {
    const before = store.getState().chatMessages;
    const reload = JSON.parse(JSON.stringify(before));
    let notifyCount = 0;
    const unsub = store.subscribe(() => {
      notifyCount += 1;
    });

    store.applyAppealHistoryReload(appealId, {
      messages: reload,
      appealStatus: 'escalated',
      chatLoading: false
    });
    unsub();

    // sessions may update (new array), but active feed reference must stay put
    assert.equal(store.getState().chatMessages, before);
    assert.equal(store.getState().appealStatus, 'escalated');
    assert.ok(notifyCount <= 1);
  });

  it('applies messages + status + loading in one notification', () => {
    const nextMessages = [
      { id: 'u1', role: 'user', content: 'Маржа?' },
      {
        id: 'a1',
        role: 'assistant',
        content: 'Нет в регламентах (server)',
        status: 'escalate',
        email_draft: { to: 'quality@company.ru', subject: 'S', body: 'B' },
        ticketCreated: true,
        ticketId: 't-1'
      }
    ];
    let notifyCount = 0;
    const unsub = store.subscribe(() => {
      notifyCount += 1;
    });

    store.applyAppealHistoryReload(appealId, {
      messages: nextMessages,
      appealStatus: 'escalated',
      chatLoading: false
    });
    unsub();

    assert.equal(notifyCount, 1);
    assert.equal(store.getState().chatMessages[1].ticketCreated, true);
    assert.equal(store.getState().chatMessages[1].ticketId, 't-1');
    const session = store.getState().sessions.find((s) => s.session_id === appealId);
    assert.equal(session.messages[1].ticketCreated, true);
  });

  it('updates appealStatus without replacing equal messages', () => {
    const before = store.getState().chatMessages;
    store.applyAppealHistoryReload(appealId, {
      messages: JSON.parse(JSON.stringify(before)),
      appealStatus: 'resolved_by_officer',
      chatLoading: false
    });
    assert.equal(store.getState().chatMessages, before);
    assert.equal(store.getState().appealStatus, 'resolved_by_officer');
  });
});
