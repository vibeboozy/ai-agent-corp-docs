import { store } from '../state/store.js';
import { apiClient } from '../services/apiClient.js';
import { escapeHtml, formatTextWithLineBreaks, formatDateTime } from '../utils/dom.js';
import { toastSuccess, toastError } from '../utils/toast.js';

export class QualityTab {
  constructor(container) {
    this.container = container;
    this.unsubscribe = null;
  }

  async mount() {
    this.renderLayout();
    this.bindStaticEvents();

    this.unsubscribe = store.subscribe((newState, prevState) => {
      this.handleStateChange(newState, prevState);
    });

    // Первичная загрузка тикетов
    await this.loadTickets();
  }

  unmount() {
    if (this.unsubscribe) {
      this.unsubscribe();
      this.unsubscribe = null;
    }
  }

  renderLayout() {
    this.container.innerHTML = `
      <div class="quality-container">
        <!-- Верхняя панель инструментов -->
        <div class="quality-toolbar">
          <div class="quality-filters">
            <button type="button" class="filter-btn active" data-filter="all">
              <span>Все</span>
              <span id="filter-count-all" class="filter-count">0</span>
            </button>
            <button type="button" class="filter-btn" data-filter="open">
              <span>Ожидают ответа</span>
              <span id="filter-count-open" class="filter-count">0</span>
            </button>
            <button type="button" class="filter-btn" data-filter="resolved">
              <span>В базе знаний</span>
              <span id="filter-count-resolved" class="filter-count">0</span>
            </button>
          </div>

          <button id="refresh-tickets-btn" type="button" class="btn btn-secondary btn-sm" title="Обновить список тикетов">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
            </svg>
            <span>Обновить</span>
          </button>
        </div>

        <!-- Master-Detail раскладка -->
        <div class="quality-layout">
          <!-- Левая колонка: список тикетов -->
          <aside class="quality-sidebar">
            <div id="quality-ticket-list" class="ticket-list" role="list">
              <!-- Список карточек тикетов -->
            </div>
          </aside>

          <!-- Правая колонка: детальный просмотр и форма ответа -->
          <main class="quality-content">
            <div id="quality-detail-container" class="ticket-detail-view-wrapper">
              <!-- Детали тикета -->
            </div>
          </main>
        </div>
      </div>
    `;
  }

