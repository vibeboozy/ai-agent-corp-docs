import { store } from '../state/store.js';
import { mockService } from './mockService.js';
import { CONFIG } from '../config.js';
import {
  APPEALS_LIST_LIMIT,
  isServerAppealId,
  mapAppealStatusToTicketStatus,
  resolveEmployeeQuestion
} from '../utils/appealHelpers.js';

class ApiClient {
  getBaseUrl() {
    const raw = store.getState().apiBaseUrl || CONFIG.DEFAULT_API_BASE_URL;
    return raw.replace(/\/+$/, '');
  }

  isMockMode() {
    return store.getState().mode === 'mock';
  }

  /**
   * Выполнение сетевого HTTP-запроса с таймаутом и обработкой ошибок
   */
  async request(endpoint, options = {}) {
    const baseUrl = this.getBaseUrl();
    const url = `${baseUrl}${endpoint.startsWith('/') ? endpoint : '/' + endpoint}`;
    const timeout = options.timeout || CONFIG.REQUEST_TIMEOUT_MS;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    const headers = {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(options.headers || {})
    };

    try {
      const response = await fetch(url, {
        ...options,
        headers,
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        let errorDetail = `Ошибка сервера: ${response.status} ${response.statusText}`;
        let errorCode = null;
        try {
          const errorData = await response.json();
          if (errorData.detail) {
            errorDetail = typeof errorData.detail === 'string'
              ? errorData.detail
              : JSON.stringify(errorData.detail);
          } else if (errorData.message) {
            errorDetail = errorData.message;
          }
          if (errorData.code) errorCode = errorData.code;
        } catch {
          // Игнорируем ошибку парсинга тела
        }
        const err = new Error(errorDetail);
        err.status = response.status;
        err.code = errorCode;
        throw err;
      }

      return await response.json();
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError') {
        throw new Error(`Превышено время ожидания ответа сервера (${timeout / 1000} сек)`);
      }
      throw err;
    }
  }

  /**
   * Create a new appeal with the first user message.
   */
  async createAppealWithMessage(question) {
    return await this.request('/appeals', {
      method: 'POST',
      body: JSON.stringify({
        topic: question.slice(0, 120),
        message: {
          content: question
        }
      })
    });
  }

  /**
   * Post a follow-up user message to an existing appeal.
   */
  async postAppealMessage(appealId, question) {
    return await this.request(`/appeals/${appealId}/messages`, {
      method: 'POST',
      body: JSON.stringify({
        content: question,
        role: 'user'
      })
    });
  }

  /**
   * Normalize CreateAppeal / CreateMessage response into the chat UI shape.
   */
  normalizeChatResponse(responseData, question, sessionId) {
    const appeal = responseData.appeal || {};
    const messages = responseData.messages || [];
    const lastAssistantMsg =
      [...messages].reverse().find((m) => m.role === 'assistant') ||
      messages[messages.length - 1];

    let status = 'answer';
    if (appeal.status === 'clarifying' || lastAssistantMsg?.message_kind === 'clarification') {
      status = 'clarify';
    } else if (appeal.status === 'escalated' || lastAssistantMsg?.message_kind === 'escalation_notice') {
      status = 'escalate';
    } else if (lastAssistantMsg?.message_kind === 'refusal') {
      status = 'refusal';
    }

    const citations = (lastAssistantMsg?.citations || []).map((c) => ({
      doc_name: c.document_title || c.document_id || 'Корпоративный регламент',
      section: c.locator || '',
      quote: c.quote || ''
    }));

    let email_draft = null;
    if (status === 'escalate') {
      email_draft = {
        to: 'quality@company.ru',
        subject: `Запрос разъяснения регламента: ${question.slice(0, 45)}...`,
        body:
          `Здравствуйте!\n\nПрошу предоставить официальное разъяснение по вопросу:\n«${question}»\n\nС уважением,\nСотрудник отдела сопровождения`
      };
    }

    const appealId = appeal.id ? String(appeal.id) : sessionId;
    if (appeal.id && String(appeal.id) !== sessionId) {
      store.updateSessionId(sessionId, String(appeal.id), appeal.status || null);
    } else if (appeal.status) {
      store.setAppealStatus(appeal.status);
    }

    return {
      status,
      reply: lastAssistantMsg?.content || 'Ответ сформирован.',
      citations,
      email_draft,
      appeal_id: appealId,
      appeal_status: appeal.status || null
    };
  }

  /**
   * Отправка вопроса в чат (адаптировано под Appeal-центричный контракт бэкенда /api/v1/appeals)
   * @param {{ question: string, session_id: string, history: Array }} payload
   */
  async sendChatMessage(payload) {
    if (this.isMockMode()) {
      return await mockService.sendChatMessage(payload);
    }

    const { question, session_id } = payload;
    // Only continue an existing appeal when session_id is a real server UUID.
    // Local ids use sess-… prefix so they never collide with crypto.randomUUID leftovers.
    const hasServerAppeal = isServerAppealId(session_id);

    let responseData;
    if (hasServerAppeal) {
      try {
        responseData = await this.postAppealMessage(session_id, question);
      } catch (err) {
        // Stale local UUID that never existed on the server → create a fresh appeal.
        if (err.status === 404 || err.code === 'NOT_FOUND') {
          responseData = await this.createAppealWithMessage(question);
        } else {
          throw err;
        }
      }
    } else {
      responseData = await this.createAppealWithMessage(question);
    }

    return this.normalizeChatResponse(responseData, question, session_id);
  }

