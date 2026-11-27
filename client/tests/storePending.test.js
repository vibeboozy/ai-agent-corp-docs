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
