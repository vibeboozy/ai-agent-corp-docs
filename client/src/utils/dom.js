/**
 * Экранирование спецсимволов HTML для предотвращения XSS-уязвимостей.
 * @param {string} str 
 * @returns {string}
 */
export function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  const s = String(str);
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Безопасное экранирование текста с преобразованием переводов строк \n в <br>.
 * @param {string} str 
 * @returns {string}
 */
export function formatTextWithLineBreaks(str) {
  if (!str) return '';
  return escapeHtml(str).replace(/\n/g, '<br>');
}

/**
 * Форматирование ISO-даты в читаемый формат (например: 26 нояб. 2026, 12:35)
 * @param {string|Date} dateInput 
 * @returns {string}
 */
export function formatDateTime(dateInput) {
  if (!dateInput) return '';
  try {
    const d = new Date(dateInput);
    if (isNaN(d.getTime())) return String(dateInput);
    return d.toLocaleString('ru-RU', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch {
    return String(dateInput);
  }
}

/**
 * Краткое время (например: 12:35)
 * @param {string|Date} dateInput 
 * @returns {string}
 */
export function formatTimeShort(dateInput) {
  if (!dateInput) return '';
  try {
    const d = new Date(dateInput);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleTimeString('ru-RU', {
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch {
    return '';
  }
}

/**
 * Компактное отображение даты для списка сессий (например: "14:35" если сегодня, иначе "26 нояб.")
 * @param {string|Date} dateInput 
 * @returns {string}
 */
export function formatSessionDate(dateInput) {
  if (!dateInput) return '';
  try {
    const d = new Date(dateInput);
    if (isNaN(d.getTime())) return '';
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    if (isToday) {
      return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
  } catch {
    return '';
  }
}

/**
 * Автоматическое изменение высоты textarea под вводимый контент
 * @param {HTMLTextAreaElement} textarea 
 * @param {number} maxHeight 
 */
export function autoResizeTextarea(textarea, maxHeight = 120) {
  if (!textarea) return;
  textarea.style.height = 'auto';
  const newHeight = Math.min(textarea.scrollHeight, maxHeight);
  textarea.style.height = `${newHeight}px`;
}
