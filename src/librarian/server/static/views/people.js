import * as api from '../api.js';
import { h } from '../dom.js';
import { href, waitingOn } from '../filters.js';

const NEEDS = 'needs_attention';

const involves = (item, name) => item.owner === name || item.links.some((l) => l.to === name);

/** Each count is a query over the one open-items answer, so a card never says more than the Items page shows. */
export function standing(records, name) {
  const open = records.filter((r) => r.group);
  return {
    owned: open.filter((r) => r.owner === name),
    waiting: open.filter((r) => waitingOn(r) === name),
    needs: open.filter((r) => r.group === NEEDS && involves(r, name)),
    related: records.filter((r) => r.links.some((l) => l.to === name)),
  };
}

const openItem = (item) => h('a', { href: href({ open: item.id, owner: null, waiting: null, tag: null }), 'data-link': true }, item.title);

const count = (part, label, n) => h('span', { 'data-part': part }, h('b', {}, String(n)), ` ${label}`);

function card(person, records) {
  const s = standing(records, person.name);
  return h('div', { class: 'panel', 'data-part': 'person' },
    h('div', { class: 't' }, h('a', { href: `/people?person=${encodeURIComponent(person.name)}`, 'data-link': true, 'data-part': 'person-name' }, person.name),
      person.is_me ? h('span', { class: 'm' }, ' You') : null),
    h('div', { class: 'm' }, count('person-owned', 'own', s.owned.length), count('person-waiting', 'waiting on them', s.waiting.length),
      count('person-needs', 'need you', s.needs.length)));
}

function section(part, title, items, line) {
  return h('section', { 'data-part': part },
    h('div', { class: 'grp' }, `${title} (${items.length})`),
    items.length ? items.map(line) : h('p', { class: 'empty small', 'data-part': 'empty' }, 'None.'));
}

function detail(person, records) {
  const s = standing(records, person.name);
  const link = (part, text, to) => h('a', { class: 'chip', href: to, 'data-link': true, 'data-part': part }, text);
  return h('div', { class: 'panel', 'data-part': 'person-detail' },
    h('div', { class: 't' }, person.name),
    h('div', { class: 'acts' },
      link('person-items', 'Items they own', href({ owner: person.name, waiting: null, tag: null })),
      link('person-waiting-items', 'Items waiting on them', href({ waiting: person.name, owner: null, tag: null })),
      link('person-all', 'All people', '/people')),
    section('person-owned-list', 'Owned', s.owned, (i) => h('div', { class: 'it', 'data-part': 'person-item' }, h('div', { class: 't' }, openItem(i)))),
    section('person-waiting-list', 'Waiting on them', s.waiting, (i) => h('div', { class: 'it', 'data-part': 'person-item' }, h('div', { class: 't' }, openItem(i)))),
    section('person-relations', 'Relations', s.related, (i) => h('div', { class: 'it', 'data-part': 'person-relation' },
      h('div', { class: 't' }, openItem(i)),
      h('div', { class: 'm' }, i.links.filter((l) => l.to === person.name).map((l) => h('span', {}, l.type.replace(/_/g, ' ')))))));
}

/** People the Librarian has confirmed, with the work each is part of. `?person=` opens one. */
export async function people() {
  const { records, people: persons } = await api.get('/api/open-items?scope=all');
  const chosen = new URLSearchParams(location.search).get('person');
  const one = persons.find((p) => p.name === chosen);
  return h('section', { class: 'page', 'data-part': 'people' },
    h('h1', {}, 'People'),
    one ? detail(one, records) : null,
    persons.length
      ? persons.filter((p) => p !== one).map((p) => card(p, records))
      : h('p', { class: 'empty small', 'data-part': 'empty' }, 'No people to show yet.'));
}