  bindStaticEvents() {
    // Переключение фильтров
    const filterBtns = this.container.querySelectorAll('.filter-btn');
    filterBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        const filter = btn.getAttribute('data-filter');
        filterBtns.forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');

        store.setState({ ticketFilter: filter });
      });
    });

    // Кнопка обновления
    const refreshBtn = this.container.querySelector('#refresh-tickets-btn');
    refreshBtn.addEventListener('click', async () => {
      refreshBtn.disabled = true;
      try {
        await this.loadTickets();
        toastSuccess('Список обращений обновлён');
      } catch (err) {
        toastError(err.message || 'Ошибка обновления списка');
      } finally {
        refreshBtn.disabled = false;
      }
    });
  }

  async loadTickets() {
    store.setState({ ticketsLoading: true });
    try {
      const tickets = await apiClient.getTickets();
      store.setState({ tickets, ticketsLoading: false });
    } catch (err) {
      store.setState({ ticketsLoading: false });
      toastError(err.message || 'Не удалось загрузить тикеты');
    }
  }

  handleStateChange(newState, prevState) {
    if (
      newState.tickets !== prevState.tickets ||
      newState.selectedTicketId !== prevState.selectedTicketId ||
      newState.ticketFilter !== prevState.ticketFilter
    ) {
      this.updateView(newState);
    }
  }

  updateView(state) {
    const { tickets, selectedTicketId, ticketFilter } = state;

    // Обновление счётчиков на кнопках фильтров
    const allCount = tickets.length;
    const openCount = tickets.filter((t) => t.status === 'open').length;
    const resolvedCount = tickets.filter((t) => t.status === 'resolved').length;

    const countAllEl = this.container.querySelector('#filter-count-all');
    const countOpenEl = this.container.querySelector('#filter-count-open');
    const countResolvedEl = this.container.querySelector('#filter-count-resolved');

    if (countAllEl) countAllEl.textContent = allCount;
    if (countOpenEl) countOpenEl.textContent = openCount;
    if (countResolvedEl) countResolvedEl.textContent = resolvedCount;

    // Фильтрация списка тикетов
    let filteredTickets = tickets;
    if (ticketFilter === 'open') {
      filteredTickets = tickets.filter((t) => t.status === 'open');
    } else if (ticketFilter === 'resolved') {
      filteredTickets = tickets.filter((t) => t.status === 'resolved');
    }

    // Автовыбор тикета, если ни один не выбран, но список не пуст
    let activeTicket = tickets.find((t) => t.ticket_id === selectedTicketId);
    if (!activeTicket && filteredTickets.length > 0) {
      activeTicket = filteredTickets[0];
      // Обновляем selectedTicketId без лишнего перерендера
      state.selectedTicketId = activeTicket.ticket_id;
    }

    this.renderTicketList(filteredTickets, activeTicket ? activeTicket.ticket_id : null);
    this.renderTicketDetail(activeTicket);
  }

  renderTicketList(tickets, selectedId) {
    const listContainer = this.container.querySelector('#quality-ticket-list');
    if (!listContainer) return;

    if (!tickets || tickets.length === 0) {
      listContainer.innerHTML = `
        <div class="ticket-empty-list">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <rect width="18" height="18" x="3" y="3" rx="2"/>
            <line x1="9" y1="9" x2="15" y2="9"/>
            <line x1="9" y1="13" x2="15" y2="13"/>
          </svg>
          <span>Запросов пока нет</span>
        </div>
      `;
      return;
    }

    listContainer.innerHTML = tickets.map((t) => {
      const isSelected = t.ticket_id === selectedId;
      const isOpen = t.status === 'open';

      return `
        <div
          class="ticket-card ${isSelected ? 'active' : ''}"
          data-ticket-id="${escapeHtml(t.ticket_id)}"
          role="button"
          tabindex="0"
        >
          <div class="ticket-card-header">
            <span class="ticket-id">${escapeHtml(t.ticket_id)}</span>
            <span class="badge ${isOpen ? 'badge-open' : 'badge-resolved'}">
              <span class="badge-dot"></span>
              ${isOpen ? 'Открыт' : 'В базе знаний'}
            </span>
          </div>
          <div class="ticket-card-title">${escapeHtml(t.question)}</div>
          <div class="ticket-card-footer">
            <span>${formatDateTime(t.created_at)}</span>
          </div>
        </div>
      `;
    }).join('');

    // Привязка кликов по карточкам
    const cards = listContainer.querySelectorAll('.ticket-card');
    cards.forEach((card) => {
      card.addEventListener('click', () => {
        const id = card.getAttribute('data-ticket-id');
        store.setState({ selectedTicketId: id });
      });
    });
  }

  renderTicketDetail(ticket) {
    const detailContainer = this.container.querySelector('#quality-detail-container');
    if (!detailContainer) return;

    if (!ticket) {
      detailContainer.innerHTML = `
        <div class="ticket-detail-placeholder">
          <div class="placeholder-icon">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>
          <p>Выберите обращение из списка слева для просмотра деталей</p>
        </div>
      `;
      return;
    }

    const isOpen = ticket.status === 'open';

    // Блок формы ответа (для открытых) или подтверждения (для закрытых)
    let actionBlockHtml = '';
    if (isOpen) {
      actionBlockHtml = `
        <form id="resolve-ticket-form" class="resolve-form-box">
          <div class="resolve-form-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 20h9"/>
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
            </svg>
            <span>Добавление решения в базу знаний Отдела качества</span>
          </div>

          <div class="form-group">
            <label for="resolve-answer-input">Эталонный ответ для сотрудника и базы знаний <span style="color: var(--color-danger)">*</span></label>
            <textarea
              id="resolve-answer-input"
              class="form-control resolve-textarea"
              placeholder="Например: При реорганизации юридического лица перенос лицензий допускается по официальному заявлению правопреемника с приложением выписки из ЕГРЮЛ и передаточного акта в течение 30 календарных дней..."
              required
            ></textarea>
            <span class="form-hint">Этот ответ агент будет возвращать при аналогичных вопросах сотрудников.</span>
          </div>

          <div class="form-group">
            <label for="resolve-ref-input">Привязка к регламенту / разделу <span style="color: var(--color-danger)">*</span></label>
            <input
              id="resolve-ref-input"
              type="text"
              class="form-control"
              placeholder="Например: Регламент корпоративного лицензирования, п. 5.4"
              required
            />
          </div>

          <div class="form-actions">
            <button id="resolve-submit-btn" type="submit" class="btn btn-success">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              <span>Сохранить ответ и пополнить базу знаний</span>
            </button>
          </div>
        </form>
      `;
    } else {
      actionBlockHtml = `
        <div class="resolved-info-box">
          <div class="resolved-badge-header">
            <div class="resolved-title">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
              <span>Добавлено в базу знаний агента</span>
            </div>
            <span class="ticket-detail-date">Обработано: ${formatDateTime(ticket.resolved_at)}</span>
          </div>

          <div class="ticket-section">
            <span class="ticket-section-title">Сохранённый эталонный ответ:</span>
            <div class="resolved-answer-text">${formatTextWithLineBreaks(ticket.answer)}</div>
          </div>

          <div class="resolved-regulation-row">
            <span>Официальный источник:</span>
            <span class="resolved-ref-badge">${escapeHtml(ticket.regulation_ref || 'Регламент')}</span>
          </div>
        </div>
      `;
    }

    detailContainer.innerHTML = `
      <div class="ticket-detail-view">
        <!-- Шапка тикета -->
        <div class="ticket-detail-header">
          <div class="ticket-detail-title-group">
            <span class="ticket-detail-id">${escapeHtml(ticket.ticket_id)}</span>
            <span class="ticket-detail-date">Создан: ${formatDateTime(ticket.created_at)}</span>
          </div>
          <span class="badge ${isOpen ? 'badge-open' : 'badge-resolved'}">
            <span class="badge-dot"></span>
            ${isOpen ? 'Ожидает ответа' : 'В базе знаний'}
          </span>
        </div>

        <!-- Вопрос сотрудника -->
        <div class="ticket-section">
          <span class="ticket-section-title">Вопрос сотрудника:</span>
          <div class="ticket-question-text">${formatTextWithLineBreaks(ticket.question)}</div>
        </div>

        <!-- Контекст и сформированное письмо -->
        <details class="ticket-context-accordion">
          <summary class="ticket-context-summary">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect width="20" height="16" x="2" y="4" rx="2"/>
              <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>
            </svg>
            <span>Сформированное письмо и контекст диалога</span>
          </summary>
          <div class="ticket-context-body">
            <div class="context-row">
              <span class="context-label">Кому:</span>
              <div class="context-val">${escapeHtml(ticket.email_to || 'quality@company.ru')}</div>
            </div>
            <div class="context-row">
              <span class="context-label">Тема:</span>
              <div class="context-val">${escapeHtml(ticket.email_subject || 'Без темы')}</div>
            </div>
            <div class="context-row">
              <span class="context-label">Текст сформированного письма:</span>
              <div class="context-val">${formatTextWithLineBreaks(ticket.email_body || '')}</div>
            </div>
            ${ticket.context ? `
              <div class="context-row">
                <span class="context-label">Контекст обращения:</span>
                <div class="context-val">${formatTextWithLineBreaks(ticket.context)}</div>
              </div>
            ` : ''}
          </div>
        </details>

        <!-- Блок добавления ответа или результат -->
        ${actionBlockHtml}
      </div>
    `;

    // Привязка формы разрешения тикета
    if (isOpen) {
      const resolveForm = detailContainer.querySelector('#resolve-ticket-form');
      const submitBtn = detailContainer.querySelector('#resolve-submit-btn');
      const answerInput = detailContainer.querySelector('#resolve-answer-input');
      const refInput = detailContainer.querySelector('#resolve-ref-input');

      resolveForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const answer = answerInput.value.trim();
        const regulation_ref = refInput.value.trim();

        if (!answer || !regulation_ref) {
          toastError('Пожалуйста, заполните эталонный ответ и ссылку на регламент');
          return;
        }

        submitBtn.disabled = true;
        submitBtn.innerHTML = `<span>Сохранение...</span>`;

        try {
          const updatedTicket = await apiClient.resolveTicket(ticket.ticket_id, {
            answer,
            regulation_ref
          });

          // Обновляем список тикетов в хранилище
          const currentTickets = store.getState().tickets;
          const updatedList = currentTickets.map((t) => {
            if (t.ticket_id === ticket.ticket_id) {
              return {
                ...t,
                status: 'resolved',
                answer,
                regulation_ref,
                resolved_at: updatedTicket.resolved_at || new Date().toISOString()
              };
            }
            return t;
          });

          store.setState({
            tickets: updatedList,
            selectedTicketId: ticket.ticket_id
          });

          toastSuccess('Ответ сохранён. База знаний агента пополнена!');
        } catch (err) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = `<span>Сохранить ответ и пополнить базу знаний</span>`;
          toastError(err.message || 'Ошибка сохранения ответа');
        }
      });
    }
  }
}
