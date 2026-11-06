import * as api from './api.js';
import { h } from './dom.js';
import { clock, isToday, parseLocal, shortDate } from './format.js';

// The order the line is read in.
const LABELS = { slack: 'slack', session: 'claude sessions', drive: 'recordings' };

function source(name, state) {
  const label = LABELS[name] ?? name;
  const warn = state.overdue ? 'w' : null;
  if (!state.last_import_finished_at) return h('span', { class: 'w' }, `${label} never imported`);
  const at = parseLocal(state.last_import_finished_at);
  return h('span', { class: warn }, isToday(at) ? `${label} ${clock(at)} today` : `${label} through ${shortDate(at)}`);
}

/** The last successful Import per source, shown at the top of every view. */
export async function render(target) {
  const { freshness } = await api.get('/api/open-items');
  const parts = Object.keys(LABELS)
    .filter((name) => name in freshness.sources)
    .map((name) => source(name, freshness.sources[name]));
  const line = [];
  parts.forEach((part, i) => line.push(i ? ' · ' : 'Updated from ', part));
  target.replaceChildren(...line);
}

/** "Last import 09:12." for the empty state; names the day when it was not today. */
export function lastImport(freshness) {
  if (!freshness.last_import_finished_at) return 'No import yet.';
  const at = parseLocal(freshness.last_import_finished_at);
  return `Last import ${isToday(at) ? '' : `${shortDate(at)} `}${clock(at)}.`;
}
