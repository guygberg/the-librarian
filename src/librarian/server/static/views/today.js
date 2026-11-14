import { act, justActed } from '../actions.js';
import * as api from '../api.js';
import { h } from '../dom.js';
import { clock, dateLine, isToday, shortDate } from '../format.js';
import { lastImport } from '../freshness.js';
import { href } from '../filters.js';
import { changedStrip } from './stream.js';
import { suggestionLine } from './suggestion-card.js';

const PAGE = 5;
const NEEDS = 'needs_attention';
const WAITING = 'waiting_on_others';

const when = (iso) => {
  const at = new Date(iso);
  return isToday(at) ? `today ${clock(at)}` : `${shortDate(at)} ${clock(at)}`;
};

const open = (item) => h('a', { href: href({ open: item.id }), 'data-link': true }, item.title);

/** Why the item is ranked where it is: the query's own order, and the flags that raise an item within its group. */
function why(item, ahead) {
  const flags = [];
  if (item.contradictions.length) flags.push('its sources disagree');
  if (item.stale && item.last_evidence) flags.push(`it has not been mentioned since ${shortDate(new Date(item.last_evidence))}`);
  if (item.stated_deadline) flags.push(`it is due ${item.stated_deadline}`);
  const rank = ahead ? `first of ${ahead + 1} things that need you` : 'the only thing that needs you';
  return `Ranked ${rank}${flags.length ? `: ${flags.join(', ')}` : ''}.`;
}

function tile(part, label, value, to) {
  return h('a', { class: 'tile', href: to, 'data-link': true, 'data-part': part }, h('b', {}, String(value)), h('span', {}, label));
}

function nextBestMove(needs) {
  const [first] = needs;
  if (!first) return null;
  return h('section', { class: 'panel next', 'data-part': 'next-best-move' },
    h('div', { class: 'grp' }, 'Next best move'),
    h('div', { class: 't', 'data-part': 'next-title' }, open(first)),
    h('p', { class: 'pnote', 'data-part': 'next-why' }, why(first, needs.length - 1)),
    h('div', { class: 'acts' }, h('a', { class: 'chip', href: href({ open: first.id }), 'data-link': true, 'data-part': 'next-open' }, 'Open')));
}

function button(part, text, onClick) {
  const el = h('button', { type: 'button', class: 'chip', 'data-part': part }, text);
  el.addEventListener('click', onClick);
  return el;
}

/** A panel that shows `PAGE` entries at a time; its Previous and Next controls redraw only the panel. */
function pagedPanel(part, title, list, entry, empty, settle) {
  const body = h('div', { 'data-part': `${part}-list` });
  const pager = h('div', { class: 'm', 'data-part': `${part}-pager` });
  let at = 0;
  const draw = () => {
    const shown = list.slice(at, at + PAGE);
    body.replaceChildren(...(shown.length ? shown.map(entry) : [h('p', { class: 'empty small', 'data-part': 'empty' }, empty)]));
    const prev = button(`${part}-prev`, 'Previous', () => { at -= PAGE; draw(); });
    const next = button(`${part}-next`, 'Next', () => { at += PAGE; draw(); });
    prev.disabled = at === 0;
    next.disabled = at + PAGE >= list.length;
    pager.replaceChildren(...(list.length > PAGE
      ? [h('span', { 'data-part': `${part}-range` }, `${at + 1}–${at + shown.length} of ${list.length}`), prev, next]
      : []));
  };
  draw();
  return h('section', { class: settle ? 'panel settle' : 'panel', 'data-part': part },
    h('div', { class: 'grp' }, `${title} (${list.length})`), body, pager);
}

const itemRow = (item) => h('div', { class: 'it', 'data-part': 'today-item' },
  h('div', { class: 't' }, open(item)),
  h('div', { class: 'm' },
    h('span', {}, item.tags.map((p) => p.title).join(', ')),
    item.stated_deadline ? h('span', {}, `due ${item.stated_deadline}`) : null,
    button('today-done', 'Mark done', () => act(item.id, 'done'))));