  /**
   * Создание тикета при эскалации
   */
  async createTicket(payload) {
    if (this.isMockMode()) {
      return await mockService.createTicket(payload);
    }

    // На бэкенде Appeal создаётся сразу при первом вопросе
    if (payload.session_id && isServerAppealId(payload.session_id)) {
      return {
        ticket_id: payload.session_id,
        status: 'open'
      };
    }

    const data = await this.request('/appeals', {
      method: 'POST',
      body: JSON.stringify({
        topic: payload.question || 'Эскалация в Службу качества',
        message: {
          content: payload.question || payload.email_draft?.body || ''
        }
      })
    });

    return {
      ticket_id: data.appeal?.id || 'SQ-101',
      status: 'open'
    };
  }

  /**
   * Map a server Appeal DTO to the quality-cabinet ticket shape.
   * Never use summary as the employee question (summary is the AI answer/refusal).
   */
  mapAppealToTicket(item) {
    const uiStatus = mapAppealStatusToTicketStatus(item.status);
    const isResolved = uiStatus === 'resolved';
    const question = resolveEmployeeQuestion({
      topic: item.topic,
      question: item.question
    });

    return {
      ticket_id: String(item.id),
      question,
      status: uiStatus,
      raw_status: item.status,
      email_to: 'quality@company.ru',
      email_subject: item.topic || `Обращение ${String(item.id).slice(0, 8)}`,
      email_body: item.summary || '',
      context: null,
      dialogue: null,
      created_at: item.created_at,
      answer: isResolved ? (item.summary || 'Ответ эксперта внесён в базу знаний') : null,
      regulation_ref: item.topic || 'Регламент компании',
      resolved_at: isResolved ? item.updated_at : null,
      session_id: String(item.id),
      message_count: item.message_count || 0
    };
  }

  /**
   * Загрузка списка тикетов / обращений (GET /api/v1/appeals)
   * @param {string} [status]
   */
  async getTickets(status = null) {
    if (this.isMockMode()) {
      return await mockService.getTickets(status);
    }

    const params = new URLSearchParams();
    params.set('limit', String(APPEALS_LIST_LIMIT));
    if (status === 'open') {
      params.set('status', 'escalated');
    } else if (status === 'resolved') {
      params.set('status', 'resolved_by_officer');
    } else if (status === 'answered') {
      params.set('status', 'answered');
    }

    const data = await this.request(`/appeals?${params.toString()}`, {
      method: 'GET'
    });

    const items = data.items || (Array.isArray(data) ? data : []);
    return items.map((item) => this.mapAppealToTicket(item));
  }

  /**
   * Закрытие тикета экспертом СК и дообучение (POST /api/v1/appeals/{id}/officer-reply)
   * @param {string} ticketId
   * @param {{ answer: string, regulation_ref: string }} payload
   */
  async resolveTicket(ticketId, payload) {
    if (this.isMockMode()) {
      return await mockService.resolveTicket(ticketId, payload);
    }

    const data = await this.request(`/appeals/${ticketId}/officer-reply`, {
      method: 'POST',
      body: JSON.stringify({
        content: payload.answer,
        source_document_hint: payload.regulation_ref
      })
    });

    const appeal = data.appeal || {};
    return {
      ticket_id: appeal.id || ticketId,
      status: 'resolved',
      answer: payload.answer,
      regulation_ref: payload.regulation_ref,
      resolved_at: appeal.updated_at || new Date().toISOString()
    };
  }

  /**
   * Получение статистики для вкладки Аналитики (GET /api/v1/stats)
   */
  async getStats() {
    if (this.isMockMode()) {
      return {
        appeals_total: 42,
        by_status: { answered: 28, clarifying: 6, escalated: 8 },
        messages_total: 126,
        clarify_rate: 0.14,
        escalation_rate: 0.19,
        answered_rate: 0.67,
        learning_updates: 5
      };
    }

    return await this.request('/stats', {
      method: 'GET'
    });
  }

  /**
   * Получение детальной карточки обращения (GET /api/v1/appeals/{id})
   * @param {string} appealId
   */
  async getAppeal(appealId) {
    if (this.isMockMode()) {
      const tickets = mockService.getStoredTickets();
      const ticket = tickets.find((t) => t.ticket_id === appealId || t.session_id === appealId);
      if (!ticket) throw new Error('Обращение не найдено');
      return ticket;
    }

    return await this.request(`/appeals/${appealId}`, {
      method: 'GET'
    });
  }

  /**
   * Получение полной истории сообщений обращения с бэкенда (GET /api/v1/appeals/{id}/messages)
   * @param {string} appealId
   */
  async getAppealMessages(appealId) {
    if (this.isMockMode()) {
      const history = mockService.getHistory();
      return {
        appeal_id: appealId,
        items: history
      };
    }

    const data = await this.request(`/appeals/${appealId}/messages`, {
      method: 'GET'
    });

    const items = data.items || [];
    return {
      appeal_id: data.appeal_id || appealId,
      items: items.map((m) => {
        let status = 'answer';
        if (m.message_kind === 'clarification') {
          status = 'clarify';
        } else if (m.message_kind === 'escalation_notice') {
          status = 'escalate';
        } else if (m.message_kind === 'refusal') {
          status = 'refusal';
        }

        const citations = (m.citations || []).map((c) => ({
          doc_name: c.document_title || c.document_id || 'Корпоративный регламент',
          section: c.locator || '',
          quote: c.quote || ''
        }));

        return {
          id: m.id,
          role: m.role,
          content: m.content,
          status,
          message_kind: m.message_kind,
          citations,
          timestamp: m.created_at || new Date().toISOString()
        };
      })
    };
  }
}

export const apiClient = new ApiClient();
