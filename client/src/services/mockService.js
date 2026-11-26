import { CONFIG } from '../config.js';

// Задержка сети для реалистичной симуляции
function delay(ms = 500) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Начальный демо-набор тикетов
const INITIAL_SEED_TICKETS = [
  {
    ticket_id: 'SQ-100',
    question: 'Как согласовать скидку свыше 15% для крупного корпоративного клиента?',
    status: 'resolved',
    email_to: 'quality@company.ru',
    email_subject: 'Запрос согласования скидки свыше 15%',
    email_body: 'Здравствуйте!\n\nПрошу дать разъяснение по согласованию условий нестандартной корпоративной скидки свыше 15%.\n\nКонтекст: Переговоры с ключевым клиентом.\n\nС уважением,\nОтдел продаж',
    session_id: 'demo-seed-session-100',
    context: 'Вопрос возник при оформлении договора на 50 рабочих мест.',
    created_at: new Date(Date.now() - 86400000 * 2).toISOString(),
    answer: 'Предоставление скидки свыше 15% допускается только по письменному согласованию с коммерческим директором через служебную записку в СЭД с приложением расчёта маржинальности сделки.',
    regulation_ref: 'Регламент ценообразования и корпоративных скидок, п. 3.2',
    resolved_at: new Date(Date.now() - 86400000).toISOString()
  }
];

class MockService {
  /**
   * Получение всех тикетов из localStorage
   * @returns {Array}
   */
  getStoredTickets() {
    try {
      const raw = localStorage.getItem(CONFIG.STORAGE_KEYS.TICKETS);
      if (raw) {
        return JSON.parse(raw);
      }
    } catch (e) {
      console.warn('Ошибка чтения тикетов из localStorage:', e);
    }
    // Если пусто - инициализируем сидовыми данными
    this.saveStoredTickets(INITIAL_SEED_TICKETS);
    return [...INITIAL_SEED_TICKETS];
  }

  /**
   * Сохранение тикетов в localStorage
   * @param {Array} tickets 
   */
  saveStoredTickets(tickets) {
    try {
      localStorage.setItem(CONFIG.STORAGE_KEYS.TICKETS, JSON.stringify(tickets));
    } catch (e) {
      console.error('Ошибка записи тикетов в localStorage:', e);
    }
  }

  /**
   * Сброс мок-данных к начальному состоянию
   */
  resetDemoData() {
    this.saveStoredTickets(INITIAL_SEED_TICKETS);
    localStorage.removeItem(CONFIG.STORAGE_KEYS.CHAT_HISTORY);
    return [...INITIAL_SEED_TICKETS];
  }

  /**
   * Генерация очередного ID тикета (SQ-101, SQ-102 и т.д.)
   */
  generateNextTicketId(tickets) {
    let maxNum = 100;
    tickets.forEach((t) => {
      const match = t.ticket_id && t.ticket_id.match(/SQ-(\d+)/);
      if (match) {
        const num = parseInt(match[1], 10);
        if (num > maxNum) maxNum = num;
      }
    });
    return `SQ-${maxNum + 1}`;
  }

  /**
   * Проверка совпадения вопроса с закрытыми тикетами (дообученная БЗ)
   */
  findResolvedTicketMatch(question, tickets) {
    const resolvedTickets = tickets.filter((t) => t.status === 'resolved' && t.answer);
    const qLower = question.toLowerCase();

    // 1. Проверка прямых корней для кейса 3 (перенос лицензии на другое юрлицо)
    const hasReorgRoots = (qLower.includes('перенес') || qLower.includes('перенос')) &&
                          (qLower.includes('реорганизац') || qLower.includes('юрлиц'));

    for (const ticket of resolvedTickets) {
      const tLower = ticket.question.toLowerCase();

      if (hasReorgRoots && (tLower.includes('перенес') || tLower.includes('реорганизац') || tLower.includes('юрлиц'))) {
        return ticket;
      }

      // 2. Сравнение по значимым словам >= 4 символов
      const qWords = qLower.match(/[а-яa-z0-9]{4,}/g) || [];
      const tWords = new Set(tLower.match(/[а-яa-z0-9]{4,}/g) || []);

      let matches = 0;
      for (const w of qWords) {
        if (tWords.has(w)) matches++;
      }

      if (matches >= 2) {
        return ticket;
      }
    }

    return null;
  }

