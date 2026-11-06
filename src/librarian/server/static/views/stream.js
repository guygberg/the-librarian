import * as api from '../api.js';
import { h } from '../dom.js';
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

function owner(item) {
  if (item.owner_is_me) return 'Yours';
  const suggested = (item.suggested ?? []).some((s) => s.link === 'owner' && s.kind === UNKNOWN_SPEAKER);
  return !item.owner || suggested ? 'No owner' : item.owner;
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

function row(item) {
  const [cls, label] = BASIS[item.basis] ?? [null, item.basis];
  const who = owner(item);
  const due = item.stated_deadline ? ` · due ${item.stated_deadline}` : '';
  return h('div', { class: 'it', 'data-part': 'item' },
    h('div', { class: 't' }, item.title),
    h('div', { class: 'm' },
      h('span', {}, item.projects.map((p) => p.title).join(', ')),
      h('span', {}, who + due),
      h('span', { class: cls, 'data-part': `basis-${item.basis}` }, label),
      warnings(item).map((w) => h('span', { class: 'w', 'data-part': 'warning' }, w))));
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

/** The single stream: headline, progress and the three groups of open items. */
export async function stream() {
  const [answer, status] = await Promise.all([api.get('/api/open-items'), api.get('/api/status')]);
  const of = (group) => answer.records.filter((r) => r.group === group);
  const section = (title, items) => [h('div', { class: 'grp', 'data-part': 'group' }, title), items.map(row)];
  const needs = of(NEEDS);
  const waiting = of(WAITING);
  const other = of(OTHER);

  return h('div', {},
    h('div', { class: 'date', 'data-part': 'date-line' }, `${dateLine(new Date())} · ${status.workspace}`),
    headline(answer.headline.text),
    progress(answer.progress),
    needs.length
      ? section('Needs attention', needs)
      : [h('div', { class: 'grp', 'data-part': 'group' }, 'Needs attention'),
        h('p', { class: 'empty', 'data-part': 'empty' }, `Nothing needs you today. ${lastImport(answer.freshness)}`)],
    waiting.length ? section('Waiting on others', waiting) : null,
    other.length
      ? h('details', { 'data-part': 'other-open' },
        h('summary', { class: 'grp', 'data-part': 'group' }, `Other open`), other.map(row))
      : null);
}
