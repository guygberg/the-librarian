import { h } from './dom.js';

export const TABS = [['items', 'Items'], ['decisions', 'Decisions'], ['blockers', 'Blockers'], ['questions', 'Questions'], ['done', 'Done']];
const RECORD_KIND = { decisions: 'decision', blockers: 'blocker', questions: 'open_question' };

/** Every filter lives in the URL, so a reload or a shared link returns to the same view. An expanded item is `/items/<id>`. */
export function current() {
  const q = new URLSearchParams(location.search);
  const kind = q.get('kind');
  return {
    project: q.get('project'), kind: TABS.some(([k]) => k === kind) ? kind : 'items', owner: q.get('owner'), waiting: q.get('waiting'),
    open: location.pathname.match(/^\/items\/(\d+)$/)?.[1] ?? null, tab: q.get('tab') === 'relations' ? 'relations' : 'evidence',
    source: q.get('source'), center: q.get('center'), hops: q.get('hops'), kinds: q.get('kinds'),
  };
}

/** The URL for the current filters with `change` applied; a null value clears that filter. The expanded item and
 * its tab are not carried over: changing a filter collapses it. The source sheet (`source`, an Evidence locator)
 * is only ever the one asked for. */
export function href({ open = null, tab = null, source = null, ...change }) {
  const q = new URLSearchParams();
  const graphKeys = ['center', 'hops', 'kinds']; // the Relations graph's state, kept only while that tab is shown
  for (const [key, value] of Object.entries({ ...current(), ...change, tab: open ? tab : null, source })) {
    if (graphKeys.includes(key) && !(open && tab === 'relations')) continue;
    if (key !== 'open' && value && !(key === 'kind' && value === 'items')) q.set(key, value);
  }
  return `${open ? `/items/${open}` : '/'}${q.size ? `?${q}` : ''}`;
}

export function waitingOn(item) {
  return item.waiting_on ?? item.links.find((l) => l.type === 'waiting_on')?.to ?? null;
}

export function matches(item, state) {
  if (state.project && !item.projects.some((p) => p.title === state.project)) return false;
  if (state.owner && item.owner !== state.owner) return false;
  if (state.waiting && waitingOn(item) !== state.waiting) return false;
  switch (state.kind) {
    case 'done': return item.lifecycle === 'done';
    case 'decisions': return item.kind === 'decision';
    case 'items': return item.group !== null;
    default: return item.kind === RECORD_KIND[state.kind] && item.group !== null;
  }
}

const chip = (text, to, on, part) => h('a', { href: to, class: on ? 'chip on' : 'chip', 'data-link': true, 'data-part': part }, text);

export function chips(projects, state) {
  return h('div', { class: 'pf', 'data-part': 'project-filter' },
    chip('All work', href({ project: null }), !state.project, 'project-chip'),
    projects.map((p) => chip(p.title, href({ project: p.title }), state.project === p.title, 'project-chip')));
}

export function tabs(state) {
  return h('div', { class: 'tabs', 'data-part': 'kind-tabs' },
    TABS.map(([kind, label]) => chip(label, href({ kind }), state.kind === kind, 'kind-tab')));
}

function menu(label, key, names, state) {
  const select = h('select', { 'data-part': `${key}-filter`, 'aria-label': label },
    h('option', { value: '' }, label),
    names.map((n) => h('option', { value: n, selected: state[key] === n }, n)));
  select.addEventListener('change', () => window.librarianNavigate(href({ [key]: select.value || null })));
  return select;
}

/** A person is a filter on owner and on waiting-on, never a page. */
export function people(owners, waiting, state) {
  const names = (list) => [...new Set(list.filter(Boolean))].sort();
  return h('div', { class: 'people', 'data-part': 'person-filter' },
    menu('Owner: anyone', 'owner', names(owners), state),
    menu('Waiting on: anyone', 'waiting', names(waiting), state));
}
