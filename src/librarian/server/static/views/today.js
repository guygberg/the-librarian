import { itemForm, priorityBadge } from '../entities.js';
import { justActed } from '../actions.js';
import * as api from '../api.js';
import { h } from '../dom.js';
import { clock, isToday, parseLocal, shortDate } from '../format.js';
import { href } from '../filters.js';
import { lastImport, openDialog } from '../shell.js';
import { NEEDS, WAITING, btn, emblem, first, icon } from '../ui.js';
import { assign, blurb, complete } from './common.js';

const when = (iso) => {
  const at = new Date(iso);
  return isToday(at) ? clock(at) : `${shortDate(at)} ${clock(at)}`;
};

function greeting() {
  const hour = new Date().getHours();
  return hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
}

function flag(item) { return item ? priorityBadge(item) : null; }

function hero(needs, people, calm) {
  const [next] = needs;
  return h('section', { class: 'panel accent today-hero', 'data-part': 'next-best-move' }, emblem('cube'),
    h('div', { class: 'grow' },
      h('div', { class: 'today-hero-label' }, h('div', { class: 'eyebrow' }, 'NEXT BEST MOVE'), flag(next)),
      h('h2', { 'data-part': 'next-title' }, next ? next.title : 'You’re all caught up'),
      h('p', { 'data-part': 'next-why' }, next ? blurb(next) : calm)),
    next ? h('div', { class: 'actions' },
      btn('Open item', { href: href({ open: next.id }), 'data-part': 'next-open' }),
      btn([icon('check'), 'Mark done'], { cls: 'primary', onClick: () => complete(next), 'data-part': 'next-done' }),
      !next.is_tag
        ? btn([icon('user'), 'Assign to…', icon('down', 'small')], { onClick: () => assign(next, people), 'data-part': 'next-assign' })
        : null) : null);
}

/** One of the three cards under the hero: it shows one entry at a time, and its arrows redraw only the card. */
function carousel({ part, title, glyph, list, all, entry, calm }) {
  const host = h('section', {});
  let at = 0;
  const draw = () => {
    at = list.length ? (at + list.length) % list.length : 0;
    const shown = list.length ? entry(list[at]) : null;
    const step = (dir, name, label) => btn(icon(name), { cls: 'round', disabled: list.length < 2, 'aria-label': `${label} ${title}`,
      'data-part': `${part}-${dir < 0 ? 'prev' : 'next'}`, onClick: () => { at += dir; draw(); } });
    host.className = shown?.to ? 'panel carousel clickable-ticket' : 'panel carousel';
    for (const [name, value] of [['data-part', part], ['data-href', shown?.to ?? null]]) {
      if (value) host.setAttribute(name, value); else host.removeAttribute(name);
    }
    host.replaceChildren(
      h('div', { class: 'row' }, icon(glyph), title, h('span', { class: 'counter', 'data-part': `${part}-count` }, String(list.length)),
        btn(icon('more'), { cls: 'textbtn', href: all, 'aria-label': `View ${title}` })),
      h('div', { class: 'today-ticket-heading' },
        h('h2', {}, shown
          ? (shown.to ? h('a', { class: 'today-ticket-link', href: shown.to, 'data-link': true, 'data-part': 'today-item' }, shown.title) : shown.title)
          : 'All clear'),
        shown?.flag),
      h('p', shown ? {} : { 'data-part': 'empty' }, shown ? shown.text : calm),
      h('div', { class: 'carousel-controls' }, step(-1, 'back', 'Previous'), shown ? shown.action : btn([icon('check'), 'Done'], { cls: 'primary', disabled: true }), step(1, 'chevron', 'Next')),
      h('div', { class: 'carousel-index', 'data-part': `${part}-range` }, `${list.length ? at + 1 : 0} of ${list.length}`));
  };
  draw();
  return host;
}

const itemEntry = (item) => ({
  title: item.title, to: href({ open: item.id }), flag: flag(item),
  text: blurb(item),
  action: btn([icon('check'), 'Done'], { cls: 'primary', onClick: () => complete(item), 'data-part': 'today-done' }),
});

const reviewEntry = (row) => ({
  title: row.record.title, to: null, flag: null,
  text: `${row.mark.replace(/^./, (c) => c.toUpperCase())}${row.raw_name ? ` · “${row.raw_name}”` : ''}`,
  action: btn([icon('spark'), 'Review'], { cls: 'primary', href: '/review', 'data-part': 'today-review' }),
});

const EVENT_ICONS = { done: 'check', reopen: 'reset', owner: 'user', project: 'tag', resolve: 'sliders', accept: 'spark', reject: 'close' };
const label = (event) => event.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());

