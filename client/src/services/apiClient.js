import { store } from '../state/store.js';
import { mockService } from './mockService.js';
import { CONFIG } from '../config.js';

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
        try {
          const errorData = await response.json();
          if (errorData.detail) {
            errorDetail = typeof errorData.detail === 'string'
              ? errorData.detail
              : JSON.stringify(errorData.detail);
          } else if (errorData.message) {
            errorDetail = errorData.message;
          }
        } catch {
          // Игнорируем ошибку парсинга тела
        }
        throw new Error(errorDetail);
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
   * Отправка вопроса в чат (адаптировано под Appeal-центричный контракт бэкенда /api/v1/appeals)
   * @param {{ question: string, session_id: string, history: Array }} payload
   */
  async sendChatMessage(payload) {
    if (this.isMockMode()) {
      return await mockService.sendChatMessage(payload);
    }

    const { question, session_id } = payload;
    const isServerUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(session_id);

    let responseData;
    if (isServerUuid) {
      // Продолжение диалога внутри существующего обращения: POST /api/v1/appeals/{id}/messages
      responseData = await this.request(`/appeals/${session_id}/messages`, {
        method: 'POST',
        body: JSON.stringify({
          content: question,
          role: 'user'
        })
      });
    } else {
      // Старт нового обращения: POST /api/v1/appeals
      responseData = await this.request('/appeals', {
        method: 'POST',
        body: JSON.stringify({
          topic: question.slice(0, 50),
          message: {
            content: question
          }
        })
      });
    }

    const appeal = responseData.appeal || {};
    const messages = responseData.messages || [];
    const lastAssistantMsg = [...messages].reverse().find((m) => m.role === 'assistant') || messages[messages.length - 1];

    let status = 'answer';
    if (appeal.status === 'clarifying' || lastAssistantMsg?.message_kind === 'clarification') {
      status = 'clarify';
    } else if (appeal.status === 'escalated' || lastAssistantMsg?.message_kind === 'escalation_notice') {
      status = 'escalate';
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
        body: `Здравствуйте!\n\nПрошу предоставить официальное разъяснение по вопросу:\n«${question}»\n\nС уважением,\nСотрудник отдела сопровождения`
      };
    }

    // Если сервер сгенерировал новый UUID для Appeal, синхронизируем идентификатор сессии
    if (appeal.id && String(appeal.id) !== session_id) {
      store.updateSessionId(session_id, String(appeal.id));
    }

    return {
      status,
      reply: lastAssistantMsg?.content || 'Ответ сформирован.',
      citations,
      email_draft,
      appeal_id: appeal.id || session_id
    };
  }

  /**
   * Создание тикета при эскалации
   */
  async createTicket(payload) {
    if (this.isMockMode()) {
      return await mockService.createTicket(payload);
    }

    // На бэкенде Appeal создаётся сразу при первом вопросе
    if (payload.session_id) {
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
   * Загрузка списка тикетов / обращений (GET /api/v1/appeals)
   * @param {string} [status]
   */
  async getTickets(status = null) {
    if (this.isMockMode()) {
      return await mockService.getTickets(status);
    }

    let query = '';
    if (status === 'open') {
      query = '?status=escalated';
    } else if (status === 'resolved') {
      query = '?status=resolved_by_officer';
    }

    const data = await this.request(`/appeals${query}`, {
      method: 'GET'
    });

    const items = data.items || (Array.isArray(data) ? data : []);

    return items.map((item) => {
      const isResolved = item.status === 'resolved_by_officer' || item.status === 'closed';
      return {
        ticket_id: String(item.id),
        question: item.topic || item.summary || 'Вопрос сотрудника в Службу качества',
        status: isResolved ? 'resolved' : 'open',
        raw_status: item.status,
        email_to: 'quality@company.ru',
        email_subject: item.topic || `Обращение ${String(item.id).slice(0, 8)}`,
        email_body: item.summary || '',
        created_at: item.created_at,
        answer: item.summary || (isResolved ? 'Ответ эксперта внесён в базу знаний' : null),
        regulation_ref: item.topic || 'Регламент компании',
        resolved_at: isResolved ? item.updated_at : null
      };
    });
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
          citations,
          timestamp: m.created_at || new Date().toISOString()
        };
      })
    };
  }
}

export const apiClient = new ApiClient();