const doneRow = (item) => h('div', { class: 'it', 'data-part': 'completed-item' },
  h('div', { class: 't' }, open(item)),
  h('div', { class: 'm' },
    h('span', { 'data-part': 'completed-at' }, `Finished ${when(item.done_at)}`),
    button('today-reopen', 'Reopen', () => act(item.id, 'reopen'))));

const reviewRow = (row) => h('div', { class: 'it', 'data-part': 'today-review' },
  h('div', { class: 'm' }, h('span', { class: 'w' }, row.mark), row.raw_name ? h('span', {}, `"${row.raw_name}"`) : null),
  h('div', { class: 't' }, h('a', { href: '/review', 'data-link': true }, row.record.title)));

const label = (event) => event.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());

/** What the person and Import changed since the last meeting; nothing invented when it was quiet. */
function activity(changes) {
  const titles = new Map(changes.records.map((r) => [r.id, r.title]));
  const imported = changes.changes.filter((c) => c.import);
  const made = imported.filter((c) => c.import === 'created').length;
  const lines = [
    ...changes.person_events.map((e) => h('div', { class: 'm', 'data-part': 'person-event' },
      h('span', {}, `${label(e.event)} · ${titles.get(e.record_id) ?? 'an item'}`), h('span', {}, when(e.at)))),
    imported.length
      ? h('div', { class: 'm', 'data-part': 'import-change' }, h('span', {}, `Import: ${made} new, ${imported.length - made} updated`))
      : null,
  ].filter(Boolean);
  return h('section', { class: 'panel', 'data-part': 'activity' },
    h('div', { class: 'grp' }, 'Activity'),
    h('p', { class: 'pnote' }, changes.resolved.baseline),
    lines.length ? lines : h('p', { class: 'empty small', 'data-part': 'empty' }, 'Nothing has changed in that time.'));
}

/** The Today dashboard: every number and list comes from the open-items, review and changes answers. */
export async function today() {
  const acted = justActed();
  const settled = ['done', 'reopen'].includes(acted?.name);
  const [answer, review, changes, visit] = await Promise.all([
    api.get('/api/open-items?scope=all'), api.get('/api/review'), api.get('/api/changes'), api.get('/api/visit')]);
  const of = (group) => answer.records.filter((r) => r.group === group);
  const needs = of(NEEDS);
  const waiting = of(WAITING);
  const openCount = answer.records.filter((r) => r.group).length;
  const completed = answer.records
    .filter((r) => r.lifecycle === 'done' && r.done_at)
    .sort((a, b) => b.done_at.localeCompare(a.done_at));
  const calm = `Nothing needs you today. ${lastImport(answer.freshness)}`;

  return h('section', { class: 'page today', 'data-part': 'today' },
    h('div', { class: 'date', 'data-part': 'date-line' }, dateLine(new Date())),
    changedStrip(visit),
    h('h1', {}, 'Today'),
    h('div', { class: settled ? 'tiles settle' : 'tiles', 'data-part': 'counts' },
      tile('count-open', 'Open', openCount, '/items'),
      tile('count-needs', 'Needs attention', needs.length, '/items'),
      tile('count-waiting', 'Waiting', waiting.length, '/items'),
      tile('count-review', 'Review', review.count, '/review')),
    nextBestMove(needs),
    pagedPanel('needs', 'Needs you', needs, itemRow, calm, settled),
    pagedPanel('waiting', 'Waiting', waiting, itemRow, 'Nothing is waiting on someone else.', settled),
    pagedPanel('review', 'Review', review.rows, (row) => (row.type === 'suggestion' ? suggestionLine(row) : reviewRow(row)), 'Nothing to review.', false),
    pagedPanel('completed', 'Recently completed', completed, doneRow, 'Nothing has been finished yet.', settled),
    activity(changes));
}
