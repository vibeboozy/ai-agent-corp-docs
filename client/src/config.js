/**
 * Конфигурация и демо-промпты для демонстрации 3 обязательных бизнес-кейсов
 */

export const DEMO_PROMPTS = [
  {
    id: 'case-1',
    text: 'Можно ли вернуть лицензию после активации ключа?',
    badge: 'Кейс 1',
    subtitle: 'Строгий ответ по регламенту'
  },
  {
    id: 'case-2',
    text: 'Что делать, если ключ не пришёл, а оплата прошла?',
    badge: 'Кейс 2',
    subtitle: 'Уточняющий диалог'
  },
  {
    id: 'case-3',
    text: 'Можно ли перенести лицензию на другое юрлицо при реорганизации?',
    badge: 'Кейс 3',
    subtitle: 'Эскалация и дообучение базы знаний'
  }
];

export const CONFIG = {
  DEFAULT_MODE: 'mock', // 'mock' | 'api'
  DEFAULT_API_BASE_URL: '/api',
  STORAGE_KEYS: {
    MODE: 'sq_agent_mode',
    API_URL: 'sq_agent_api_url',
    TICKETS: 'sq_agent_tickets',
    CHAT_HISTORY: 'sq_agent_chat_history',
    SESSION_ID: 'sq_agent_session_id',
    SESSIONS: 'sq_agent_sessions'
  },
  REQUEST_TIMEOUT_MS: 90000 // 90 секунд таймаут для RAG/LLM
};
