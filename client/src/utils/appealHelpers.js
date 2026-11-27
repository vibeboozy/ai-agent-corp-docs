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
 * Client-side preview of the quality-service email for an escalate answer.
 * Server does not persist this draft on messages — the chat UI synthesizes it
 * on live escalate and must recompute the same shape when reloading history.
 */
export function buildEscalationEmailDraft(question) {
  const q = typeof question === 'string' ? question.trim() : '';
  const topic = q || 'вопрос по регламенту';
  return {
    to: 'quality@company.ru',
    subject: `Запрос разъяснения регламента: ${topic.slice(0, 45)}...`,
    body:
      `Здравствуйте!\n\nПрошу предоставить официальное разъяснение по вопросу:\n«${topic}»\n\nС уважением,\nСотрудник отдела сопровождения`
  };
}

/**
 * Whether the quality-preview form should render for an escalate message.
 * Hide after local send confirmation, or when the appeal is no longer awaiting quality.
 */
export function shouldShowEscalationPreviewForm(msg, appealStatus) {
  if (!msg || msg.status !== 'escalate') return false;
  if (msg.ticketCreated) return false;
  if (
    appealStatus === 'resolved_by_officer' ||
    appealStatus === 'closed' ||
    appealStatus === 'answered'
  ) {
    return false;
  }
  return Boolean(msg.email_draft);
}

/**
 * Attach synthesized email_draft to escalate messages using the preceding user question.
 * Idempotent: keeps an existing draft / ticketCreated / ticketId when present.
 */
export function attachEscalationEmailDrafts(messages) {
  if (!Array.isArray(messages)) return [];
  let lastUserQuestion = '';
  return messages.map((m) => {
    if (m && m.role === 'user' && m.content) {
      lastUserQuestion = String(m.content).trim();
    }
    const isEscalate =
      m &&
      (m.status === 'escalate' || m.message_kind === 'escalation_notice');
    if (!isEscalate) return m;
    if (m.email_draft) {
      return {
        ...m,
        ticketCreated: Boolean(m.ticketCreated),
        ticketId: m.ticketId || null
      };
    }
    return {
      ...m,
      email_draft: buildEscalationEmailDraft(lastUserQuestion),
      ticketCreated: Boolean(m.ticketCreated),
      ticketId: m.ticketId || null
    };
  });
}

/**
 * Merge local ticketCreated / ticketId / edited email_draft onto server-reloaded messages
 * so a return to the same appeal keeps send-confirmation (or an edited preview).
 */
export function mergeLocalEscalationState(serverMessages, localMessages) {
  const enriched = attachEscalationEmailDrafts(serverMessages);
  if (!Array.isArray(localMessages) || localMessages.length === 0) return enriched;
  const localById = new Map(
    localMessages.filter((m) => m && m.id != null).map((m) => [String(m.id), m])
  );
  return enriched.map((m) => {
    if (!m || m.id == null) return m;
    const local = localById.get(String(m.id));
    if (!local) return m;
    const isEscalate =
      m.status === 'escalate' || m.message_kind === 'escalation_notice';
    if (!isEscalate) return m;
    return {
      ...m,
      email_draft: local.email_draft || m.email_draft,
      ticketCreated: Boolean(local.ticketCreated) || Boolean(m.ticketCreated),
      ticketId: local.ticketId || m.ticketId || null
    };
  });
}

/**
 * Compare chat message lists for feed-render equivalence.
 * Used to skip wholesale DOM remounts when a history reload returns the same UI.
 */
export function areChatMessagesRenderEqual(a, b) {
  if (a === b) return true;
  if (!Array.isArray(a) || !Array.isArray(b)) return false;
  if (a.length !== b.length) return false;

  for (let i = 0; i < a.length; i++) {
    const left = a[i] || {};
    const right = b[i] || {};
    if (String(left.id) !== String(right.id)) return false;
    if (left.role !== right.role) return false;
    if (left.content !== right.content) return false;
    if ((left.status || '') !== (right.status || '')) return false;
    if (Boolean(left.ticketCreated) !== Boolean(right.ticketCreated)) return false;
    if (String(left.ticketId || '') !== String(right.ticketId || '')) return false;

    const leftDraft = left.email_draft || null;
    const rightDraft = right.email_draft || null;
    if (Boolean(leftDraft) !== Boolean(rightDraft)) return false;
    if (leftDraft && rightDraft) {
      if ((leftDraft.to || '') !== (rightDraft.to || '')) return false;
      if ((leftDraft.subject || '') !== (rightDraft.subject || '')) return false;
      if ((leftDraft.body || '') !== (rightDraft.body || '')) return false;
    }

    const leftCitations = left.citations || [];
    const rightCitations = right.citations || [];
    if (leftCitations.length !== rightCitations.length) return false;
    for (let c = 0; c < leftCitations.length; c++) {
      const lc = leftCitations[c] || {};
      const rc = rightCitations[c] || {};
      if ((lc.doc_name || '') !== (rc.doc_name || '')) return false;
      if ((lc.section || '') !== (rc.section || '')) return false;
      if ((lc.quote || '') !== (rc.quote || '')) return false;
    }
  }
  return true;
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
