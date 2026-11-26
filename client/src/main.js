import { store } from './state/store.js';
import { apiClient } from './services/apiClient.js';
import { mockService } from './services/mockService.js';
import { ChatTab } from './modules/chatTab.js';
import { QualityTab } from './modules/qualityTab.js';
import { AnalyticsTab } from './modules/analyticsTab.js';
import { toastSuccess, toastInfo } from './utils/toast.js';

class App {
  constructor() {
    this.chatTab = null;
    this.qualityTab = null;
    this.analyticsTab = null;
  }

  async init() {
    this.initTabs();
    this.initHeaderControls();
    this.initSettingsPopover();
    this.subscribeToStore();

    // Загрузка начального списка тикетов для синхронизации бейджа
    try {
      const tickets = await apiClient.getTickets();
      store.setState({ tickets });
    } catch (err) {
      console.warn('Не удалось загрузить начальные тикеты:', err);
    }
  }

  initTabs() {
    const chatContainer = document.getElementById('tab-chat');
    const qualityContainer = document.getElementById('tab-quality');
    const analyticsContainer = document.getElementById('tab-analytics');

    this.chatTab = new ChatTab(chatContainer);
    this.qualityTab = new QualityTab(qualityContainer);
    this.analyticsTab = new AnalyticsTab(analyticsContainer);

    // Монтируем вкладки
    this.chatTab.mount();
    this.qualityTab.mount();
    this.analyticsTab.mount();

    // Обработчики кликов по табам в шапке
    const navButtons = document.querySelectorAll('.nav-tab');
    navButtons.forEach((btn) => {
      btn.addEventListener('click', () => {
        const targetTab = btn.getAttribute('data-tab');
        if (targetTab) {
          store.setState({ activeTab: targetTab });
        }
      });
    });
  }

  initHeaderControls() {
    const mockBtn = document.getElementById('mode-mock-btn');
    const apiBtn = document.getElementById('mode-api-btn');

    const updateModeButtons = (mode) => {
      if (mode === 'mock') {
        mockBtn.classList.add('active');
        mockBtn.setAttribute('aria-checked', 'true');
        apiBtn.classList.remove('active');
        apiBtn.setAttribute('aria-checked', 'false');
      } else {
        apiBtn.classList.add('active');
        apiBtn.setAttribute('aria-checked', 'true');
        mockBtn.classList.remove('active');
        mockBtn.setAttribute('aria-checked', 'false');
      }
    };

    // Начальное состояние
    updateModeButtons(store.getState().mode);

    mockBtn.addEventListener('click', () => {
      if (store.getState().mode !== 'mock') {
        store.setState({ mode: 'mock' });
        updateModeButtons('mock');
        toastInfo('Режим переключен: Mock (автономная эмуляция)');
      }
    });

    apiBtn.addEventListener('click', () => {
      if (store.getState().mode !== 'api') {
        store.setState({ mode: 'api' });
        updateModeButtons('api');
        toastInfo(`Режим переключен: Real API (${store.getState().apiBaseUrl})`);
      }
    });
  }

  initSettingsPopover() {
    const toggleBtn = document.getElementById('settings-toggle-btn');
    const popover = document.getElementById('settings-popover');
    const closeBtn = document.getElementById('settings-close-btn');
    const apiUrlInput = document.getElementById('api-base-url-input');
    const saveUrlBtn = document.getElementById('save-api-url-btn');
    const resetDemoBtn = document.getElementById('reset-demo-btn');

    // Начальное значение
    if (apiUrlInput) {
      apiUrlInput.value = store.getState().apiBaseUrl;
    }

    const openPopover = () => {
      popover.classList.remove('hidden');
      toggleBtn.setAttribute('aria-expanded', 'true');
      if (apiUrlInput) apiUrlInput.value = store.getState().apiBaseUrl;
    };

    const closePopover = () => {
      popover.classList.add('hidden');
      toggleBtn.setAttribute('aria-expanded', 'false');
    };

    toggleBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isHidden = popover.classList.contains('hidden');
      if (isHidden) openPopover();
      else closePopover();
    });

    closeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      closePopover();
    });

    // Закрытие при клике вне поповера
    document.addEventListener('click', (e) => {
      if (!popover.contains(e.target) && !toggleBtn.contains(e.target)) {
        closePopover();
      }
    });

    // Сохранение API URL
    saveUrlBtn.addEventListener('click', () => {
      const val = apiUrlInput.value.trim() || '/api';
      store.setState({ apiBaseUrl: val });
      toastSuccess(`API Base URL сохранён: ${val}`);
      closePopover();
    });

    // Сброс демо-данных
    resetDemoBtn.addEventListener('click', async () => {
      const freshTickets = mockService.resetDemoData();
      store.startNewChat();
      store.setState({
        tickets: freshTickets,
        selectedTicketId: null
      });
      toastSuccess('Демо-данные успешно сброшены');
      closePopover();
    });
  }

  subscribeToStore() {
    store.subscribe((state, prevState) => {
      // 1. Переключение активной вкладки
      if (state.activeTab !== prevState.activeTab) {
        this.switchActiveTab(state.activeTab);
      }

      // 2. Обновление бейджа открытых тикетов в шапке
      if (state.tickets !== prevState.tickets) {
        this.updateTicketBadge(state.tickets);
      }
    });

    // Начальная синхронизация таба и бейджа
    const current = store.getState();
    this.switchActiveTab(current.activeTab);
    this.updateTicketBadge(current.tickets);
  }

  switchActiveTab(tabName) {
    const chatBtn = document.getElementById('tab-btn-chat');
    const qualityBtn = document.getElementById('tab-btn-quality');
    const chatPane = document.getElementById('tab-chat');
    const qualityPane = document.getElementById('tab-quality');
    const analyticsPane = document.getElementById('tab-analytics');

    chatBtn.classList.toggle('active', tabName === 'chat');
    qualityBtn.classList.toggle('active', tabName === 'quality');

    chatPane.classList.toggle('hidden', tabName !== 'chat');
    qualityPane.classList.toggle('hidden', tabName !== 'quality');
    analyticsPane.classList.toggle('hidden', tabName !== 'analytics');
  }

  updateTicketBadge(tickets) {
    const badge = document.getElementById('header-ticket-badge');
    if (!badge) return;

    const openCount = tickets.filter((t) => t.status === 'open').length;
    if (openCount > 0) {
      badge.textContent = String(openCount);
      badge.classList.remove('hidden');
    } else {
      badge.textContent = '0';
      badge.classList.add('hidden');
    }
  }
}

// Запуск приложения после готовности DOM
document.addEventListener('DOMContentLoaded', () => {
  const app = new App();
  app.init();
});
