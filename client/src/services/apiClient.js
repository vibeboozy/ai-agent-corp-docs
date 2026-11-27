import { store } from '../state/store.js';
import { mockService } from './mockService.js';
import { CONFIG } from '../config.js';
import {
  APPEALS_LIST_LIMIT,
  attachEscalationEmailDrafts,
  buildEscalationEmailDraft,
  isServerAppealId,
  mapAppealStatusToTicketStatus,
  resolveEmployeeQuestion
} from '../utils/appealHelpers.js';
import { dedupeCitations } from '../utils/citations.js';

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
   * Пауза между опросами (мс).
   */
  sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * Сетевой обрыв без ответа сервера: у такой ошибки нет HTTP-статуса и кода
   * (fetch TypeError «Failed to fetch» при срезе соединения прокси, либо
   * AbortError по клиентскому таймауту).
   */
  isNetworkCut(err) {
    return Boolean(err) && err.status === undefined && err.code === undefined;
  }

  /**
   * Восстановление после обрыва долгого POST. Два режима отказа прокси-релея:
   *  A) запрос дошёл до бэкенда, ответ срезан на полпути — тогда ответ появится
   *     в БД, и мы его заберём поллингом GET /appeals/{id}/messages;
   *  B) запрос вообще не дошёл (в обращении нет нашего user-сообщения) —
   *     возвращаем null, вызывающая сторона повторно отправляет вопрос.
   */
  async pollMessagesUntilAnswer(appealId, question, { intervalMs = 4000, acceptedAfterMs = 40000, maxWaitMs = 120000 } = {}) {
    const start = Date.now();
    const deadline = start + maxWaitMs;
    const target = (question || '').trim();
    let consecutiveFailures = 0;
    while (Date.now() < deadline) {
      await this.sleep(intervalMs);
      let data;
      try {
        data = await this.getAppealMessages(appealId);
        consecutiveFailures = 0;
      } catch (err) {
        if (err.status === 404 || err.code === 'NOT_FOUND') throw err;
        if (this.isNetworkCut(err)) {
          consecutiveFailures += 1;
          // Три осечки подряд — похоже, API недоступен целиком, не мучаем пользователя.
          if (consecutiveFailures >= 3) {
            throw new Error('Сервер недоступен. Проверьте подключение и повторите вопрос.');
          }
        }
        continue; // иная ошибка (например 5xx) — считаем временной, опрашиваем дальше
      }
      const items = data.items || [];
      if (items.some((m) => m.role === 'assistant' && m.content)) {
        return { appeal: { id: data.appeal_id || appealId }, messages: items };
      }
      const accepted = items.some((m) => m.role === 'user' && (m.content || '').trim() === target);
      if (!accepted && Date.now() - start > acceptedAfterMs) {
        return null; // запрос до бэкенда не дошёл — нужна повторная отправка
      }
    }
    throw new Error('Ответ формируется дольше обычного. Повторите тот же вопрос — теперь он придёт мгновенно.');
  }

  /**
   * Поиск только что созданного обращения по тексту вопроса — для первого
   * сообщения, когда id обращения не успели получить из-за обрыва.
   */
  async findAppealIdByQuestion(question, { intervalMs = 4000, maxWaitMs = 120000 } = {}) {
    const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
    const target = norm(question);
    const deadline = Date.now() + maxWaitMs;
    let consecutiveFailures = 0;
    while (Date.now() < deadline) {
      await this.sleep(intervalMs);
      let data;
      try {
        data = await this.request('/appeals?limit=20', { method: 'GET' });
        consecutiveFailures = 0;
      } catch (err) {
        if (this.isNetworkCut(err)) {
          consecutiveFailures += 1;
          if (consecutiveFailures >= 3) return null;
        }
        continue;
      }
      const items = data.items || (Array.isArray(data) ? data : []);
      const match = items.find((it) => {
        const q = norm(resolveEmployeeQuestion({ question: it.question, topic: it.topic }));
        return q === target && it.id;
      });
      if (match) return String(match.id);
    }
    return null;
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

    const citations = dedupeCitations(
      (lastAssistantMsg?.citations || []).map((c) => ({
        doc_name: c.document_title || c.document_id || 'Корпоративный регламент',
        section: c.locator || '',
        quote: c.quote || '',
        chunk_id: c.chunk_id || ''
      }))
    );

    // Draft is client-only (not on Message DTO) — same helper as history reload.
    const email_draft = status === 'escalate' ? buildEscalationEmailDraft(question) : null;

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
        if (err.status === 404 || err.code === 'NOT_FOUND') {
          // Stale local UUID that never existed on the server → create a fresh appeal.
          responseData = await this.createAppealWithMessage(question);
        } else if (this.isNetworkCut(err)) {
          // Соединение оборвано. Если запрос дошёл — дожидаемся ответа поллингом,
          // если нет — одна повторная отправка того же вопроса.
          const polled = await this.pollMessagesUntilAnswer(session_id, question);
          if (polled) {
            responseData = polled;
          } else {
            try {
              responseData = await this.postAppealMessage(session_id, question);
            } catch (err2) {
              if (!this.isNetworkCut(err2)) throw err2;
              const polled2 = await this.pollMessagesUntilAnswer(session_id, question);
              if (!polled2) {
                throw new Error('Не удалось получить ответ: соединение нестабильно. Повторите вопрос.');
              }
              responseData = polled2;
            }
          }
        } else {
          throw err;
        }
      }
    } else {
      try {
        responseData = await this.createAppealWithMessage(question);
      } catch (err) {
        if (!this.isNetworkCut(err)) throw err;
        // Первый вопрос: id обращения не успели получить — ищем его в списке
        // (обращение создаётся мгновенно, как только запрос дошёл до бэкенда).
        let appealId = await this.findAppealIdByQuestion(question, { maxWaitMs: 35000 });
        if (!appealId) {
          // Запрос не дошёл — одна повторная попытка.
          try {
            responseData = await this.createAppealWithMessage(question);
          } catch (err2) {
            if (!this.isNetworkCut(err2)) throw err2;
            appealId = await this.findAppealIdByQuestion(question, { maxWaitMs: 35000 });
          }
        }
        if (!appealId) {
          throw new Error('Не удалось получить ответ: соединение оборвалось. Повторите вопрос.');
        }
        const polled = await this.pollMessagesUntilAnswer(appealId, question);
        if (!polled) {
          throw new Error('Не удалось получить ответ: соединение оборвалось. Повторите вопрос.');
        }
        responseData = polled;
      }
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
    // Prefer API `question` (first user message) over topic; never use summary.
    const question = resolveEmployeeQuestion({
      question: item.question,
      topic: item.topic
    });

    return {
      ticket_id: String(item.id),
      question,
      status: uiStatus,
      raw_status: item.status,
      topic: item.topic || null,
      summary: item.summary || null,
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
        items: attachEscalationEmailDrafts(history || [])
      };
    }

    const data = await this.request(`/appeals/${appealId}/messages`, {
      method: 'GET'
    });

    const items = data.items || [];
    // email_draft is not stored on the server — recompute for escalate so the
    // «Превью запроса в Службу качества» form survives leave/return.
    const mapped = items.map((m) => {
      let status = 'answer';
      if (m.message_kind === 'clarification') {
        status = 'clarify';
      } else if (m.message_kind === 'escalation_notice') {
        status = 'escalate';
      } else if (m.message_kind === 'refusal') {
        status = 'refusal';
      }

      const citations = dedupeCitations(
        (m.citations || []).map((c) => ({
          doc_name: c.document_title || c.document_id || 'Корпоративный регламент',
          section: c.locator || '',
          quote: c.quote || '',
          chunk_id: c.chunk_id || ''
        }))
      );

      return {
        id: m.id,
        role: m.role,
        content: m.content,
        status,
        message_kind: m.message_kind,
        citations,
        timestamp: m.created_at || new Date().toISOString()
      };
    });

    return {
      appeal_id: data.appeal_id || appealId,
      items: attachEscalationEmailDrafts(mapped)
    };
  }
}

export const apiClient = new ApiClient();
