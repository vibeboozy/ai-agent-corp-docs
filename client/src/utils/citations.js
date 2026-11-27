/**
 * Collapse duplicate citations for «Источники и цитаты».
 * Server should already dedupe; this is a UI safety net for learned re-asks.
 */
export function dedupeCitations(citations) {
  if (!Array.isArray(citations) || citations.length === 0) {
    return [];
  }
  const seen = new Set();
  const out = [];
  for (const c of citations) {
    const doc = String(c.doc_name || c.document_title || c.document_id || '')
      .trim()
      .toLowerCase();
    const section = String(c.section || c.locator || '')
      .trim()
      .toLowerCase();
    const quote = String(c.quote || '')
      .replace(/\s+/g, ' ')
      .trim()
      .toLowerCase()
      .slice(0, 240);
    const chunk = String(c.chunk_id || '').trim();
    const key = chunk
      ? `id:${chunk}`
      : `q:${doc}|${section}|${quote}`;
    if (seen.has(key)) continue;
    if (quote) {
      const quoteKey = `quote:${quote}`;
      if (seen.has(quoteKey)) continue;
      seen.add(quoteKey);
    }
    seen.add(key);
    out.push(c);
  }
  return out;
}
