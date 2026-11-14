import { change, justActed } from '../actions.js';
import * as api from '../api.js';
import { h } from '../dom.js';
import * as filters from '../filters.js';
import { btn, icon, pageHead } from '../ui.js';
import { aliasControls } from './alias.js';
import { evidenceLine } from './evidence.js';

const PEOPLE = 'unconfirmed_person';
const INFERRED = 'inferred_project';
const SUGGESTED = 'suggested_project';
const MERGE = 'merge_project';

const itemHref = (r) => filters.href({ open: r.id });

/** What Accept does for each kind of doubt, as `[path, body]`. A speaker is settled from the item itself. */
function accepts(row) {
  const record = row.record.id;
  switch (row.kind) {
    case INFERRED: return [`/api/projects/${record}/confirm`, {}];
    case MERGE: return [`/api/projects/${record}/merge`, { into: row.other.id }];
    case SUGGESTED: return [`/api/items/${record}/project`, { project_id: row.other.id }];
    default: return null;
  }
}

function actions(row, people, failed) {
  const record = row.record.id;
  const settle = (path, name, body) => () => change(path, name, record, body, failed);
  if (row.kind === PEOPLE) {
    const accept = `/api/review/${row.id}/accept`;
    return [
      row.candidates.map((c) => h('div', { class: 'row candidate', 'data-part': 'candidate' },
        btn([icon('spark'), `Accept as ${c.name}`], { cls: 'primary', onClick: settle(accept, 'accept', { person_id: c.id }), 'data-part': 'review-accept' }),
        aliasControls({ alias: () => c.alias, from: c.id, recordId: record, people }))),
      h('div', { class: 'row' },
        btn('Dismiss', { onClick: settle(`/api/review/${row.id}/reject`, 'reject', {}), 'data-part': 'review-reject' }),
        btn('Accept as a new person', { onClick: settle(accept, 'accept', {}), 'data-part': 'review-accept-new' })),
    ];
  }
  const accept = accepts(row);
  return accept
    ? h('div', { class: 'row' }, btn([icon('spark'), 'Accept'], { cls: 'primary', onClick: settle(accept[0], 'accept', accept[1]), 'data-part': 'review-accept' }))
    : h('p', { class: 'small' }, 'Set the speaker on the item itself.');
}

/** Why the Librarian is asking, in the person's words. A suggestion stays a suggestion until Accept. */
const REASONS = {
  [PEOPLE]: (row) => `"${row.raw_name}" may be a person already known; nothing is assigned until you accept.`,
  [INFERRED]: () => 'The Librarian inferred this project from the sources; it is not confirmed.',
  [SUGGESTED]: () => 'The Librarian suggests moving this item into the project below.',
  [MERGE]: () => 'These two projects look like one; nothing merges until you accept.',
  unknown_speaker: () => 'The speaker was not recognised, so the item has no confirmed owner.',
};

function reviewCard(row, people) {
  const failed = h('p', { class: 'w', 'data-part': 'review-error' });
  const to = row.record.is_tag ? `/projects?project=${encodeURIComponent(row.record.title)}` : itemHref(row.record);
  return h('article', { class: 'panel person-card review-card', 'data-part': 'review-row', 'data-kind': row.kind },
    h('div', { class: 'row gold' }, icon('spark'), h('span', { class: 'eyebrow', 'data-part': 'review-mark' }, row.mark),
      row.raw_name ? h('span', { class: 'tagchip' }, `"${row.raw_name}"`) : null,
      h('span', { class: 'tagchip basis inf', 'data-part': 'review-basis' }, `Basis: ${row.record.basis ?? 'unknown'}`)),
    h('h3', { style: 'margin-top:15px' }, row.record.title),
    h('p', { style: 'margin:5px 0 12px', 'data-part': 'review-reason' }, (REASONS[row.kind] ?? (() => 'Needs your decision.'))(row)),
    row.other ? h('p', { class: 'small', 'data-part': 'review-other' }, 'and ', btn(row.other.title, { cls: 'textbtn', href: itemHref(row.other) })) : null,
    row.record.evidence.map((e) => evidenceLine(e, true)),
    h('div', { class: 'review-actions' },
      btn([row.record.is_tag ? 'View project ' : 'View item ', icon('arrow', 'small')], { cls: 'textbtn', href: to, 'data-part': 'review-view' }),
      h('div', { class: 'stack acts' }, actions(row, people, failed))),
    failed);
}

/** Every Suggested link and inferred project awaiting a decision, with both sides and the Evidence. */
export async function review() {
  const settled = justActed();
  const [{ count, rows }, { people }] = await Promise.all([api.get('/api/review'), api.get('/api/open-items?scope=all')]);
  return h('div', { 'data-part': 'review' },
    pageHead('Suggestions', h('span', {}, 'Small steps. A clearer workspace. ', h('span', { 'data-part': 'review-count' }, `${count} to review`)), 'cube'),
    h('div', { class: settled ? 'cards settle' : 'cards' }, rows.map((row) => reviewCard(row, people))),
    rows.length ? null : h('div', { class: 'panel empty', 'data-part': 'empty' }, h('h2', {}, 'All caught up.'), h('p', {}, 'Nothing to review.')));
}
