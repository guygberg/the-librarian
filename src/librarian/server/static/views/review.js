import { change, justActed } from '../actions.js';
import * as api from '../api.js';
import { h } from '../dom.js';
import * as filters from '../filters.js';
import { evidenceLine } from './expanded.js';
import { aliasControls } from './alias.js';
import { suggestionCard } from './suggestion-card.js';

const PEOPLE = 'unconfirmed_person';
const INFERRED = 'inferred_tag';
const SUGGESTED = 'suggested_tag';
const MERGE = 'merge_tag';

const itemLink = (r) => h('a', { href: filters.href({ open: r.id }), 'data-link': true }, r.title);

/** What Accept does for each kind of doubt, as `[path, body]`. A speaker is settled from the item itself. */
function accepts(row) {
  const record = row.record.id;
  switch (row.kind) {
    case INFERRED: return [`/api/tags/${record}/confirm`, {}];
    case MERGE: return [`/api/tags/${record}/merge`, { into: row.other.id }];
    case SUGGESTED: return [`/api/records/${record}/tag`, { tag_id: row.other.id }];
    default: return null;
  }
}

function button(part, text, onClick) {
  const el = h('button', { type: 'button', class: 'chip', 'data-part': part }, text);
  el.addEventListener('click', onClick);
  return el;
}

function actions(row, people, failed) {
  const record = row.record.id;
  const settle = (path, name, body) => () => change(path, name, record, body, failed);
  if (row.kind === PEOPLE) {
    const accept = `/api/review/${row.id}/accept`;
    return [
      row.candidates.map((c) => h('div', { class: 'm', 'data-part': 'candidate' },
        button('review-accept', `Accept as ${c.name}`, settle(accept, 'accept', { person_id: c.id })),
        aliasControls({ alias: () => c.alias, from: c.id, recordId: record, people }))),
      button('review-accept-new', 'Accept as a new person', settle(accept, 'accept', {})),
      button('review-reject', 'Reject', settle(`/api/review/${row.id}/reject`, 'reject', {})),
    ];
  }
  const accept = accepts(row);
  return accept
    ? button('review-accept', 'Accept', settle(accept[0], 'accept', accept[1]))
    : h('small', {}, 'Set the speaker on the item itself.');
}

/** Why the Librarian is asking, in the person's words. A suggestion stays a suggestion until Accept. */
const REASONS = {
  [PEOPLE]: (row) => `"${row.raw_name}" may be a person already known; nothing is assigned until you accept.`,
  [INFERRED]: () => 'The Librarian inferred this tag from the sources; it is not confirmed.',
  [SUGGESTED]: () => 'The Librarian suggests moving this item into the tag below.',
  [MERGE]: () => 'These two tags look like one; nothing merges until you accept.',
  unknown_speaker: () => 'The speaker was not recognised, so the item has no confirmed owner.',
};

function reviewRow(row, people) {
  const failed = h('p', { class: 'w', 'data-part': 'review-error' });
  return h('div', { class: 'sg legacy', 'data-part': 'review-row', 'data-kind': row.kind },
    h('div', { class: 'm' }, h('span', { class: 'w', 'data-part': 'review-mark' }, row.mark), row.raw_name ? h('span', {}, `"${row.raw_name}"`) : null,
      h('span', { 'data-part': 'review-basis' }, `Basis: ${row.record.basis ?? 'unknown'}`)),
    h('p', { class: 'pnote', 'data-part': 'review-reason' }, (REASONS[row.kind] ?? (() => 'Needs your decision.'))(row)),
    h('div', { class: 't' }, itemLink(row.record)),
    row.other ? h('div', { class: 'm', 'data-part': 'review-other' }, h('span', {}, 'and'), itemLink(row.other)) : null,
    row.record.evidence.map((e) => evidenceLine(e, true)),
    h('div', { class: 'acts' }, actions(row, people, failed)),
    failed);
}

const BANDS = ['high', 'medium', 'low'];
const SORTS = [['confidence', 'Confidence'], ['newest', 'Newest']];

/** Band and sort live in the URL like every other filter; an unknown value is the default. */
function chosen() {
  const q = new URLSearchParams(location.search);
  const band = q.get('band');
  const sort = q.get('sort');
  return { band: BANDS.includes(band) ? band : null, sort: SORTS.some(([k]) => k === sort) ? sort : 'confidence' };
}

function query(state) {
  const q = new URLSearchParams();
  if (state.band) q.set('band', state.band);
  if (state.sort !== 'confidence') q.set('sort', state.sort);
  return q.size ? `?${q}` : '';
}

const chip = (text, href, on, part) => h('a', { href, class: on ? 'chip on' : 'chip', 'aria-current': on ? 'true' : null, 'data-link': true, 'data-part': part }, text);

function controls(state) {
  return h('div', { class: 'sg-controls', 'data-part': 'suggestion-controls' },
    h('div', { class: 'pf', role: 'group', 'aria-label': 'Confidence', 'data-part': 'band-filter' },
      chip('All', `/review${query({ ...state, band: null })}`, !state.band, 'band-chip'),
      BANDS.map((b) => chip(b[0].toUpperCase() + b.slice(1), `/review${query({ ...state, band: b })}`, state.band === b, 'band-chip'))),
    h('div', { class: 'pf', role: 'group', 'aria-label': 'Sort', 'data-part': 'sort-filter' },
      SORTS.map(([k, text]) => chip(text, `/review${query({ ...state, sort: k })}`, state.sort === k, 'sort-chip'))));
}

const SVG = 'http://www.w3.org/2000/svg';

/** The lime hexagon beside the page title, as in the canonical composition. */
function hero() {
  const svg = document.createElementNS(SVG, 'svg');
  svg.setAttribute('class', 'sg-hero');
  svg.setAttribute('viewBox', '0 0 80 80');
  svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(SVG, 'path');
  path.setAttribute('d', 'M40 4 72 22v36L40 76 8 58V22L40 4ZM40 4v72M8 22l64 36M72 22 8 58M8 22h64M8 58h64');
  svg.append(path);
  return svg;
}

/** Every Suggestion and doubt awaiting a decision: Suggestions as graded cards, the rest with both sides and Evidence. */
export async function review() {
  const settled = justActed();
  const state = chosen();
  const [{ count, rows }, { people }] = await Promise.all([api.get(`/api/review${query(state)}`), api.get('/api/open-items?scope=all')]);
  return h('div', { 'data-part': 'review' },
    h('header', { class: 'sg-head' }, hero(), h('div', {}, h('h1', {}, 'Suggestions'), h('p', {}, 'Small steps. A clearer workspace.'))),
    controls(state),
    h('div', { class: 'grp', 'data-part': 'review-count' }, `${count} to review`),
    h('div', { class: settled ? 'sgrid settle' : 'sgrid' },
      rows.length ? [...rows.filter((r) => r.type === 'suggestion').map(suggestionCard), ...rows.filter((r) => r.type !== 'suggestion').map((r) => reviewRow(r, people))] : h('p', { class: 'empty', 'data-part': 'empty' }, 'Nothing to review.')));
}
