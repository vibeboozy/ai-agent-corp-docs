import { CONFIG } from '../config.js';

/**
 * Генерация уникального идентификатора сессии
 */
export function createSessionId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'sess-' + Math.random().toString(36).substring(2, 11) + Date.now().toString(36);
}

// Загрузка начальных параметров из localStorage
const savedMode = localStorage.getItem(CONFIG.STORAGE_KEYS.MODE) || CONFIG.DEFAULT_MODE;
const savedApiUrl = localStorage.getItem(CONFIG.STORAGE_KEYS.API_URL) || CONFIG.DEFAULT_API_BASE_URL;
let savedSessionId = localStorage.getItem(CONFIG.STORAGE_KEYS.SESSION_ID);
if (!savedSessionId) {
  savedSessionId = createSessionId();
  localStorage.setItem(CONFIG.STORAGE_KEYS.SESSION_ID, savedSessionId);
}

let savedChat = [];
try {
  const rawChat = localStorage.getItem(CONFIG.STORAGE_KEYS.CHAT_HISTORY);
  if (rawChat) savedChat = JSON.parse(rawChat);
} catch {
  savedChat = [];
}

let savedSessions = [];
try {
  const rawSessions = localStorage.getItem(CONFIG.STORAGE_KEYS.SESSIONS);
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
  localStorage.setItem(CONFIG.STORAGE_KEYS.SESSIONS, JSON.stringify(savedSessions));
}

const initialState = {
  activeTab: 'chat', // 'chat' | 'quality' | 'analytics'
  mode: savedMode,
  apiBaseUrl: savedApiUrl,
  sessionId: savedSessionId,
  chatMessages: savedChat,
  sessions: savedSessions,
  chatLoading: false,
  tickets: [],
  selectedTicketId: null,
  ticketFilter: 'all', // 'all' | 'open' | 'resolved'
  ticketsLoading: false,
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
      localStorage.setItem(CONFIG.STORAGE_KEYS.MODE, this.state.mode);
    }
    if (partial.apiBaseUrl !== undefined) {
      localStorage.setItem(CONFIG.STORAGE_KEYS.API_URL, this.state.apiBaseUrl);
    }
    if (partial.sessionId !== undefined) {
      localStorage.setItem(CONFIG.STORAGE_KEYS.SESSION_ID, this.state.sessionId);
    }
    if (partial.chatMessages !== undefined) {
      localStorage.setItem(CONFIG.STORAGE_KEYS.CHAT_HISTORY, JSON.stringify(this.state.chatMessages));
    }
    if (partial.sessions !== undefined) {
      localStorage.setItem(CONFIG.STORAGE_KEYS.SESSIONS, JSON.stringify(this.state.sessions));
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
      chatMessages: [],
      chatLoading: false
    });
  }

  /**
   * Переключение на ранее сохранённую сессию из истории
   * @param {string} sessionId 
   */
  switchSession(sessionId) {
    const session = this.state.sessions.find((s) => s.session_id === sessionId);
    if (session) {
      this.setState({
        sessionId: session.session_id,
        chatMessages: session.messages || [],
        chatLoading: false
      });
    }
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
        messages: newMessages
      };
    } else {
      sessions.unshift({
        session_id: currentSessionId,
        title: autoTitle,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        messages: newMessages
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
