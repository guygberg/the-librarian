import * as api from './api.js';
import { h } from './dom.js';
import * as filters from './filters.js';
import * as shell from './shell.js';

const SOURCES = { slack: 'Slack', session: 'Session', drive: 'Recording' };

const HEBREW = /[֐-׿]/;

const typing = (el) => el?.closest?.('input, textarea, select, [contenteditable]');

/** `/` focuses the search box from anywhere except a field being typed in; Enter searches (the query lives in the URL). */
export function bind(form) {
  const input = form.elements.q;
  document.addEventListener('keydown', (e) => {
    if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey || typing(e.target)) return;
    e.preventDefault();
    input.focus();
  });
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    window.librarianNavigate(filters.href({ ...filters.current(), q: input.value.trim() || null, tab: filters.tabParam(filters.current().tab) }));
  });
}

const FILTER_KEYS = ['project', 'owner', 'waiting', 'lifecycle', 'basis', 'warn', 'since'];

/** The filters still applied to the stream behind the results, with a link that clears each one. */
function activeFilters(state) {
  const on = FILTER_KEYS.filter((k) => state[k]).map((k) => [k, state[k]]);
  if (state.kind !== 'items') on.push(['kind', state.kind]);
  if (!on.length) return null;
  return h('div', { class: 'pf', 'data-part': 'search-filters' }, 'Filters kept: ',
    on.map(([key, value]) => h('a', { class: 'chip on', href: filters.href({ [key]: key === 'kind' ? 'items' : null }), 'data-link': true,
      'data-part': 'search-filter', 'aria-label': `Clear ${key} ${value}` }, `${key}: ${value} ×`)));
}

const dir = (text) => (HEBREW.test(text) ? { dir: 'rtl', lang: 'he' } : { dir: 'auto' });

/** Records first, then the raw passages. A Record opens in place in the stream; a passage opens the source sheet. */
export async function render(form, host) {
  const { q, open } = filters.current();
  form.elements.q.value = q ?? '';
  if (!q) return host.replaceChildren();
  host.replaceChildren(shell.loading('Searching'));
  let answer;
  try {
    answer = await api.get(`/api/search?q=${encodeURIComponent(q)}`);
  } catch (e) {
    return host.replaceChildren(shell.failure(`Search failed: ${e.message}`));
  }
  const passages = answer.evidence.filter((e) => e.record_id === null);
  const link = (text, to, part, attrs) => h('a', { href: to, 'data-link': true, 'data-part': part, ...attrs }, text);
  host.replaceChildren(h('div', { class: 'results', 'data-part': 'search-results' },
    activeFilters(filters.current()),
    answer.records.map((r) => h('div', { class: 'res', 'data-part': 'search-record' },
      link(r.title, filters.href({ open: r.id }), 'search-record-link', dir(r.title)), h('span', { class: 'm' }, r.kind.replace('_', ' ')))),
    passages.map((p) => h('div', { class: 'res', 'data-part': 'search-passage' },
      h('b', {}, SOURCES[p.source] ?? p.source), ' ',
      link(p.quote, filters.href({ open, source: p.locator }), 'search-passage-link', dir(p.quote)))),
    answer.records.length || passages.length ? null : h('p', { class: 'empty', 'data-part': 'search-empty' }, 'No matches.')));
}
