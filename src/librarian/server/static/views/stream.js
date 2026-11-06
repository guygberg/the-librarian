import * as api from '../api.js';
import { h } from '../dom.js';
import * as filters from '../filters.js';
import { lastImport } from '../freshness.js';
import { dateLine, shortDate } from '../format.js';

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

const evidenceLine = (e) => h('div', { class: 'evb', 'data-part': 'evidence' }, h('small', {}, e.locator), e.quote);

function row(item, evidence) {
  const [cls, label] = BASIS[item.basis] ?? [null, item.basis];
  const who = owner(item);
  const due = item.stated_deadline ? ` · due ${item.stated_deadline}` : '';
  return h('div', { class: 'it', 'data-part': 'item' },
    h('div', { class: 't' }, item.title),
    h('div', { class: 'm' },
      h('span', {}, item.projects.map((p) => p.title).join(', ')),
      h('span', {}, who + due),
      h('span', { class: cls, 'data-part': `basis-${item.basis}` }, label),
      warnings(item).map((w) => h('span', { class: 'w', 'data-part': 'warning' }, w))),
    evidence.filter((e) => e.record_id === item.id).map(evidenceLine));
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

function headline(text) {
  const [before, after] = text.split('need you');
  return h('h1', { 'data-part': 'headline' }, before, h('em', {}, 'need you'), after);
}

function progress({ done_this_week: done, total }) {
  const width = total ? Math.round((done / total) * 100) : 0;
  return [
    h('div', { class: 'bar', 'data-part': 'progress-line' }, h('i', { style: `width:${width}%` })),
    h('div', { class: 'barl' }, `${done} of ${total} items finished this week`),
  ];
}

/** The open items in their three groups. */
function groups(items, answer, evidence) {
  const of = (group) => items.filter((r) => r.group === group);
  const section = (title, list) => [h('div', { class: 'grp', 'data-part': 'group' }, title), list.map((i) => row(i, evidence))];
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
      ? h('details', { 'data-part': 'other-open' },
        h('summary', { class: 'grp', 'data-part': 'group' }, `Other open`), other.map((i) => row(i, evidence)))
      : null,
  ];
}

/** The single stream: headline, progress, filters (all in the URL) and the items they leave. */
export async function stream() {
  const state = filters.current();
  const [answer, status] = await Promise.all([api.get('/api/open-items?scope=all'), api.get('/api/status')]);
  const header = state.project ? await statusHeader(state.project) : null;
  const shown = answer.records.filter((r) => filters.matches(r, state));
  const evidence = state.kind === 'done' ? answer.evidence : [];
  const hasOwner = answer.records.filter((r) => ownerName(r));

  return h('div', {},
    h('div', { class: 'date', 'data-part': 'date-line' }, `${dateLine(new Date())} · ${status.workspace}`),
    headline(answer.headline.text),
    progress(answer.progress),
    filters.chips(answer.projects, state),
    header,
    filters.tabs(state),
    filters.people(hasOwner.map(ownerName), answer.records.map(filters.waitingOn), state),
    state.kind === 'items'
      ? groups(shown, answer, evidence)
      : shown.length
        ? shown.map((i) => row(i, evidence))
        : h('p', { class: 'empty', 'data-part': 'empty' }, 'Nothing here.'));
}
