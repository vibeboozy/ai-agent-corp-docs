import { CONFIG } from '../config.js';
import {
  areChatMessagesRenderEqual,
  createLocalSessionId,
  isServerAppealId
} from '../utils/appealHelpers.js';

/**
 * Генерация локального id сессии (НЕ UUID серверного appeal).
 * См. appealHelpers.createLocalSessionId — UUID-формат ломал POST /messages (404).
 */
export function createSessionId() {
  return createLocalSessionId();
}

const safeStorage = typeof localStorage !== 'undefined' ? localStorage : {
  _data: {},
  getItem(k) { return this._data[k] || null; },
  setItem(k, v) { this._data[k] = String(v); },
  removeItem(k) { delete this._data[k]; }
};

// Загрузка начальных параметров из localStorage
const savedMode = safeStorage.getItem(CONFIG.STORAGE_KEYS.MODE) || CONFIG.DEFAULT_MODE;
const savedApiUrl = safeStorage.getItem(CONFIG.STORAGE_KEYS.API_URL) || CONFIG.DEFAULT_API_BASE_URL;
let savedSessionId = safeStorage.getItem(CONFIG.STORAGE_KEYS.SESSION_ID);
if (!savedSessionId) {
  savedSessionId = createSessionId();
  safeStorage.setItem(CONFIG.STORAGE_KEYS.SESSION_ID, savedSessionId);
}

let savedChat = [];
try {
  const rawChat = safeStorage.getItem(CONFIG.STORAGE_KEYS.CHAT_HISTORY);
  if (rawChat) savedChat = JSON.parse(rawChat);
} catch {
  savedChat = [];
}

let savedSessions = [];
try {
  const rawSessions = safeStorage.getItem(CONFIG.STORAGE_KEYS.SESSIONS);
  if (rawSessions) savedSessions = JSON.parse(rawSessions);
} catch {
  savedSessions = [];
}

// Миграция/синхронизация: если есть открытый чат, регистрируем его в списке сессий
if (savedChat.length > 0 && !savedSessions.some((s) => s.session_id === savedSessionId)) {
  const firstUserMsg = savedChat.find((m) => m.role === 'user');
  savedSessions.unshift({
    session_id: savedSessionId,
    title: firstUserMsg ? firstUserMsg.content.slice(0, 45) : 'Предыдущий диалог',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    messages: savedChat
  });
  safeStorage.setItem(CONFIG.STORAGE_KEYS.SESSIONS, JSON.stringify(savedSessions));
}

const initialState = {
  activeTab: 'chat', // 'chat' | 'quality' | 'analytics'
  mode: savedMode,
  apiBaseUrl: savedApiUrl,
  sessionId: savedSessionId,
  /** Server AppealStatus for the active session (null until first API response). */
  appealStatus: null,
  chatMessages: savedChat,
  sessions: savedSessions,
  chatLoading: false,
  /** Session ids with an in-flight assistant request (survives navigate-away). */
  pendingSessionIds: [],
  tickets: [],
  selectedTicketId: null,
  ticketFilter: 'all', // 'all' | 'open' | 'resolved' | 'answered' | 'in_progress'
  ticketsLoading: false,
  ticketsLoadedOnce: false,
  isSettingsOpen: false
};

class Store {
  constructor(state) {
    this.state = state;
    this.listeners = new Set();
  }

  getState() {
    return this.state;
  }

