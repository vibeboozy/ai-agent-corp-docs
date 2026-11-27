/**
 * Pure helpers for appeal/session id lifecycle and quality-cabinet mapping.
 * Kept free of DOM/store so Node tests can import them directly.
 */

/** RFC-4122 UUID (any version) — used by the server for appeal ids. */
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Local client session ids must NOT look like server UUIDs.
 * Otherwise sendChatMessage treats a brand-new chat as an existing appeal
 * and POSTs to /appeals/{mystery-uuid}/messages → 404.
 */
export function createLocalSessionId() {
  const rand =
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID().replace(/-/g, '').slice(0, 16)
      : Math.random().toString(36).substring(2, 11) + Date.now().toString(36);
  return `sess-${rand}`;
}

export function isServerAppealId(id) {
  if (!id || typeof id !== 'string') return false;
  if (id.startsWith('sess-')) return false;
  return UUID_RE.test(id);
}

/**
 * Map server AppealStatus → quality-cabinet UI status.
 * Only escalated appeals await an officer; answered ≠ «Ожидают ответа».
 */
export function mapAppealStatusToTicketStatus(rawStatus) {
  switch (rawStatus) {
    case 'escalated':
      return 'open';
    case 'resolved_by_officer':
    case 'closed':
      return 'resolved';
    case 'answered':
      return 'answered';
    case 'clarifying':
    case 'open':
      return 'in_progress';
    default:
      return 'in_progress';
  }
}

export function ticketStatusLabel(uiStatus) {
  switch (uiStatus) {
    case 'open':
      return 'Ожидает ответа';
    case 'resolved':
      return 'В базе знаний';
    case 'answered':
      return 'Отвечено агентом';
    case 'in_progress':
      return 'В диалоге';
    default:
      return 'В диалоге';
  }
}

export function ticketStatusBadgeClass(uiStatus) {
  switch (uiStatus) {
    case 'open':
      return 'badge-open';
    case 'resolved':
      return 'badge-resolved';
    case 'answered':
      return 'badge-answer';
    case 'in_progress':
      return 'badge-clarify';
    default:
      return 'badge-clarify';
  }
}

/**
 * Prefer topic / explicit question; never fall back to summary (AI answer text).
 */
export function resolveEmployeeQuestion({ topic, question, firstUserMessage } = {}) {
  const candidates = [firstUserMessage, question, topic];
  for (const c of candidates) {
    if (typeof c === 'string' && c.trim()) return c.trim();
  }
  return 'Вопрос сотрудника';
}

/**
 * Pick the first user-role message content from a messages list.
 */
export function firstUserQuestionFromMessages(messages) {
  if (!Array.isArray(messages)) return null;
  const user = messages.find((m) => m && m.role === 'user' && m.content);
  return user ? String(user.content).trim() : null;
}

/**
 * Server allows further turns unless appeal is closed (409 CONFLICT_STATUS).
 * answered / clarifying / escalated / open → continue; closed → new chat.
 */
export function canSendInAppeal(rawStatus) {
  if (!rawStatus) return true;
  return rawStatus !== 'closed';
}

export const APPEALS_LIST_LIMIT = 200;
