import * as api from '../api.js';
import { h } from '../dom.js';
import * as filters from '../filters.js';
import { lastImport } from '../freshness.js';
import { dateLine, shortDate } from '../format.js';
import { justActed } from '../actions.js';
import { evidenceLine, panel } from './expanded.js';
import * as relations from './graph.js';
import { tagTools } from './tag-tools.js';

/** What the last action changed (see actions.js), so the matching parts settle on this one render. */
let acted = null;

const NEEDS = 'needs_attention';
const WAITING = 'waiting_on_others';
const OTHER = 'other_open';

const UNKNOWN_SPEAKER = 'unknown_speaker';

const BASIS = {
  inferred: ['inf', 'Inferred'],
  confirmed: ['conf', 'Confirmed'],
  stated: [null, 'Stated'],
};

/** The owner's name, or null when the owner is only a guess from an unknown speaker. */
function ownerName(item) {
  const suggested = (item.suggested ?? []).some((s) => s.link === 'owner' && s.kind === UNKNOWN_SPEAKER);
  return suggested ? null : item.owner ?? null;
}

function owner(item) {
  if (item.owner_is_me) return 'Yours';
  return ownerName(item) ?? 'No owner';
}

function warnings(item) {
  const out = [];
  if (item.contradictions.length) out.push('Sources disagree');
  if (item.transcription_uncertain) out.push('Transcription uncertain');
  if (item.stale && item.last_evidence) out.push(`Not mentioned since ${shortDate(new Date(item.last_evidence))}`);
  for (const s of item.suggested ?? []) out.push(s.mark);
  return out;
}

/** `open` is the expanded Record (its full view) and its tab; its row grows a panel, the others link to their own URL. */
function row(item, evidence, open) {
  const [cls, label] = BASIS[item.basis] ?? [null, item.basis];
  const who = owner(item);
  const due = item.stated_deadline ? ` · due ${item.stated_deadline}` : '';
  const expanded = open?.record.id === item.id;
  return h('div', { class: acted?.id === item.id ? 'it settle' : 'it', 'data-part': 'item' },
    h('div', { class: 't' }, h('a', { href: filters.href({ open: expanded ? null : item.id }), 'data-link': true }, item.title)),
    item.body ? h('p', { class: 'sum', 'data-part': 'summary' }, item.body) : null,
    h('div', { class: 'm' },
      h('span', {}, item.tags.flatMap((p, i) => [i ? ', ' : '', h('a', { href: `/tags?tag=${encodeURIComponent(p.title)}`, 'data-link': true, 'data-part': 'row-tag' }, p.title)])),
      h('span', { 'data-part': 'row-kind' }, item.kind.replace('_', ' ')),
      h('span', { 'data-part': 'row-lifecycle' }, item.lifecycle),
      h('span', {}, ownerName(item) && !item.owner_is_me
        ? h('a', { href: `/people?person=${encodeURIComponent(who)}`, 'data-link': true, 'data-part': 'row-owner' }, who)
        : who, due),
      item.last_evidence ? h('span', { 'data-part': 'updated' }, `Updated ${shortDate(new Date(item.last_evidence))}`) : null,
      h('span', { class: cls, 'data-part': `basis-${item.basis}` }, label),
      warnings(item).map((w) => h('span', { class: 'w', 'data-part': 'warning' }, w))),
    expanded ? panel(open.record, open.tab, open) : evidence.filter((e) => e.record_id === item.id).map((e) => evidenceLine(e)));
}

const fact = (label, f) => (f && f !== 'not found' ? h('div', { class: 'm' }, h('span', {}, label), h('span', {}, f.title ?? f.value)) : null);

/** What a selected tag stands at, and what changed since the last meeting. */
async function statusHeader(name, tags, items) {
  const [{ tag, resolved }, changes] = await Promise.all([
    api.get(`/api/tag?name=${encodeURIComponent(name)}`),
    api.get(`/api/changes?tag=${encodeURIComponent(name)}`),
  ]);
  if (!resolved.tag) return null;
  return h('div', { class: 'sh', 'data-part': 'status-header' },
    h('div', { class: 't' }, resolved.tag.name),
    tagTools(resolved.tag, tags, items),
    fact('Status', tag.status),
    fact('Blocker', tag.main_blocker),
    fact('Latest decision', tag.latest_decision),
    h('div', { class: 'm', 'data-part': 'changes' },
      h('span', {}, `${changes.changes.length} changed`), h('span', {}, changes.resolved.baseline)));
}

// Finishing or reopening work moves the counts; they settle once, with no sound.
const countsMoved = () => ['done', 'reopen'].includes(acted?.name);

function headline(text) {
  const [, before, verb, after] = text.match(/^(.*?)(needs? you)(.*)$/);
  return h('h1', { 'data-part': 'headline', class: countsMoved() ? 'settle' : null }, before, h('em', {}, verb), after);
}

