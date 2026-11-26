import { store } from '../state/store.js';
import { apiClient } from '../services/apiClient.js';
import { DEMO_PROMPTS } from '../config.js';
import { escapeHtml, formatTextWithLineBreaks, formatTimeShort, formatSessionDate, autoResizeTextarea } from '../utils/dom.js';
import { toastSuccess, toastError, toastInfo } from '../utils/toast.js';

export class ChatTab {
  constructor(container) {
    this.container = container;
    this.unsubscribe = null;
    this.renderedMessagesCount = 0;
  }

  mount() {
    this.renderLayout();
    this.bindEvents();
    this.renderState(store.getState());

    this.unsubscribe = store.subscribe((newState, prevState) => {
      this.handleStateChange(newState, prevState);
    });
  }

  unmount() {
    if (this.unsubscribe) {
      this.unsubscribe();
      this.unsubscribe = null;
    }
  }

  renderLayout() {
    this.container.innerHTML = `
      <div class="chat-page-layout">
        <!-- Боковая панель истории диалогов -->
        <aside id="chat-history-sidebar" class="chat-history-sidebar">
          <div class="history-sidebar-header">
            <button id="chat-new-dialog-btn" type="button" class="btn btn-primary btn-sm history-new-btn" title="Начать новый диалог">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"/>
                <line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              <span>Новый диалог</span>
            </button>
            <button id="chat-sidebar-close-btn" type="button" class="btn-icon mobile-only" title="Закрыть историю">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>

          <div class="history-sidebar-section-title">История запросов</div>

          <div id="chat-history-list" class="history-sessions-list" role="list">
            <!-- Список сессий рендерится динамически -->
          </div>
        </aside>

        <!-- Мобильная подложка (backdrop) для сайдбара -->
        <div id="chat-sidebar-backdrop" class="sidebar-backdrop mobile-only"></div>

        <!-- Основная область чата -->
        <div class="chat-container">
          <!-- Шапка чата -->
          <div class="chat-header">
            <div class="chat-header-info">
              <button id="chat-sidebar-toggle-btn" type="button" class="btn-icon mobile-only history-toggle-btn" title="История диалогов">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="3" y1="12" x2="21" y2="12"/>
                  <line x1="3" y1="6" x2="21" y2="6"/>
                  <line x1="3" y1="18" x2="21" y2="18"/>
                </svg>
              </button>
              <button id="chat-mobile-new-btn" type="button" class="btn-icon mobile-only mobile-new-chat-btn" title="Новый диалог">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="12" y1="5" x2="12" y2="19"/>
                  <line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
              </button>
              <span class="chat-header-title">Консультация по регламентам</span>
              <span id="chat-session-badge" class="chat-session-badge" title="ID текущей сессии диалога"></span>
            </div>
          </div>

          <!-- Лента сообщений -->
          <div id="chat-feed" class="chat-feed" role="log" aria-live="polite">
            <!-- Сообщения рендерятся динамически -->
          </div>

          <!-- Нижняя панель ввода -->
          <div class="chat-input-bar">
            <form id="chat-form" class="chat-input-box">
              <textarea
                id="chat-textarea"
                class="chat-textarea"
                placeholder="Задайте вопрос по регламентам..."
                rows="1"
              ></textarea>
              <button
                id="chat-send-btn"
                type="submit"
                class="chat-send-btn"
                title="Отправить сообщение (Enter)"
                disabled
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13"/>
                  <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                </svg>
              </button>
            </form>
            <div class="chat-input-hints">
              <span>Нажмите <strong>Enter</strong> для отправки, <strong>Shift + Enter</strong> - перенос строки</span>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  bindEvents() {
    const textarea = this.container.querySelector('#chat-textarea');
    const sendBtn = this.container.querySelector('#chat-send-btn');
    const form = this.container.querySelector('#chat-form');
    const newDialogBtn = this.container.querySelector('#chat-new-dialog-btn');

    // Автоувеличение высоты textarea и управление активностью кнопки
    textarea.addEventListener('input', () => {
      autoResizeTextarea(textarea, 120);
      const hasText = textarea.value.trim().length > 0;
      const isLoading = store.getState().chatLoading;
      sendBtn.disabled = !hasText || isLoading;
    });

    // Обработка Enter / Shift+Enter
    textarea.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!sendBtn.disabled) {
          form.dispatchEvent(new Event('submit', { cancelable: true }));
        }
      }
    });

    // Отправка формы
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const question = textarea.value.trim();
      if (!question || store.getState().chatLoading) return;

      textarea.value = '';
      autoResizeTextarea(textarea, 120);
      sendBtn.disabled = true;

      this.handleUserSendMessage(question);
    });

    // Кнопка нового диалога в сайдбаре
    const startNewChatHandler = () => {
      store.startNewChat();
      toastInfo('Начат новый диалог.');
      this.closeMobileSidebar();
      setTimeout(() => textarea.focus(), 50);
    };

    if (newDialogBtn) {
      newDialogBtn.addEventListener('click', startNewChatHandler);
    }

    const mobileNewBtn = this.container.querySelector('#chat-mobile-new-btn');
    if (mobileNewBtn) {
      mobileNewBtn.addEventListener('click', startNewChatHandler);
    }

    // Мобильное открытие/закрытие сайдбара истории
    const sidebarToggleBtn = this.container.querySelector('#chat-sidebar-toggle-btn');
    const sidebarCloseBtn = this.container.querySelector('#chat-sidebar-close-btn');
    const sidebarBackdrop = this.container.querySelector('#chat-sidebar-backdrop');

    if (sidebarToggleBtn) {
      sidebarToggleBtn.addEventListener('click', () => {
        this.openMobileSidebar();
      });
    }

    if (sidebarCloseBtn) {
      sidebarCloseBtn.addEventListener('click', () => {
        this.closeMobileSidebar();
      });
    }

    if (sidebarBackdrop) {
      sidebarBackdrop.addEventListener('click', () => {
        this.closeMobileSidebar();
      });
    }
  }

  openMobileSidebar() {
    const sidebar = this.container.querySelector('#chat-history-sidebar');
    const backdrop = this.container.querySelector('#chat-sidebar-backdrop');
    if (sidebar) sidebar.classList.add('mobile-open');
    if (backdrop) backdrop.classList.add('mobile-open');
  }

  closeMobileSidebar() {
    const sidebar = this.container.querySelector('#chat-history-sidebar');
    const backdrop = this.container.querySelector('#chat-sidebar-backdrop');
    if (sidebar) sidebar.classList.remove('mobile-open');
    if (backdrop) backdrop.classList.remove('mobile-open');
  }

  handleStateChange(newState, prevState) {
    // Обновление сессионного бейджа
    const sessionBadge = this.container.querySelector('#chat-session-badge');
    if (sessionBadge && newState.sessionId) {
      sessionBadge.textContent = `Сессия: ${newState.sessionId.slice(0, 8)}`;
    }

    // Обновление истории запросов при изменении списка сессий или активной сессии
    if (
      newState.sessions !== prevState.sessions ||
      newState.sessionId !== prevState.sessionId
    ) {
      this.renderSessionsHistory(newState.sessions, newState.sessionId);
    }

    // Блокировка ввода во время загрузки
    const textarea = this.container.querySelector('#chat-textarea');
    const sendBtn = this.container.querySelector('#chat-send-btn');
    if (textarea && sendBtn) {
      if (newState.chatLoading) {
        textarea.disabled = true;
        sendBtn.disabled = true;
      } else {
        textarea.disabled = false;
        sendBtn.disabled = textarea.value.trim().length === 0;
      }
    }

    // Если изменился список сообщений или состояние загрузки - обновляем ленту
    if (
      newState.chatMessages !== prevState.chatMessages ||
      newState.chatLoading !== prevState.chatLoading
    ) {
      this.renderMessages(newState.chatMessages, newState.chatLoading);
    }
  }

  renderState(state) {
    const sessionBadge = this.container.querySelector('#chat-session-badge');
    if (sessionBadge && state.sessionId) {
      sessionBadge.textContent = `Сессия: ${state.sessionId.slice(0, 8)}`;
    }
    this.renderSessionsHistory(state.sessions, state.sessionId);
    this.renderMessages(state.chatMessages, state.chatLoading);
  }

  /**
   * Отрисовка списка сессий в боковой панели истории запросов
   */
  renderSessionsHistory(sessions, currentSessionId) {
    const list = this.container.querySelector('#chat-history-list');
    if (!list) return;

    if (!sessions || sessions.length === 0) {
      list.innerHTML = `
        <div class="history-empty-placeholder">
          <span>История запросов пуста.<br>Задайте вопрос, чтобы начать.</span>
        </div>
      `;
      return;
    }

    list.innerHTML = sessions.map((s) => {
      const isActive = s.session_id === currentSessionId;
      const title = s.title || 'Новый диалог';
      const timeStr = formatSessionDate(s.updated_at || s.created_at);
      const count = (s.messages || []).length;

      return `
        <button
          type="button"
          class="history-session-item ${isActive ? 'active' : ''}"
          data-session-id="${escapeHtml(s.session_id)}"
          title="${escapeHtml(title)}"
        >
          <div class="history-session-title">${escapeHtml(title)}</div>
          <div class="history-session-meta">
            <span>${escapeHtml(timeStr)}</span>
            <span>${count} сообщ.</span>
          </div>
        </button>
      `;
    }).join('');

    // Привязка кликов для переключения между сессиями (без кнопки удаления)
    const items = list.querySelectorAll('.history-session-item');
    items.forEach((item) => {
      item.addEventListener('click', () => {
        const sid = item.getAttribute('data-session-id');
        if (sid && sid !== store.getState().sessionId) {
          store.switchSession(sid);
        }
        this.closeMobileSidebar();
      });
    });
  }

  /**
   * Отрисовка списка сообщений или пустого экрана с демо-чипсами
   */
  renderMessages(messages, isLoading) {
    const feed = this.container.querySelector('#chat-feed');
    if (!feed) return;

    if (!messages || messages.length === 0) {
      feed.innerHTML = this.renderEmptyStateHtml();
      this.bindChipsEvents();
      return;
    }

    let html = '';
    messages.forEach((msg) => {
      if (msg.role === 'user') {
        html += this.renderUserMessageHtml(msg);
      } else {
        html += this.renderAssistantMessageHtml(msg);
      }
    });

    if (isLoading) {
      html += this.renderLoadingIndicatorHtml();
    }

    feed.innerHTML = html;
    this.bindMessageDynamicActions();
    this.scrollToBottom();
  }

  renderEmptyStateHtml() {
    return `
      <div class="chat-empty-state">
        <div class="empty-state-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2a10 10 0 0 1 10 10c0 5.523-4.477 10-10 10a10 10 0 0 1-10-10C2 6.477 6.477 2 12 2z"/>
            <path d="m9 12 2 2 4-4"/>
          </svg>
        </div>
        <h2 class="empty-state-title">ИИ-кузница: Поиск ответов по регламентам</h2>
        <p class="empty-state-desc">
          Консультации строго по корпоративным регламентам Софтлайн (Служба качества).
          Выберите сценарий для быстрой демонстрации ключевых бизнес-кейсов:
        </p>

        <div class="prompt-chips-title">Быстрые сценарии для проверки:</div>
        <div class="prompt-chips-list">
          ${DEMO_PROMPTS.map((p) => `
            <button type="button" class="prompt-chip" data-prompt-id="${p.id}" data-text="${escapeHtml(p.text)}">
              <div class="chip-content">
                <span class="chip-text">«${escapeHtml(p.text)}»</span>
                <span class="chip-case">${escapeHtml(p.badge)}: ${escapeHtml(p.subtitle)}</span>
              </div>
              <span class="chip-arrow">→</span>
            </button>
          `).join('')}
        </div>
      </div>
    `;
  }

  bindChipsEvents() {
    const chips = this.container.querySelectorAll('.prompt-chip');
    chips.forEach((chip) => {
      chip.addEventListener('click', () => {
        const text = chip.getAttribute('data-text');
        if (text) {
          this.handleUserSendMessage(text);
        }
      });
    });
  }

  renderUserMessageHtml(msg) {
    return `
      <div class="message-row message-user" id="msg-${msg.id}">
        <div class="message-content">
          <div class="message-bubble">${formatTextWithLineBreaks(msg.content)}</div>
          <span class="message-meta">${formatTimeShort(msg.timestamp)}</span>
        </div>
        <div class="message-avatar avatar-user" title="Сотрудник">Я</div>
      </div>
    `;
  }

  renderAssistantMessageHtml(msg) {
    let statusBadgeHtml = '';
    if (msg.status === 'answer') {
      statusBadgeHtml = `
        <div class="agent-status-header">
          <span class="badge badge-answer">
            <span class="badge-dot"></span>
            Подтверждено регламентом
          </span>
        </div>
      `;
    } else if (msg.status === 'clarify') {
      statusBadgeHtml = `
        <div class="agent-status-header">
          <span class="badge badge-clarify">
            <span class="badge-dot"></span>
            Требуется уточнение
          </span>
        </div>
      `;
    } else if (msg.status === 'refusal') {
      statusBadgeHtml = `
        <div class="agent-status-header">
          <span class="badge badge-escalate">
            <span class="badge-dot"></span>
            Вне компетенции регламентов
          </span>
        </div>
      `;
    } else if (msg.status === 'escalate') {
      statusBadgeHtml = `
        <div class="agent-status-header">
          <span class="badge badge-escalate">
            <span class="badge-dot"></span>
            Нет в регламентах • Эскалация
          </span>
        </div>
      `;
    }

    // Блок цитат
    let citationsHtml = '';
    if (msg.citations && msg.citations.length > 0) {
      citationsHtml = `
        <details class="citations-card" open>
          <summary class="citations-summary">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/>
              <path d="M6 6h10"/>
              <path d="M6 10h10"/>
            </svg>
            Источники и цитаты (${msg.citations.length})
          </summary>
          <div class="citations-list">
            ${msg.citations.map((c) => `
              <div class="citation-item">
                <div class="citation-meta">
                  <span>${escapeHtml(c.doc_name || 'Корпоративный регламент')}</span>
                  ${c.section ? `• <span>${escapeHtml(c.section)}</span>` : ''}
                </div>
                <blockquote class="citation-quote">${formatTextWithLineBreaks(c.quote || '')}</blockquote>
              </div>
            `).join('')}
          </div>
        </details>
      `;
    }

    // Карточка превью письма при эскалации (Кейс 3)
    let emailDraftHtml = '';
    if (msg.status === 'escalate') {
      if (msg.ticketCreated) {
        emailDraftHtml = `
          <div class="email-sent-card">
            <div class="email-sent-text">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
              <span>Запрос <strong>№${escapeHtml(msg.ticketId || '')}</strong> создан и отправлен в Службу качества</span>
            </div>
            <button
              type="button"
              class="btn-open-ticket"
              data-ticket-id="${escapeHtml(msg.ticketId || '')}"
            >
              Открыть в Кабинете СК →
            </button>
          </div>
        `;
      } else if (msg.email_draft) {
        const draft = msg.email_draft;
        emailDraftHtml = `
          <div class="email-draft-card" data-msg-id="${msg.id}">
            <div class="email-draft-header">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect width="20" height="16" x="2" y="4" rx="2"/>
                <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>
              </svg>
              <span>Превью запроса в Службу качества</span>
            </div>

            <div class="email-field-row">
              <span class="email-field-label">Кому:</span>
              <input type="text" class="email-field-input readonly" value="${escapeHtml(draft.to || 'quality@company.ru')}" readonly />
            </div>

            <div class="email-field-row">
              <span class="email-field-label">Тема обращения:</span>
              <input type="text" class="email-field-input input-email-subject" value="${escapeHtml(draft.subject || '')}" />
            </div>

            <div class="email-field-row">
              <span class="email-field-label">Текст обращения (можно дополнить):</span>
              <textarea class="email-field-textarea input-email-body">${escapeHtml(draft.body || '')}</textarea>
            </div>

            <div class="email-actions">
              <button type="button" class="btn btn-primary btn-sm btn-submit-ticket">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13"/>
                  <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                </svg>
                <span>Отправить в Службу качества</span>
              </button>
            </div>
          </div>
        `;
      }
    }

    return `
      <div class="message-row message-assistant" id="msg-${msg.id}">
        <div class="message-avatar avatar-assistant" title="Агент Отдела качества">AI</div>
        <div class="message-content">
          <div class="message-bubble">
            ${statusBadgeHtml}
            <div class="message-text">${formatTextWithLineBreaks(msg.content)}</div>
            ${citationsHtml}
            ${emailDraftHtml}
          </div>
          <span class="message-meta">${formatTimeShort(msg.timestamp)}</span>
        </div>
      </div>
    `;
  }

  renderLoadingIndicatorHtml() {
    return `
      <div class="message-row message-assistant chat-loading-row">
        <div class="message-avatar avatar-assistant">AI</div>
        <div class="message-content">
          <div class="chat-typing-indicator">
            <span>Ищу ответ в регламентах</span>
            <div class="typing-dots">
              <div class="typing-dot"></div>
              <div class="typing-dot"></div>
              <div class="typing-dot"></div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  bindMessageDynamicActions() {
    // 1. Кнопка «Отправить в Службу качества»
    const sendTicketBtns = this.container.querySelectorAll('.btn-submit-ticket');
    sendTicketBtns.forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        const card = e.target.closest('.email-draft-card');
        if (!card) return;

        const msgId = card.getAttribute('data-msg-id');
        const subjectInput = card.querySelector('.input-email-subject');
        const bodyInput = card.querySelector('.input-email-body');

        const subject = subjectInput ? subjectInput.value.trim() : '';
        const body = bodyInput ? bodyInput.value.trim() : '';

        const state = store.getState();
        const msg = state.chatMessages.find((m) => String(m.id) === String(msgId));
        if (!msg) return;

        // Поиск предшествующего вопроса пользователя
        const msgIndex = state.chatMessages.indexOf(msg);
        let userQuestion = '';
        for (let i = msgIndex - 1; i >= 0; i--) {
          if (state.chatMessages[i].role === 'user') {
            userQuestion = state.chatMessages[i].content;
            break;
          }
        }

        btn.disabled = true;
        btn.innerHTML = `<span>Отправка...</span>`;

        try {
          const result = await apiClient.createTicket({
            question: userQuestion || subject,
            email_draft: {
              to: msg.email_draft?.to || 'quality@company.ru',
              subject,
              body
            },
            session_id: state.sessionId,
            context: `Диалог в сессии ${state.sessionId}`
          });

          const ticketId = result.ticket_id || result.id || 'SQ-101';

          // Обновляем сообщение в хранилище и сохраняем сессию
          const updatedMessages = state.chatMessages.map((m) => {
            if (String(m.id) === String(msgId)) {
              return {
                ...m,
                ticketCreated: true,
                ticketId
              };
            }
            return m;
          });

          store.saveActiveSessionMessages(updatedMessages);

          // Обновляем список тикетов в store
          const updatedTickets = await apiClient.getTickets();
          store.setState({
            tickets: updatedTickets
          });

          toastSuccess(`Запрос №${ticketId} отправлен в Службу качества!`);
        } catch (err) {
          btn.disabled = false;
          btn.innerHTML = `<span>Отправить в Службу качества</span>`;
          toastError(err.message || 'Ошибка отправки тикета');
        }
      });
    });

    // 2. Кнопка «Открыть в Кабинете СК →»
    const openTicketBtns = this.container.querySelectorAll('.btn-open-ticket');
    openTicketBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        const ticketId = btn.getAttribute('data-ticket-id');
        store.setState({
          activeTab: 'quality',
          selectedTicketId: ticketId
        });
      });
    });
  }

  async handleUserSendMessage(question) {
    const state = store.getState();
    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: question,
      timestamp: new Date().toISOString()
    };

    const newMessages = [...state.chatMessages, userMsg];

    // Формируем историю для API
    const historyPayload = state.chatMessages.map((m) => ({
      role: m.role,
      content: m.content
    }));

    store.saveActiveSessionMessages(newMessages);
    store.setState({
      chatLoading: true
    });

    try {
      const response = await apiClient.sendChatMessage({
        question,
        session_id: state.sessionId,
        history: historyPayload
      });

      const assistantMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.reply || 'Ответ сформирован.',
        status: response.status || 'answer',
        citations: response.citations || [],
        email_draft: response.email_draft || null,
        ticketCreated: false,
        ticketId: null,
        timestamp: new Date().toISOString()
      };

      store.saveActiveSessionMessages([...newMessages, assistantMsg]);
      store.setState({
        chatLoading: false
      });
    } catch (err) {
      store.setState({ chatLoading: false });
      toastError(err.message || 'Не удалось получить ответ от ассистента');
    }
  }

  scrollToBottom() {
    const feed = this.container.querySelector('#chat-feed');
    if (feed) {
      requestAnimationFrame(() => {
        feed.scrollTop = feed.scrollHeight;
      });
    }
  }
}
