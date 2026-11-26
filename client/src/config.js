/**
 * Конфигурация и демо-промпты для демонстрации 3 обязательных бизнес-кейсов
 */

export const DEMO_PROMPTS = [
  {
    id: 'case-1',
    text: 'Кто подписывает договоры на закупку?',
    badge: 'UC-01',
    subtitle: 'Ответ по регламенту с источником'
  },
  {
    id: 'case-2',
    text: 'Кто подписывает договоры?',
    badge: 'UC-02',
    subtitle: 'Уточняющий диалог'
  },
  {
    id: 'case-3',
    text: 'Какой цвет логотипа у конкурентов согласно брендбуку компании?',
    badge: 'UC-03',
    subtitle: 'Эскалация в СК и пополнение БЗ'
  },
  {
    id: 'case-4',
    text: 'Какая завтра погода в Москве?',
    badge: 'UC-04',
    subtitle: 'Отказ от вопроса не по регламенту'
  }
];

export const CONFIG = {
  DEFAULT_MODE: 'mock', // 'mock' | 'api'
  DEFAULT_API_BASE_URL: '/api/v1',
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