function progress({ done_this_week: done, total }) {
  const width = total ? Math.round((done / total) * 100) : 0;
  return [
    h('div', { class: 'bar', 'data-part': 'progress-line' }, h('i', { style: `width:${width}%` })),
    h('div', { class: countsMoved() ? 'barl settle' : 'barl' }, `${done} of ${total} items finished this week`),
  ];
}

/** The open items in their three groups. */
function groups(items, answer, evidence, open) {
  const of = (group) => items.filter((r) => r.group === group);
  const section = (title, list) => [h('div', { class: 'grp', 'data-part': 'group' }, title), list.map((i) => row(i, evidence, open))];
  const needs = of(NEEDS);
  const waiting = of(WAITING);
  const other = of(OTHER);
  return [
    needs.length
      ? section('Needs attention', needs)
      : [h('div', { class: 'grp', 'data-part': 'group' }, 'Needs attention'),
        h('p', { class: 'empty', 'data-part': 'empty' }, `Nothing needs you today. ${lastImport(answer.freshness)}`)],
    waiting.length ? section('Waiting on others', waiting) : null,
    other.length
      ? h('details', { 'data-part': 'other-open', open: other.some((i) => i.id === open?.record.id) },
        h('summary', { class: 'grp', 'data-part': 'group' }, `Other open`), other.map((i) => row(i, evidence, open)))
      : null,
  ];
}

/** The same records in columns: the query's groups, then Done. Anything else that matched (a decision, a dropped item) is never dropped. */
function board(items, evidence, open) {
  const column = (part, title, list) => h('section', { class: 'col', 'data-part': part },
    h('div', { class: 'grp', 'data-part': 'group' }, `${title} (${list.length})`),
    list.map((i) => row(i, evidence, open)));
  const of = (group) => items.filter((r) => r.group === group);
  const done = items.filter((r) => r.group === null && r.lifecycle === 'done');
  const rest = items.filter((r) => r.group === null && r.lifecycle !== 'done');
  return h('div', { class: 'board', 'data-part': 'board' },
    column('col-needs', 'Needs attention', of(NEEDS)),
    column('col-waiting', 'Waiting on others', of(WAITING)),
    column('col-other', 'Other open', of(OTHER)),
    column('col-done', 'Done', done),
    rest.length ? column('col-rest', 'Not open', rest) : null);
}

/** What changed since the person last dismissed this strip; gone for good until something changes again. */
export function changedStrip({ last_visit: last, changed }) {
  if (!changed) return null;
  const strip = h('div', { class: 'strip', 'data-part': 'changed-strip' },
    h('span', {}, last ? `${changed} changed since your last visit` : `${changed} records so far`),
    h('button', { type: 'button', 'data-part': 'changed-dismiss' }, 'Dismiss'));
  strip.querySelector('button').addEventListener('click', async () => {
    await api.post('/api/visit/seen', {});
    strip.remove();
  });
  return strip;
}

/** The single stream: headline, progress, filters (all in the URL) and the items they leave. */
export async function stream() {
  const state = filters.current();
  acted = justActed();
  const [answer, status, visit] = await Promise.all([
    api.get('/api/open-items?scope=all'), api.get('/api/status'), api.get('/api/visit')]);
  const shown = answer.records.filter((r) => filters.matches(r, state));
  const header = state.tag ? await statusHeader(state.tag, answer.tags, shown) : null;
  const evidence = state.kind === 'done' ? answer.evidence : [];
  const hasOwner = answer.records.filter((r) => ownerName(r));
  const graphState = state.open && state.tab === 'relations' ? relations.params(state.open) : null;
  const open = state.open
    ? {
      record: (await api.get(`/api/record?id=${state.open}`)).record, tab: state.tab, people: answer.people, tags: answer.tags,
      graphState, graph: graphState && await api.get(relations.query(graphState)),
    }
    : null;
  // An expanded item the filters would hide still shows, above the list.
  const stray = open && !shown.some((r) => r.id === open.record.id) ? row(open.record, [], open) : null;

  return h('div', {},
    h('div', { class: 'date', 'data-part': 'date-line' }, `${dateLine(new Date())} · ${status.workspace}`),
    changedStrip(visit),
    headline(answer.headline.text),
    progress(answer.progress),
    filters.chips(answer.tags, state),
    header,
    filters.views(state),
    filters.tabs(state),
    filters.people(hasOwner.map(ownerName), answer.records.map(filters.waitingOn), state),
    filters.more(state),
    stray,
    state.view === 'board'
      ? board(shown, evidence, open)
      : state.kind === 'items'
        ? groups(shown, answer, evidence, open)
        : shown.length
        ? shown.map((i) => row(i, evidence, open))
        : h('p', { class: 'empty', 'data-part': 'empty' }, 'Nothing here.'));
}
