import { act } from '../actions.js';
import { h } from '../dom.js';
import * as filters from '../filters.js';
import { shortDate } from '../format.js';
import * as relations from './graph.js';

const BASIS = {
  stated: 'Stated: a source says this outright.',
  inferred: 'Inferred: no source says this outright. Check the Evidence.',
  confirmed: 'Confirmed by you.',
};

const day = (iso) => shortDate(new Date(iso));

/** The quote opens its source in the sheet; `open` is the expanded Record to return to, if any. */
export function evidenceLine(e, withRole = false, open = null) {
  const tab = open && filters.current().tab === 'relations' ? 'relations' : null;
  return h('div', { class: 'evb', 'data-part': 'evidence' },
    h('small', {}, withRole ? `${e.locator} · ${e.role}` : e.locator),
    h('a', { href: filters.href({ open, tab, source: e.locator }), 'data-link': true, 'data-part': 'evidence-quote' }, e.quote));
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

const button = (part, text, onClick) => {
  const el = h('button', { type: 'button', class: 'chip', 'data-part': part }, text);
  el.addEventListener('click', onClick);
  return el;
};

function disagreement(r) {
  if (!r.contradictions.length) return null;
  const [rival] = r.contradictions;
  // Whichever side is chosen, the item that settles is the one open on the page.
  const resolve = (id, other, outcome) => () => act(id, 'resolve', { other, outcome }, r.id);
  return h('div', { class: 'dis', 'data-part': 'disagreement' },
    h('p', { class: 'w' }, 'Sources disagree'),
    [r, ...r.contradictions].map((side) => h('div', { class: 'side', 'data-part': 'side' },
      h('a', { href: filters.href({ open: side.id }), 'data-link': true }, side.title),
      side.evidence.map((e) => evidenceLine(e, true, r.id)),
      button('act-holds', 'This one holds', resolve(side.id, side === r ? rival.id : r.id, 'holds')))),
    button('act-both-wrong', 'Both are wrong', resolve(r.id, rival.id, 'both_wrong')));
}

function choose(part, label, options, selected, onPick) {
  const select = h('select', { 'data-part': part, 'aria-label': label },
    h('option', { value: '' }, label),
    options.map((o) => h('option', { value: o.id, selected: o.id === selected }, o.name ?? o.title)));
  select.addEventListener('change', () => select.value && onPick(Number(select.value)));
  return select;
}

/** The corrections a person can make; each is a Person event, the source is never touched. */
function actions(r, ctx) {
  const done = r.lifecycle === 'done';
  return h('div', { class: 'acts', 'data-part': 'actions' },
    done ? button('act-reopen', 'Reopen', () => act(r.id, 'reopen')) : button('act-done', 'Mark done', () => act(r.id, 'done')),
    r.kind === 'action_item' ? choose('act-owner', 'Change owner', ctx.people, null, (person_id) => act(r.id, 'owner', { person_id })) : null,
    choose('act-project', 'Move to project', ctx.projects, r.projects[0]?.id, (project_id) => act(r.id, 'project', { project_id })));
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
export function panel(r, tab, ctx) {
  return h('div', { class: 'open', 'data-part': 'item-expanded' },
    fact('lifecycle', lifecycle(r)),
    actions(r, ctx),
    fact('basis-text', BASIS[r.basis] ?? r.basis),
    r.kind === 'action_item' && r.commitment ? fact('commitment', `Commitment: ${r.commitment}`) : null,
    r.stated_deadline ? fact('deadline', `Deadline: ${r.stated_deadline}`) : null,
    flags(r),
    disagreement(r),
    tabs(r, tab),
    tab === 'relations'
      ? relations.view(ctx.graph, r.id, ctx.graphState, ctx.people)
      : r.evidence.map((e) => evidenceLine(e, true, r.id)),
    history(r));
}