  /**
   * Симуляция отправки сообщения в чат (POST /chat)
   * @param {{ question: string, session_id: string, history: Array }} payload
   */
  async sendChatMessage({ question, session_id, history = [] }) {
    await delay(450 + Math.random() * 250);

    const tickets = this.getStoredTickets();
    const qTrimmed = (question || '').trim();
    const qLower = qTrimmed.toLowerCase();

    // 1. ПРОВЕРКА ДООБУЧЕННОЙ БАЗЫ ЗНАНИЙ (Кейс 3 после добавления ответа в Кабинете СК)
    const matchedTicket = this.findResolvedTicketMatch(qTrimmed, tickets);
    if (matchedTicket) {
      return {
        status: 'answer',
        reply: matchedTicket.answer,
        citations: [
          {
            doc_name: matchedTicket.regulation_ref || 'База знаний Службы качества',
            section: `Подтверждено Службой качества (${matchedTicket.ticket_id})`,
            quote: matchedTicket.answer
          }
        ],
        email_draft: null
      };
    }

    // 1.1. ПРОВЕРКА UC-04: Отказ от вопроса не по регламенту (FR-07, шаблон AG-001)
    const isOffTopic = qLower.includes('погода') ||
      qLower.includes('стих') ||
      qLower.includes('анекдот') ||
      qLower.includes('рецепт') ||
      qLower.includes('курс валют') ||
      qLower.includes('гороскоп') ||
      qLower.includes('котиков');

    if (isOffTopic) {
      return {
        status: 'refusal',
        reply: 'Данный вопрос не относится к регламентам и базе знаний.\n\nРекомендация: обратитесь в службу качества.',
        citations: [],
        email_draft: null
      };
    }

    // 2. КЕЙС 1: Прямой ответ по регламенту (возврат лицензии ИЛИ подписание договоров на закупку)
    if (
      (qLower.includes('вернуть') || qLower.includes('возврат')) &&
      qLower.includes('активац')
    ) {
      return {
        status: 'answer',
        reply: 'После успешной активации лицензионного ключа возврат денежных средств и обмен лицензии не производятся. Активированный электронный ключ признаётся использованным цифровым продуктом надлежащего качества и повторной перепродаже или отмене не подлежит.',
        citations: [
          {
            doc_name: 'Регламент возврата и обмена программных лицензий',
            section: 'п. 4.2',
            quote: 'Возврат денежных средств, отмена заказа или замена ключа после успешного ввода и активации лицензионного ключа пользователем в личном кабинете категорически не допускаются (п. 4.2 Регламента).'
          }
        ],
        email_draft: null
      };
    }

    if (qLower.includes('договор') && (qLower.includes('закупк') || qLower.includes('закуп')) && !qLower.includes('подряд')) {
      return {
        status: 'answer',
        reply: 'Договоры на закупку товаров и услуг подписывает руководитель службы снабжения (при сумме сделки до 1 000 000 руб.) либо генеральный директор компании (при сумме свыше 1 000 000 руб.) в соответствии с утверждённой матрицей полномочий.',
        citations: [
          {
            doc_name: 'Регламент закупок товаров и услуг',
            section: 'п. 3.2 (Полномочия подписания)',
            quote: 'Договоры на закупку товаров и услуг подписываются руководителем службы снабжения в пределах лимита 1 млн руб. При превышении лимита договор подлежит подписанию генеральным директором.'
          }
        ],
        email_draft: null
      };
    }

    // 3. КЕЙС 2: Уточняющий диалог (ключ не пришёл ИЛИ неоднозначный вопрос о договорах)
    const isPaymentIssue = qLower.includes('ключ не приш') ||
      (qLower.includes('оплата прошла') || (qLower.includes('оплат') && qLower.includes('ключ')));

    const isContractIssue = qLower.includes('кто подписывает договор') ||
      (qLower.includes('подписывает') && qLower.includes('договор') && !qLower.includes('закупк') && !qLower.includes('подряд'));

    // Проверяем последнее сообщение ассистента в истории
    const lastAssistantMsg = [...history].reverse().find((m) => m.role === 'assistant');
    const wasClarifyingQuestionAsked = lastAssistantMsg && lastAssistantMsg.content &&
      (lastAssistantMsg.content.includes('два сценария') || lastAssistantMsg.content.includes('30 минут'));

    if (isPaymentIssue && !wasClarifyingQuestionAsked) {
      return {
        status: 'clarify',
        reply: 'В регламенте описаны два сценария: сбой доставки письма и ошибка платёжного шлюза. Подскажите, оплата списалась, но письмо с ключом не пришло в течение 30 минут?',
        citations: [],
        email_draft: null
      };
    }

    if (isContractIssue && !wasClarifyingQuestionAsked) {
      return {
        status: 'clarify',
        reply: 'В корпоративных регламентах описаны разные правила подписания: отдельно для договоров закупки товаров и договоров с подрядчиками на оказание услуг. Уточните, пожалуйста: речь идёт о закупке товаров или договоре подряда?',
        citations: [],
        email_draft: null
      };
    }

    const wasContractClarifyingAsked = lastAssistantMsg && lastAssistantMsg.content &&
      lastAssistantMsg.content.includes('закупке товаров или договоре подряда');

    if (wasContractClarifyingAsked) {
      if (qLower.includes('закупк') || qLower.includes('товар') || qLower.includes('перв')) {
        return {
          status: 'answer',
          reply: 'Договоры на закупку товаров подписывает руководитель службы снабжения (до 1 млн руб.) либо генеральный директор компании (свыше 1 млн руб.).',
          citations: [
            {
              doc_name: 'Регламент закупок товаров и услуг',
              section: 'п. 3.2',
              quote: 'Договоры на закупку товаров подписываются руководителем службы снабжения согласно утверждённой матрице лимитов.'
            }
          ],
          email_draft: null
        };
      } else {
        return {
          status: 'answer',
          reply: 'Договоры подряда на оказание услуг подписываются директором по операционной деятельности независимо от суммы договора.',
          citations: [
            {
              doc_name: 'Регламент взаимодействия с подрядчиками',
              section: 'п. 4.1',
              quote: 'Все договоры подряда и возмездного оказания услуг подлежат визированию и подписанию операционным директором компании.'
            }
          ],
          email_draft: null
        };
      }
    }

    if (wasClarifyingQuestionAsked) {
      // Пользователь отвечает на уточняющий вопрос
      const isAffirmative =
        qLower.includes('да') ||
        qLower.includes('верно') ||
        qLower.includes('30') ||
        qLower.includes('не приш') ||
        qLower.includes('списал') ||
        qLower.includes('уже час') ||
        qLower.includes('давно');

      if (isAffirmative) {
        return {
          status: 'answer',
          reply: 'По регламенту при подтверждённом списании средств и отсутствии письма свыше 30 минут выполните следующие шаги:\n1. Обязательно проверьте папки «Спам» и «Рассылки» в почтовом ящике.\n2. Если письма нет, обратитесь к инженеру поддержки с номером чека/транзакции - специалист проверит лог почтового шлюза и продублирует ключ вручную.',
          citations: [
            {
              doc_name: 'Регламент технической поддержки лицензий',
              section: 'п. 2.3.1 (Сценарий: сбой почтовой доставки)',
              quote: 'Если транзакция подтверждена платёжным шлюзом, но письмо с ключом не поступило клиенту в течение 30 минут, специалист 1-й линии производит сверку ID транзакции и отправляет дубликат ключа повторно.'
            }
          ],
          email_draft: null
        };
      } else {
        return {
          status: 'answer',
          reply: 'Если с момента транзакции прошло менее 30 минут, операция находится в межбанковском клиринге платёжного шлюза. Ключ автоматически формируется и отправляется на почту сразу после окончательного подтверждения банком-эквайером.',
          citations: [
            {
              doc_name: 'Регламент технической поддержки лицензий',
              section: 'п. 2.3.2 (Сценарий: задержка шлюза)',
              quote: 'При статусе операции «В обработке» генерация лицензионного ключа приостанавливается до поступления подтверждающего вебхука от платёжной системы (нормативный срок - до 30 минут).'
            }
          ],
          email_draft: null
        };
      }
    }

    // 4. КЕЙС 3: Эскалация - ответа нет в регламентах (UC-03)
    const historyText = history
      .map((h) => `${h.role === 'user' ? 'Сотрудник' : 'Агент'}: ${h.content}`)
      .join('\n');

    return {
      status: 'escalate',
      reply: 'К сожалению, я не нашел ответа в регламентах.\nВаш запрос передан в службу качества.\nОжидайте ответ в ближайшее время.',
      citations: [],
      email_draft: {
        to: 'quality@company.ru',
        subject: `Запрос разъяснения регламента: ${qTrimmed.slice(0, 45)}...`,
        body: `Здравствуйте!\n\nПрошу предоставить официальное разъяснение и регламентное решение по вопросу:\n«${qTrimmed}»\n\nКонтекст обращения:\n${historyText || 'Первичное обращение сотрудника в чате'}\n\nС уважением,\nСотрудник компании`
      }
    };
  }

