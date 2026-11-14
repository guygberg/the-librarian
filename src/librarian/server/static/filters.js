import { h } from './dom.js';

export const TABS = [['items', 'Items'], ['decisions', 'Decisions'], ['blockers', 'Blockers'], ['questions', 'Questions'], ['done', 'Done']];
export const DETAIL_TABS = ['overview', 'activity', 'sources', 'relations'];
/** A tab as it appears in the URL: the first one is the default and is left out. */
export const tabParam = (tab) => (tab === 'overview' ? null : tab);
const RECORD_KIND = { decisions: 'decision', blockers: 'blocker', questions: 'open_question' };

/** Every filter lives in the URL, so a reload or a shared link returns to the same view. An expanded item is `/items/<id>`. */
export function current() {
  const q = new URLSearchParams(location.search);
  const kind = q.get('kind');
  return {
    view: q.get('view') === 'board' ? 'board' : 'list', lifecycle: q.get('lifecycle'), basis: q.get('basis'), warn: q.get('warn'), since: q.get('since'),
    tag: q.get('tag'), kind: TABS.some(([k]) => k === kind) ? kind : 'items', owner: q.get('owner'), waiting: q.get('waiting'),
    open: location.pathname.match(/^\/items\/(\d+)$/)?.[1] ?? null, tab: DETAIL_TABS.includes(q.get('tab')) ? q.get('tab') : 'overview',
    source: q.get('source'), quote: q.get('quote'), q: q.get('q'), center: q.get('center'), hops: q.get('hops'), kinds: q.get('kinds'),
  };
}

/** The URL for the current filters with `change` applied; a null value clears that filter. The expanded item and
 * its tab are not carried over: changing a filter collapses it. The source sheet (`source`, an Evidence locator)
 * is only ever the one asked for, with the `quote` clicked: a locator names a Source item, not which of its
 * Evidence quotes was meant. */
export function href({ open = null, tab = null, source = null, quote = null, ...change }) {
  const q = new URLSearchParams();
  const graphKeys = ['center', 'hops', 'kinds']; // the Relations graph's state, kept only while that tab is shown
  for (const [key, value] of Object.entries({ ...current(), ...change, tab: open ? tab : null, source, quote })) {
    if (graphKeys.includes(key) && !(open && tab === 'relations')) continue;
    if (key !== 'open' && value && !(key === 'kind' && value === 'items') && !(key === 'view' && value === 'list')) q.set(key, value);
  }
  return `${open ? `/items/${open}` : '/items'}${q.size ? `?${q}` : ''}`;
}

export function waitingOn(item) {
  return item.waiting_on ?? item.links.find((l) => l.type === 'waiting_on')?.to ?? null;
}

/** Warning states a Record can carry, named for the `warn` filter. The query core decides them; the browser only reads the flags. */
export const WARNINGS = {
  disagree: ['Sources disagree', (i) => i.contradictions.length > 0],
  uncertain: ['Transcription uncertain', (i) => Boolean(i.transcription_uncertain)],
  stale: ['Not mentioned lately', (i) => Boolean(i.stale && i.last_evidence)],
  suggested: ['Awaiting confirmation', (i) => (i.suggested ?? []).length > 0],
};

export function matches(item, state) {
  if (state.lifecycle && item.lifecycle !== state.lifecycle) return false;
  if (state.basis && item.basis !== state.basis) return false;
  if (state.warn && !WARNINGS[state.warn]?.[1](item)) return false;
  if (state.since && !(item.last_evidence && item.last_evidence.slice(0, 10) >= state.since)) return false;
  if (state.tag && !item.tags.some((p) => p.title === state.tag)) return false;
  if (state.owner && item.owner !== state.owner) return false;
  if (state.waiting && waitingOn(item) !== state.waiting) return false;
  switch (state.kind) {
    case 'done': return item.lifecycle === 'done';
    case 'decisions': return item.kind === 'decision';
    case 'items': return item.group !== null || (state.view === 'board' && item.lifecycle === 'done');
    default: return item.kind === RECORD_KIND[state.kind] && item.group !== null;
  }
}

const chip = (text, to, on, part) => h('a', { href: to, class: on ? 'chip on' : 'chip', 'data-link': true, 'data-part': part }, text);

export function chips(tags, state) {
  return h('div', { class: 'pf', 'data-part': 'tag-filter' },
    chip('All work', href({ tag: null }), !state.tag, 'tag-chip'),
    tags.map((p) => chip(p.title, href({ tag: p.title }), state.tag === p.title, 'tag-chip')));
}

export function tabs(state) {
  return h('div', { class: 'tabs', 'data-part': 'kind-tabs' },
    TABS.map(([kind, label]) => chip(label, href({ kind }), state.kind === kind, 'kind-tab')));
}

/** `choices` are names, or [value, label] pairs when the URL value differs from the text shown. */
function menu(label, key, choices, state) {
  const select = h('select', { 'data-part': `${key}-filter`, 'aria-label': label },
    h('option', { value: '' }, label),
    choices.map((c) => [].concat(c)).map(([value, text = value]) => h('option', { value, selected: state[key] === value }, text)));
  select.addEventListener('change', () => window.librarianNavigate(href({ [key]: select.value || null })));
  return select;
}

/** Lifecycle, Basis, warning state and date: the filters that need no list of names from the data. */
export function more(state) {
  const since = h('input', { type: 'date', value: state.since ?? '', 'data-part': 'since-filter', 'aria-label': 'Updated since' });
  since.addEventListener('change', () => window.librarianNavigate(href({ since: since.value || null })));
  return h('div', { class: 'people', 'data-part': 'more-filters' },
    menu('Lifecycle: any', 'lifecycle', ['open', 'pending', 'suspended', 'done', 'dropped', 'superseded'], state),
    menu('Basis: any', 'basis', ['stated', 'inferred', 'confirmed'], state),
    menu('Warning: any', 'warn', Object.entries(WARNINGS).map(([k, [text]]) => [k, text]), state),
    since);
}

/** List and Board show the same filtered records; only the layout differs. */
export function views(state) {
  return h('div', { class: 'tabs', 'data-part': 'view-toggle' },
    [['list', 'List'], ['board', 'Board']].map(([view, text]) => chip(text, href({ view }), state.view === view, 'view-tab')));
}

/** A person is a filter on owner and on waiting-on, never a page. */
export function people(owners, waiting, state) {
  const names = (list) => [...new Set(list.filter(Boolean))].sort();
  return h('div', { class: 'people', 'data-part': 'person-filter' },
    menu('Owner: anyone', 'owner', names(owners), state),
    menu('Waiting on: anyone', 'waiting', names(waiting), state));
}
