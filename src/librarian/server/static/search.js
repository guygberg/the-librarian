import * as api from './api.js';
import { h } from './dom.js';
import * as filters from './filters.js';
import * as shell from './shell.js';
import { btn, icon } from './ui.js';

const SOURCES = { slack: 'Slack', session: 'Session', drive: 'Recording' };

const HEBREW = /[֐-׿]/;

const typing = (el) => el?.closest?.('input, textarea, select, [contenteditable]');

/** `/` focuses the search box from anywhere except a field being typed in; Enter searches (the query lives in the URL). */
export function bind(form) {
  const input = form.elements.q;
  document.addEventListener('keydown', (e) => {
    if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey || typing(e.target) || document.getElementById('dialog').open) return;
    e.preventDefault();
    input.focus();
  });
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const state = filters.current();
    window.librarianNavigate(filters.href({ open: state.open, q: input.value.trim() || null, tab: filters.tabParam(state.tab), page: state.page }));
  });
}

/** The filters still applied to the list behind the results, each with a button that clears it. */
function activeFilters(state) {
  const on = filters.FILTER_KEYS.filter((k) => state[k]).map((k) => [k, state[k]]);
  if (state.kind !== 'items') on.push(['kind', state.kind]);
  if (!on.length) return null;
  return h('div', { class: 'row kept', 'data-part': 'search-filters' }, h('span', { class: 'muted small' }, 'Filters kept:'),
    on.map(([key, value]) => btn(`${key}: ${value} ×`, { cls: 'tagchip', href: filters.href({ [key]: key === 'kind' ? 'items' : null, q: state.q }),
      'data-part': 'search-filter', 'aria-label': `Clear ${key} ${value}` })));
}

const dir = (text) => (HEBREW.test(text) ? { dir: 'rtl', lang: 'he' } : { dir: 'auto' });

/** Records first, then the raw passages. A Record opens its own page; a passage opens the source sheet. */
export async function render(form, host) {
  const state = filters.current();
  const { q, open } = state;
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
  const total = answer.records.length + passages.length;
  host.replaceChildren(h('section', { class: 'panel results', 'data-part': 'search-results' },
    h('div', { class: 'filter-banner' }, icon('search', 'small'), h('span', {}, `${total} ${total === 1 ? 'match' : 'matches'} · “${q}”`),
      btn('Clear search ×', { cls: 'textbtn', href: filters.href({ open, tab: filters.tabParam(state.tab), q: null, page: state.page }), 'data-part': 'search-clear' })),
    activeFilters(state),
    answer.records.map((r) => h('div', { class: 'res', 'data-part': 'search-record' },
      btn([icon('doc'), h('span', dir(r.title), r.title), icon('arrow', 'small')],
        { cls: 'source-row', href: filters.href({ open: r.id }), 'data-part': 'search-record-link' }))),
    passages.map((p) => h('div', { class: 'res', 'data-part': 'search-passage' },
      btn([icon('clip'), h('span', { class: 'tagchip' }, SOURCES[p.source] ?? p.source), h('span', dir(p.quote), p.quote), icon('external', 'small')],
        { cls: 'source-row', href: filters.href({ open, tab: filters.tabParam(state.tab), source: p.locator, q, page: state.page }), 'data-part': 'search-passage-link' }))),
    total ? null : h('p', { class: 'empty', 'data-part': 'search-empty' }, 'No matches.')));
}