  /**
   * Симуляция получения тикетов (GET /tickets)
   * @param {string} [filterStatus] 
   */
  async getTickets(filterStatus = null) {
    await delay(300);
    const tickets = this.getStoredTickets();
    const sorted = [...tickets].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    if (filterStatus && filterStatus !== 'all') {
      return sorted.filter((t) => t.status === filterStatus);
    }
    return sorted;
  }

  /**
   * Симуляция создания тикета (POST /tickets)
   * @param {{ question: string, email_draft: Object, session_id: string, context?: string }} payload 
   */
  async createTicket({ question, email_draft = {}, session_id = '', context = '' }) {
    await delay(500);
    const tickets = this.getStoredTickets();
    const newId = this.generateNextTicketId(tickets);

    const newTicket = {
      ticket_id: newId,
      question: question || email_draft.subject || 'Вопрос сотрудника',
      status: 'open',
      email_to: email_draft.to || 'quality@company.ru',
      email_subject: email_draft.subject || `Запрос ${newId}`,
      email_body: email_draft.body || '',
      session_id: session_id,
      context: context || 'Сформировано из чата сотрудника',
      created_at: new Date().toISOString(),
      answer: null,
      regulation_ref: null,
      resolved_at: null
    };

    tickets.unshift(newTicket);
    this.saveStoredTickets(tickets);

    return newTicket;
  }

  /**
   * Симуляция закрытия тикета и пополнения БЗ (POST /tickets/{id}/resolve)
   * @param {string} ticketId 
   * @param {{ answer: string, regulation_ref: string }} payload 
   */
  async resolveTicket(ticketId, { answer, regulation_ref }) {
    await delay(500);
    const tickets = this.getStoredTickets();
    const index = tickets.findIndex((t) => t.ticket_id === ticketId);

    if (index === -1) {
      throw new Error(`Тикет с номером ${ticketId} не найден в базе`);
    }

    const updated = {
      ...tickets[index],
      status: 'resolved',
      answer: (answer || '').trim(),
      regulation_ref: (regulation_ref || '').trim(),
      resolved_at: new Date().toISOString()
    };

    tickets[index] = updated;
    this.saveStoredTickets(tickets);

    return updated;
  }
}

export const mockService = new MockService();
