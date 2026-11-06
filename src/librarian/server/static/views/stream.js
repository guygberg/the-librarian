import * as api from '../api.js';
import { h } from '../dom.js';
import * as filters from '../filters.js';
import { lastImport } from '../freshness.js';
import { dateLine, shortDate } from '../format.js';
import { justActed } from '../actions.js';
import { evidenceLine, panel } from './expanded.js';
import * as relations from './graph.js';

/** What the last action changed (see actions.js), so the matching parts settle on this one render. */
let acted = null;

const NEEDS = 'needs_attention';
const WAITING = 'waiting_on_others';
const OTHER = 'other_open';

const UNKNOWN_SPEAKER = 'unknown_speaker';
const UNCONFIRMED_PERSON = 'unconfirmed_person';

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
  for (const s of item.suggested ?? []) {
    if (s.link === 'owner' && [UNKNOWN_SPEAKER, UNCONFIRMED_PERSON].includes(s.kind)) out.push(s.mark);
  }
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
    h('div', { class: 'm' },
      h('span', {}, item.projects.map((p) => p.title).join(', ')),
      h('span', {}, who + due),
      h('span', { class: cls, 'data-part': `basis-${item.basis}` }, label),
      warnings(item).map((w) => h('span', { class: 'w', 'data-part': 'warning' }, w))),
    expanded ? panel(open.record, open.tab, open) : evidence.filter((e) => e.record_id === item.id).map((e) => evidenceLine(e)));
}

const fact = (label, f) => (f && f !== 'not found' ? h('div', { class: 'm' }, h('span', {}, label), h('span', {}, f.title ?? f.value)) : null);

/** What a selected project stands at, and what changed since the last meeting. */
async function statusHeader(name) {
  const [{ project, resolved }, changes] = await Promise.all([
    api.get(`/api/project?name=${encodeURIComponent(name)}`),
    api.get(`/api/changes?project=${encodeURIComponent(name)}`),
  ]);
  if (!resolved.project) return null;
  return h('div', { class: 'sh', 'data-part': 'status-header' },
    h('div', { class: 't' }, resolved.project.name),
    fact('Status', project.status),
    fact('Blocker', project.main_blocker),
    fact('Latest decision', project.latest_decision),
    h('div', { class: 'm', 'data-part': 'changes' },
      h('span', {}, `${changes.changes.length} changed`), h('span', {}, changes.resolved.baseline)));
}

// Finishing or reopening work moves the counts; they settle once, with no sound.
const countsMoved = () => ['done', 'reopen'].includes(acted?.name);

function headline(text) {
  const [before, after] = text.split('need you');
  return h('h1', { 'data-part': 'headline', class: countsMoved() ? 'settle' : null }, before, h('em', {}, 'need you'), after);
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

/** The single stream: headline, progress, filters (all in the URL) and the items they leave. */
export async function stream() {
  const state = filters.current();
  acted = justActed();
  const [answer, status] = await Promise.all([api.get('/api/open-items?scope=all'), api.get('/api/status')]);
  const header = state.project ? await statusHeader(state.project) : null;
  const shown = answer.records.filter((r) => filters.matches(r, state));
  const evidence = state.kind === 'done' ? answer.evidence : [];
  const hasOwner = answer.records.filter((r) => ownerName(r));
  const graphState = state.open && state.tab === 'relations' ? relations.params(state.open) : null;
  const open = state.open
    ? {
      record: (await api.get(`/api/record?id=${state.open}`)).record, tab: state.tab, people: answer.people, projects: answer.projects,
      graphState, graph: graphState && await api.get(relations.query(graphState)),
    }
    : null;
  // An expanded item the filters would hide still shows, above the list.
  const stray = open && !shown.some((r) => r.id === open.record.id) ? row(open.record, [], open) : null;

  return h('div', {},
    h('div', { class: 'date', 'data-part': 'date-line' }, `${dateLine(new Date())} · ${status.workspace}`),
    headline(answer.headline.text),
    progress(answer.progress),
    filters.chips(answer.projects, state),
    header,
    filters.tabs(state),
    filters.people(hasOwner.map(ownerName), answer.records.map(filters.waitingOn), state),
    stray,
    state.kind === 'items'
      ? groups(shown, answer, evidence, open)
      : shown.length
        ? shown.map((i) => row(i, evidence, open))
        : h('p', { class: 'empty', 'data-part': 'empty' }, 'Nothing here.'));
}