/** What the person and Import changed since the last meeting; nothing invented when it was quiet. */
function activity(changes, freshness) {
  const titles = new Map(changes.records.map((r) => [r.id, r.title]));
  const imported = changes.changes.filter((c) => c.import);
  const made = imported.filter((c) => c.import === 'created').length;
  const at = freshness.last_import_finished_at ? parseLocal(freshness.last_import_finished_at) : null;
  const rows = [
    ...changes.person_events.map((e) => ({ part: 'person-event', icon: EVENT_ICONS[e.event] ?? 'doc', actor: 'You', time: when(e.at),
      text: `${label(e.event)} · ${titles.get(e.record_id) ?? 'an item'}` })),
    ...(imported.length ? [{ part: 'import-change', icon: 'download', actor: 'System', time: at ? when(at) : '',
      text: `Imported ${made} new, ${imported.length - made} updated` }] : []),
  ];
  const line = (r) => h('div', { class: 'activity-row', 'data-part': r.part }, icon(r.icon), h('span', {}, r.text),
    h('span', { class: 'actor' }, r.actor), h('time', {}, r.time));
  const body = h('div', { 'data-part': 'activity-rows' });
  const tabs = h('div', { class: 'tabs' });
  let tab = 'All';
  const of = () => rows.filter((r) => tab === 'All' || r.actor === tab);
  const draw = () => {
    tabs.replaceChildren(...['All', 'You', 'System'].map((t) => btn(t, { cls: tab === t ? 'tab active' : 'tab', 'data-part': 'activity-tab', onClick: () => { tab = t; draw(); } })));
    const shown = of().slice(0, 5);
    body.replaceChildren(...(shown.length ? shown.map(line) : [h('p', { class: 'empty', 'data-part': 'empty' }, 'Nothing has changed in that time.')]));
  };
  draw();
  return h('section', { class: 'panel activity', 'data-part': 'activity' },
    h('div', { class: 'panel-heading' }, h('h2', {}, 'Activity log'), h('p', { 'data-part': 'activity-baseline' }, changes.resolved.baseline ?? 'Everything that happened'), tabs,
      btn(['View all ', icon('arrow', 'small')], { cls: 'textbtn', 'data-part': 'activity-all',
        onClick: () => openDialog('Activity log', h('div', { style: 'max-height:65vh;overflow:auto' }, of().length ? of().map(line) : h('p', { class: 'empty' }, 'No activity yet.'))) })),
    body);
}

function completedPanel(done) {
  const shown = done.slice(0, 3);
  const today = done.filter((i) => isToday(new Date(i.done_at)));
  const allToday = shown.length > 0 && shown.every((i) => isToday(new Date(i.done_at)));
  return h('section', { class: 'panel completed-panel', 'data-part': 'completed' },
    h('div', { class: 'panel-heading' },
      h('h2', {}, allToday || !shown.length ? 'Today’s completed tasks' : 'Recently completed'),
      h('p', { 'data-part': 'completed-count' }, `${today.length} completed · +${today.length * 20} XP`),
      btn(['Open archive ', icon('arrow', 'small')], { cls: 'textbtn', href: href({ kind: 'done', group: null }), style: 'margin-left:auto', 'data-part': 'open-archive' })),
    h('div', { class: 'completed-grid' }, shown.length
      ? shown.map((i, n) => h('div', { class: 'completed-card', 'data-part': 'completed-item' },
        h('div', { class: 'medal' }, emblem(['chip', 'cube', 'rings'][n])),
        h('div', {}, btn(i.title, { cls: 'item-title', href: href({ open: i.id }) }),
          h('p', { 'data-part': 'completed-at' }, `Completed at ${when(i.done_at)}`))))
      : h('p', { class: 'empty', 'data-part': 'empty' }, 'Your completed items will appear here.')));
}

/** The Today dashboard: every number and list comes from the open-items, review and changes answers. */
export async function today() {
  const acted = justActed();
  const settled = ['done', 'reopen'].includes(acted?.name);
  const [answer, review, changes] = await Promise.all([
    api.get('/api/open-items?scope=all'), api.get('/api/review'), api.get('/api/changes')]);
  const of = (group) => answer.records.filter((r) => r.group === group && !r.parent_id);
  const needs = of(NEEDS);
  const waiting = of(WAITING);
  const openCount = answer.records.filter((r) => r.group && !r.parent_id).length;
  const completed = answer.records
    .filter((r) => r.lifecycle === 'done' && r.done_at)
    .sort((a, b) => b.done_at.localeCompare(a.done_at));
  const calm = `Nothing needs you today. ${lastImport(answer.freshness)}`;
  const me = first(answer.people.find((p) => p.is_me)?.name);
  const count = (part, n, text) => h('span', { 'data-part': part }, h('b', {}, String(n)), ` ${text}`);

  return h('section', { class: 'today', 'data-part': 'today' },
    h('div', { class: 'greeting' },
      h('h1', {}, `${greeting()}${me ? `, ${me}` : ''}.`),
      h('p', { class: settled ? 'settle' : null, 'data-part': 'counts' },
        count('count-open', openCount, openCount === 1 ? 'open item' : 'open items'), ' · ',
        count('count-needs', needs.length, needs.length === 1 ? 'needs you' : 'need you'), ' · ',
        count('count-waiting', waiting.length, 'waiting on others'), ' · ',
        count('count-review', review.count, 'suggestions')),
      btn([icon('plus'), 'New item'], { cls: 'primary', onClick: () => itemForm(), 'data-part': 'today-new' })),
    hero(needs, answer.people, calm),
    h('div', { class: settled ? 'carousel-grid settle' : 'carousel-grid' },
      carousel({ part: 'needs', title: 'Needs you', glyph: 'target', list: needs, all: href({ group: 'needs', kind: 'items' }), entry: itemEntry, calm }),
      carousel({ part: 'waiting', title: 'Waiting on others', glyph: 'hourglass', list: waiting, all: href({ group: 'waiting', kind: 'items' }), entry: itemEntry,
        calm: 'Nothing is waiting on someone else.' }),
      carousel({ part: 'review', title: 'Suggestions', glyph: 'spark', list: review.rows, all: '/review', entry: reviewEntry, calm: 'Nothing to review.' })),
    activity(changes, answer.freshness),
    completedPanel(completed));
}
