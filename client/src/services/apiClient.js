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
    const url = `${this.getBaseUrl()}${endpoint.startsWith('/') ? endpoint : '/' + endpoint}`;
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
          // Игнорируем ошибку парсинга тела ошибки
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
   * Отправка вопроса в чат (POST /chat)
   * @param {{ question: string, session_id: string, history: Array }} payload
   */
  async sendChatMessage(payload) {
    if (this.isMockMode()) {
      return await mockService.sendChatMessage(payload);
    }

    return await this.request('/chat', {
      method: 'POST',
      body: JSON.stringify({
        question: payload.question,
        session_id: payload.session_id,
        history: payload.history || []
      })
    });
  }

  /**
   * Создание тикета при эскалации (POST /tickets)
   * @param {{ question: string, email_draft: Object, session_id: string, context?: string }} payload
   */
  async createTicket(payload) {
    if (this.isMockMode()) {
      return await mockService.createTicket(payload);
    }

    const data = await this.request('/tickets', {
      method: 'POST',
      body: JSON.stringify({
        question: payload.question,
        email_to: payload.email_draft?.to || 'quality@company.ru',
        email_subject: payload.email_draft?.subject || '',
        email_body: payload.email_draft?.body || '',
        email_draft: payload.email_draft,
        session_id: payload.session_id,
        context: payload.context || ''
      })
    });

    return data.ticket || data;
  }

  /**
   * Загрузка списка тикетов (GET /tickets)
   * @param {string} [status]
   */
  async getTickets(status = null) {
    if (this.isMockMode()) {
      return await mockService.getTickets(status);
    }

    const query = status && status !== 'all' ? `?status=${encodeURIComponent(status)}` : '';
    const data = await this.request(`/tickets${query}`, {
      method: 'GET'
    });

    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.tickets)) return data.tickets;
    return [];
  }

  /**
   * Добавление ответа эксперта и пополнение БЗ (POST /tickets/{ticketId}/resolve)
   * @param {string} ticketId
   * @param {{ answer: string, regulation_ref: string }} payload
   */
  async resolveTicket(ticketId, payload) {
    if (this.isMockMode()) {
      return await mockService.resolveTicket(ticketId, payload);
    }

    const data = await this.request(`/tickets/${encodeURIComponent(ticketId)}/resolve`, {
      method: 'POST',
      body: JSON.stringify({
        answer: payload.answer,
        regulation_ref: payload.regulation_ref
      })
    });

    return data.ticket || data;
  }
}

export const apiClient = new ApiClient();
