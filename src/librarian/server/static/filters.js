import { priority } from './entities.js';
import { NEEDS, WAITING } from './ui.js';

export const KINDS = [['items', 'Open items'], ['done', 'Completed']];
export const DETAIL_TABS = ['overview', 'activity', 'sources', 'relations'];
/** A tab as it appears in the URL: the first one is the default and is left out. */
export const tabParam = (tab) => (tab === 'overview' ? null : tab);
const GROUPS = { needs: NEEDS, waiting: WAITING };

/** Every filter lives in the URL, so a reload or a shared link returns to the same view. An item's own page is `/items/<id>`. */
export function current() {
  const q = new URLSearchParams(location.search);
  const kind = q.get('kind');
  return {
    untagged: q.get('untagged'), priority: q.get('priority'),
    view: q.get('view') === 'board' ? 'board' : 'list', lifecycle: q.get('lifecycle'), basis: q.get('basis'), warn: q.get('warn'), since: q.get('since'),
    project: q.get('project'), kind: KINDS.some(([k]) => k === kind) ? kind : 'items', group: q.get('group') in GROUPS ? q.get('group') : null,
    owner: q.get('owner'), waiting: q.get('waiting'), person: q.get('person'), sort: q.get('sort') === 'name' ? 'name' : null,
    page: Number(q.get('page')) > 1 ? q.get('page') : null,
    open: location.pathname.match(/^\/items\/(\d+)$/)?.[1] ?? null, tab: DETAIL_TABS.includes(q.get('tab')) ? q.get('tab') : 'overview',
    source: q.get('source'), quote: q.get('quote'), q: q.get('q'), center: q.get('center'), hops: q.get('hops'), kinds: q.get('kinds'),
  };
}

/** The filters that narrow the Items list, as the banner and the search results name them. */
export const FILTER_KEYS = ['priority', 'untagged', 'project', 'person', 'owner', 'waiting', 'lifecycle', 'basis', 'warn', 'since'];

/** The URL for the current filters with `change` applied; a null value clears that filter. The open item and
 * its tab are not carried over: changing a filter returns to the list, on its first page unless `page` is given.
 * The source sheet (`source`, an Evidence locator) is only ever the one asked for, with the `quote` clicked:
 * a locator names a Source item, not which of its Evidence quotes was meant. */
export function href({ open = null, tab = null, source = null, quote = null, page = null, ...change }) {
  const q = new URLSearchParams();
  const graphKeys = ['center', 'hops', 'kinds']; // the Relations graph's state, kept only while that tab is shown
  for (const [key, value] of Object.entries({ ...current(), ...change, tab: open ? tab : null, source, quote, page })) {
    if (graphKeys.includes(key) && !(open && tab === 'relations')) continue;
    if (key !== 'open' && value && !(key === 'kind' && value === 'items') && !(key === 'view' && value === 'list')) q.set(key, value);
  }
  return `${open ? `/items/${open}` : '/items'}${q.size ? `?${q}` : ''}`;
}

/** The Items list with nothing narrowed. */
export const cleared = () => href(Object.fromEntries([...FILTER_KEYS, 'q', 'group', 'kind', 'sort'].map((k) => [k, null])));

export function waitingOn(item) {
  return item.waiting_on ?? item.links.find((l) => l.type === 'waiting_on')?.to ?? null;
}

export const involves = (item, name) => item.owner === name || item.links.some((l) => l.to === name);

/** Warning states a Record can carry, named for the `warn` filter. The query core decides them; the browser only reads the flags. */
export const WARNINGS = {
  disagree: ['Sources disagree', (i) => i.contradictions.length > 0],
  uncertain: ['Transcription uncertain', (i) => Boolean(i.transcription_uncertain)],
  stale: ['Not mentioned lately', (i) => Boolean(i.stale && i.last_evidence)],
  suggested: ['Awaiting confirmation', (i) => (i.suggested ?? []).length > 0],
};

export function matches(item, state) {
  if (state.priority && (priority(item) >= 80 ? 'high' : priority(item) >= 60 ? 'medium' : 'low') !== state.priority) return false;
  if (state.untagged && item.projects.length) return false;
  if (state.lifecycle && item.lifecycle !== state.lifecycle) return false;
  if (state.basis && item.basis !== state.basis) return false;
  if (state.warn && !WARNINGS[state.warn]?.[1](item)) return false;
  if (state.since && !(item.last_evidence && item.last_evidence.slice(0, 10) >= state.since)) return false;
  if (state.project && !item.projects.some((p) => p.title === state.project)) return false;
  if (state.owner && item.owner !== state.owner) return false;
  if (state.waiting && waitingOn(item) !== state.waiting) return false;
  if (state.person && !involves(item, state.person)) return false;
  if (state.group && item.group !== GROUPS[state.group]) return false;
  switch (state.kind) {
    case 'done': return item.lifecycle === 'done';
    // A lifecycle asked for by name is shown even when it is not an open one.
    case 'items': return item.group !== null || Boolean(state.lifecycle && !item.is_tag);
    default: return false;
  }
}
