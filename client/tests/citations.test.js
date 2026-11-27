import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { dedupeCitations } from '../src/utils/citations.js';

describe('dedupeCitations', () => {
  it('collapses identical quotes from separate learned docs', () => {
    const quote = 'Цвет логотипа — Pantone 286 C.';
    const out = dedupeCitations([
      { doc_name: 'Канонический ответ офицера качества', section: '', quote },
      { doc_name: 'Канонический ответ офицера качества', section: '', quote },
      { doc_name: 'Канонический ответ офицера качества', section: '', quote }
    ]);
    assert.equal(out.length, 1);
    assert.equal(out[0].quote, quote);
  });

  it('keeps distinct quotes', () => {
    const out = dedupeCitations([
      { doc_name: 'Регламент A', section: '1.1', quote: 'Первая цитата' },
      { doc_name: 'Регламент B', section: '2.2', quote: 'Вторая цитата' }
    ]);
    assert.equal(out.length, 2);
  });

  it('dedupes by chunk_id when present', () => {
    const out = dedupeCitations([
      { chunk_id: 'c1', doc_name: 'Doc', quote: 'A' },
      { chunk_id: 'c1', doc_name: 'Doc', quote: 'A again' }
    ]);
    assert.equal(out.length, 1);
  });
});