  setState(partial) {
    const prevState = this.state;
    this.state = { ...this.state, ...partial };

    // Синхронизация с localStorage
    if (partial.mode !== undefined) {
      safeStorage.setItem(CONFIG.STORAGE_KEYS.MODE, this.state.mode);
    }
    if (partial.apiBaseUrl !== undefined) {
      safeStorage.setItem(CONFIG.STORAGE_KEYS.API_URL, this.state.apiBaseUrl);
    }
    if (partial.sessionId !== undefined) {
      safeStorage.setItem(CONFIG.STORAGE_KEYS.SESSION_ID, this.state.sessionId);
    }
    if (partial.chatMessages !== undefined) {
      safeStorage.setItem(CONFIG.STORAGE_KEYS.CHAT_HISTORY, JSON.stringify(this.state.chatMessages));
    }
    if (partial.sessions !== undefined) {
      safeStorage.setItem(CONFIG.STORAGE_KEYS.SESSIONS, JSON.stringify(this.state.sessions));
    }

    // Оповещение подписчиков
    this.listeners.forEach((listener) => {
      try {
        listener(this.state, prevState);
      } catch (err) {
        console.error('Store listener error:', err);
      }
    });
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /**
   * Сброс текущей беседы в чате (начало нового диалога)
   */
  startNewChat() {
    const newSessionId = createSessionId();
    this.setState({
      sessionId: newSessionId,
      appealStatus: null,
      chatMessages: [],
      chatLoading: false
    });
  }

  isSessionPending(sessionId) {
    if (!sessionId) return false;
    return (this.state.pendingSessionIds || []).includes(sessionId);
  }

  markSessionPending(sessionId) {
    if (!sessionId) return;
    const pending = this.state.pendingSessionIds || [];
    const next = pending.includes(sessionId) ? pending : [...pending, sessionId];
    this.setState({
      pendingSessionIds: next,
      chatLoading: next.includes(this.state.sessionId)
    });
  }

  clearSessionPending(sessionId) {
    if (!sessionId) return;
    const pending = (this.state.pendingSessionIds || []).filter((id) => id !== sessionId);
    this.setState({
      pendingSessionIds: pending,
      chatLoading: pending.includes(this.state.sessionId)
    });
  }

  getSessionMessages(sessionId) {
    if (!sessionId) return [];
    if (sessionId === this.state.sessionId) {
      return this.state.chatMessages || [];
    }
    const session = (this.state.sessions || []).find((s) => s.session_id === sessionId);
    return session?.messages || [];
  }

  /**
   * Persist messages for a specific session (active or background).
   * Keeps the in-flight answer attached to the appeal that asked, even after navigate-away.
   */
  saveSessionMessages(sessionId, newMessages) {
    if (!sessionId) return;
    const sessions = [...this.state.sessions];
    const index = sessions.findIndex((s) => s.session_id === sessionId);
    const firstUserMsg = (newMessages || []).find((m) => m.role === 'user');
    const autoTitle = firstUserMsg ? firstUserMsg.content.slice(0, 45) : 'Новый диалог';

    if (index >= 0) {
      sessions[index] = {
        ...sessions[index],
        title:
          sessions[index].title && sessions[index].title !== 'Новый диалог'
            ? sessions[index].title
            : autoTitle,
        updated_at: new Date().toISOString(),
        messages: newMessages,
        appeal_status:
          sessionId === this.state.sessionId
            ? this.state.appealStatus
            : sessions[index].appeal_status
      };
    } else {
      sessions.unshift({
        session_id: sessionId,
        title: autoTitle,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        messages: newMessages,
        appeal_status: sessionId === this.state.sessionId ? this.state.appealStatus : null
      });
    }

    const partial = { sessions };
    if (sessionId === this.state.sessionId) {
      partial.chatMessages = newMessages;
    }
    this.setState(partial);
  }

  /**
   * Apply a server history reload for one appeal in a single setState.
   * Avoids the open-path flicker from sequential saveSessionMessages →
   * setChatLoading → setAppealStatus (each remounted the whole feed).
   * Skips replacing active chatMessages when the feed would look the same.
   *
   * @param {string} sessionId
   * @param {{ messages?: Array, appealStatus?: string|null, chatLoading?: boolean }} payload
   */
  applyAppealHistoryReload(sessionId, payload = {}) {
    if (!sessionId) return;
    const { messages, appealStatus, chatLoading } = payload;
    const isActive = this.state.sessionId === sessionId;
    const hasMessages = Array.isArray(messages);
    const nextStatus =
      appealStatus !== undefined && appealStatus !== null
        ? appealStatus
        : isActive
          ? this.state.appealStatus
          : null;

    let sessions = this.state.sessions;
    let sessionsChanged = false;

    if (hasMessages) {
      sessions = [...this.state.sessions];
      const index = sessions.findIndex((s) => s.session_id === sessionId);
      const firstUserMsg = messages.find((m) => m.role === 'user');
      const autoTitle = firstUserMsg ? firstUserMsg.content.slice(0, 45) : 'Новый диалог';
      const statusForSession =
        appealStatus !== undefined && appealStatus !== null
          ? appealStatus
          : index >= 0
            ? sessions[index].appeal_status
            : null;

      if (index >= 0) {
        sessions[index] = {
          ...sessions[index],
          title:
            sessions[index].title && sessions[index].title !== 'Новый диалог'
              ? sessions[index].title
              : autoTitle,
          updated_at: new Date().toISOString(),
          messages,
          appeal_status: statusForSession
        };
      } else {
        sessions.unshift({
          session_id: sessionId,
          title: autoTitle,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          messages,
          appeal_status: statusForSession
        });
      }
      sessionsChanged = true;
    } else if (appealStatus !== undefined && appealStatus !== null) {
      sessions = this.state.sessions.map((s) => {
        if (s.session_id !== sessionId) return s;
        if (s.appeal_status === appealStatus) return s;
        sessionsChanged = true;
        return { ...s, appeal_status: appealStatus };
      });
    }

    const partial = {};
    if (sessionsChanged) {
      partial.sessions = sessions;
    }

    if (isActive && hasMessages) {
      const sameFeed = areChatMessagesRenderEqual(this.state.chatMessages, messages);
      if (!sameFeed) {
        partial.chatMessages = messages;
      }
    }

    if (
      isActive &&
      appealStatus !== undefined &&
      appealStatus !== null &&
      appealStatus !== this.state.appealStatus
    ) {
      partial.appealStatus = appealStatus;
    }

    if (chatLoading !== undefined && chatLoading !== this.state.chatLoading) {
      // Only touch loading for the active appeal; background reloads must not
      // clear/set the spinner of a different open chat.
      if (isActive) {
        partial.chatLoading = chatLoading;
      }
    }

    if (Object.keys(partial).length === 0) return;
    this.setState(partial);
  }

  /**
   * Переключение на ранее сохранённую сессию из истории
   * @param {string} sessionId 
   */
  switchSession(sessionId) {
    const session = this.state.sessions.find((s) => s.session_id === sessionId);
    if (session) {
      const pending = this.isSessionPending(session.session_id);
      this.setState({
        sessionId: session.session_id,
        appealStatus: session.appeal_status || null,
        chatMessages: session.messages || [],
        chatLoading: pending
      });
    }
  }

  /**
   * Обновление идентификатора сессии при получении реального UUID от бэкенда
   * @param {string} oldId 
   * @param {string} newId 
   * @param {string} [appealStatus]
   */
  updateSessionId(oldId, newId, appealStatus) {
    if (!newId || oldId === newId) {
      if (appealStatus && this.state.sessionId === (newId || oldId)) {
        this.setAppealStatus(appealStatus);
      }
      return;
    }
    if (!isServerAppealId(newId)) return;
    const sessions = this.state.sessions.map((s) => {
      if (s.session_id === oldId) {
        return {
          ...s,
          session_id: newId,
          appeal_status: appealStatus || s.appeal_status || null
        };
      }
      return s;
    });
    const pendingSessionIds = (this.state.pendingSessionIds || []).map((id) =>
      id === oldId ? newId : id
    );
    const nextSessionId = this.state.sessionId === oldId ? newId : this.state.sessionId;
    this.setState({
      sessionId: nextSessionId,
      appealStatus:
        this.state.sessionId === oldId
          ? appealStatus || this.state.appealStatus
          : this.state.appealStatus,
      sessions,
      pendingSessionIds,
      chatLoading: pendingSessionIds.includes(nextSessionId)
    });
  }

  setAppealStatus(appealStatus) {
    const currentSessionId = this.state.sessionId;
    const sessions = this.state.sessions.map((s) => {
      if (s.session_id === currentSessionId) {
        return { ...s, appeal_status: appealStatus };
      }
      return s;
    });
    this.setState({ appealStatus, sessions });
  }

  /**
   * Сохранение сообщений активной сессии с авто-обновлением заголовка
   * @param {Array} newMessages 
   */
  saveActiveSessionMessages(newMessages) {
    const currentSessionId = this.state.sessionId;
    const sessions = [...this.state.sessions];
    const index = sessions.findIndex((s) => s.session_id === currentSessionId);

    const firstUserMsg = newMessages.find((m) => m.role === 'user');
    const autoTitle = firstUserMsg ? firstUserMsg.content.slice(0, 45) : 'Новый диалог';

    if (index >= 0) {
      sessions[index] = {
        ...sessions[index],
        title: sessions[index].title && sessions[index].title !== 'Новый диалог' ? sessions[index].title : autoTitle,
        updated_at: new Date().toISOString(),
        messages: newMessages,
        appeal_status: this.state.appealStatus
      };
    } else {
      sessions.unshift({
        session_id: currentSessionId,
        title: autoTitle,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        messages: newMessages,
        appeal_status: this.state.appealStatus
      });
    }

    this.setState({
      chatMessages: newMessages,
      sessions
    });
  }

  /**
   * Подсчёт открытых тикетов
   */
  getOpenTicketsCount() {
    return this.state.tickets.filter((t) => t.status === 'open').length;
  }
}

export const store = new Store(initialState);
