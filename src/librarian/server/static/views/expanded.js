import { h } from '../dom.js';
import * as filters from '../filters.js';
import { shortDate } from '../format.js';

const BASIS = {
  stated: 'Stated: a source says this outright.',
  inferred: 'Inferred: no source says this outright. Check the Evidence.',
  confirmed: 'Confirmed by you.',
};

const day = (iso) => shortDate(new Date(iso));

export function evidenceLine(e, withRole = false) {
  return h('div', { class: 'evb', 'data-part': 'evidence' },
    h('small', {}, withRole ? `${e.locator} · ${e.role}` : e.locator), e.quote);
}

function lifecycle(r) {
  const why = r.reason ? ` (${r.reason})` : '';
  switch (r.lifecycle) {
    case 'pending': return `Pending${filters.waitingOn(r) ? `, waiting on ${filters.waitingOn(r)}` : ''}`;
    case 'suspended': return `Suspended${r.suspended_by ? ` by ${r.suspended_by}` : ''}${why}`;
    case 'done': return `Done${r.done_at ? ` ${day(r.done_at)}` : ''}`;
    case 'dropped': return `Dropped${why}`;
    case 'superseded': return 'Superseded';
    default: return 'Open';
  }
}

const fact = (part, text) => h('div', { class: 'fact', 'data-part': part }, text);

/** The sentence under the title: what is wrong with, or worth knowing about, this Record. */
function flags(r) {
  return [
    r.no_longer_found ? fact('flag', 'No longer found in sources.') : null,
    r.stale && r.last_evidence ? fact('flag', `Stale: not mentioned in any source since ${day(r.last_evidence)}.`) : null,
  ];
}

function disagreement(r) {
  if (!r.contradictions.length) return null;
  return h('div', { class: 'dis', 'data-part': 'disagreement' },
    h('p', { class: 'w' }, 'Sources disagree'),
    [r, ...r.contradictions].map((side) => h('div', { class: 'side', 'data-part': 'side' },
      h('a', { href: filters.href({ open: side.id }), 'data-link': true }, side.title),
      side.evidence.map((e) => evidenceLine(e, true)))));
}

function history(r) {
  if (!r.history.length) return null;
  return h('div', { 'data-part': 'history' },
    h('div', { class: 'grp' }, 'History'),
    r.history.map((e) => h('div', { class: 'm', 'data-part': 'event' },
      h('span', {}, e.event.replaceAll('_', ' ')), h('span', {}, day(e.at)))));
}

function tabs(r, tab) {
  const one = (name, label) => h('a', {
    href: filters.href({ open: r.id, tab: name === 'evidence' ? null : name }),
    class: tab === name ? 'chip on' : 'chip', 'data-link': true, 'data-part': `tab-${name}`,
  }, label);
  return h('div', { class: 'tabs', 'data-part': 'expanded-tabs' }, one('evidence', 'Evidence'), one('relations', 'Relations'));
}

/** The expanded item: everything known about one Record, in place under its row. */
export function panel(r, tab) {
  return h('div', { class: 'open', 'data-part': 'item-expanded' },
    fact('lifecycle', lifecycle(r)),
    fact('basis-text', BASIS[r.basis] ?? r.basis),
    r.kind === 'action_item' && r.commitment ? fact('commitment', `Commitment: ${r.commitment}`) : null,
    r.stated_deadline ? fact('deadline', `Deadline: ${r.stated_deadline}`) : null,
    flags(r),
    disagreement(r),
    tabs(r, tab),
    tab === 'relations'
      ? h('p', { class: 'empty small', 'data-part': 'relations-placeholder' }, 'Relations are not shown here yet.')
      : r.evidence.map((e) => evidenceLine(e, true)),
    history(r));
}
