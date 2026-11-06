import { change, justActed } from '../actions.js';
import * as api from '../api.js';
import { h } from '../dom.js';
import * as filters from '../filters.js';
import { evidenceLine } from './expanded.js';
import { aliasControls } from './alias.js';

const PEOPLE = 'unconfirmed_person';
const INFERRED = 'inferred_project';
const SUGGESTED = 'suggested_project';
const MERGE = 'merge_project';

const itemLink = (r) => h('a', { href: filters.href({ open: r.id }), 'data-link': true }, r.title);

/** What Accept does for each kind of doubt, as `[path, body]`. A speaker is settled from the item itself. */
function accepts(row) {
  const record = row.record.id;
  switch (row.kind) {
    case INFERRED: return [`/api/projects/${record}/confirm`, {}];
    case MERGE: return [`/api/projects/${record}/merge`, { into: row.other.id }];
    case SUGGESTED: return [`/api/records/${record}/project`, { project_id: row.other.id }];
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

function reviewRow(row, people) {
  const failed = h('p', { class: 'w', 'data-part': 'review-error' });
  return h('div', { class: 'it', 'data-part': 'review-row', 'data-kind': row.kind },
    h('div', { class: 'm' }, h('span', { class: 'w', 'data-part': 'review-mark' }, row.mark), row.raw_name ? h('span', {}, `"${row.raw_name}"`) : null),
    h('div', { class: 't' }, itemLink(row.record)),
    row.other ? h('div', { class: 'm', 'data-part': 'review-other' }, h('span', {}, 'and'), itemLink(row.other)) : null,
    row.record.evidence.map((e) => evidenceLine(e, true)),
    h('div', { class: 'acts' }, actions(row, people, failed)),
    failed);
}

/** Every Suggested link and inferred project awaiting a decision, with both sides and the Evidence. */
export async function review() {
  const settled = justActed();
  const [{ count, rows }, { people }] = await Promise.all([api.get('/api/review'), api.get('/api/open-items?scope=all')]);
  return h('div', { 'data-part': 'review' },
    h('div', { class: 'grp', 'data-part': 'review-count' }, `${count} to review`),
    h('div', { class: settled ? 'settle' : null },
      rows.length ? rows.map((row) => reviewRow(row, people)) : h('p', { class: 'empty', 'data-part': 'empty' }, 'Nothing to review.')));
}
