import { favorite, personForm } from '../entities.js';
import * as api from '../api.js';
import { h } from '../dom.js';
import { href, involves, waitingOn } from '../filters.js';
import { NEEDS, avatar, btn, clampPage, empty, icon, pageHead, pagination, select, tabs } from '../ui.js';
import { blurb } from './common.js';

const PAGE = 6;

/** Each count is a query over the one open-items answer, so a card never says more than the Items page shows. */
export function standing(records, name) {
  const open = records.filter((r) => r.group);
  return {
    owned: open.filter((r) => r.owner === name),
    waiting: open.filter((r) => waitingOn(r) === name),
    needs: open.filter((r) => r.group === NEEDS && involves(r, name)),
    related: open.filter((r) => involves(r, name)),
  };
}

const pill = (glyph, label, n, part, on) => h('span', { class: on && n ? 'pill needs' : 'pill' }, icon(glyph, 'small'), label, ' ',
  h('span', { class: 'counter', 'data-part': part }, String(n)));

function card(person, s, accent) {
  const [item] = [...s.waiting, ...s.needs, ...s.related];
  const scope = href({ person: person.name, owner: null, waiting: null, project: null, group: null, kind: 'items' });
  return h('article', { class: accent ? 'panel person-card accent' : 'panel person-card', 'data-part': 'person' },
    h('div', { class: 'card-top' }, avatar(person.name, true),
      h('div', { class: 'grow' },
        h('h3', { 'data-part': 'person-name' }, person.name),
        h('p', { 'data-part': 'person-owned' }, [person.role, person.department].filter(Boolean).join(' · ') || (person.is_me ? 'You' : 'Team member')),
        h('div', { class: 'card-counts' },
          pill('hourglass', 'Waiting on them', s.waiting.length, 'person-waiting', false),
          pill('target', 'Needs you', s.needs.length, 'person-needs', true))), h('div', { class: 'card-actions' }, favorite('person', person, person.name), btn(icon('more'), { cls: 'iconbtn ghost', 'aria-label': `Edit ${person.name}`, onClick: () => personForm(person) }))),
    h('div', { class: 'card-divider card-item' }, icon('doc'),
      h('div', { class: 'grow' },
        item ? btn(item.title, { cls: 'item-title', href: href({ open: item.id, owner: null, waiting: null, project: null, person: null }), 'data-part': 'person-item' })
          : h('strong', {}, 'No open items'),
        h('p', {}, item ? blurb(item) : 'Everything is up to date.'))),
    h('div', { class: 'card-link' }, btn(['View items ', icon('arrow', 'small')], { cls: 'textbtn', href: scope, 'data-part': 'person-items' })));
}

/** People the Librarian has confirmed, with the work each is part of. A person's items open as the Items list narrowed to them. */
export async function people() {
  const { records, people: persons } = await api.get('/api/open-items?scope=all');
  const q = new URLSearchParams(location.search);
  const tab = ['waiting', 'needs', 'favorites'].includes(q.get('tab')) ? q.get('tab') : 'all';
  const to = (change) => {
    const next = new URLSearchParams(location.search);
    for (const [k, v] of Object.entries(change)) { if (v) next.set(k, v); else next.delete(k); }
    return `/people${next.size ? `?${next}` : ''}`;
  };
  const all = persons.map((p) => ({ person: p, s: standing(records, p.name) }));
  const cards = h('div', { class: 'cards' });
  const foot = h('div', {});
  const find = h('input', { 'aria-label': 'Find a person…', placeholder: 'Find a person…', value: q.get('person') ?? '', 'data-part': 'person-find' });
  let sort = 'activity';
  const draw = () => {
    const text = find.value.trim().toLowerCase();
    const list = all
      .filter(({ person }) => [person.name, person.email, person.role, person.department, person.slack_id, ...(person.aliases ?? [])].filter(Boolean).join(' ').toLowerCase().includes(text))
      .filter(({ person }) => tab !== 'favorites' || person.favorite)
      .filter(({ s }) => (tab === 'waiting' ? s.waiting.length : tab === 'needs' ? s.needs.length : true))
      .sort(sort === 'name' ? (a, b) => a.person.name.localeCompare(b.person.name) : (a, b) => b.s.related.length - a.s.related.length);
    const page = clampPage(Number(q.get('page') ?? 1), list.length, PAGE);
    cards.replaceChildren(...list.slice((page - 1) * PAGE, page * PAGE).map(({ person, s }, i) => card(person, s, i === 0 && page === 1)));
    foot.replaceChildren(
      list.length ? '' : empty(persons.length ? 'No matches found.' : 'No people to show yet.', persons.length ? 'Try another search or clear your filters.' : null),
      pagination({ total: list.length, size: PAGE, page, noun: 'people', to: (n) => to({ page: n > 1 ? String(n) : null }) }));
  };
  find.addEventListener('input', draw);
  draw();
  return h('section', { 'data-part': 'people' },
    pageHead('People', 'The people moving things forward.', 'people', btn([icon('plus'), 'Add person'], { cls: 'primary', onClick: () => personForm() })),
    h('div', { class: 'tabs view-tabs' }, tabs([
      ['Everyone', to({ tab: null, page: null }), tab === 'all', persons.length, 'people-tab'],
      ['Waiting on them', to({ tab: 'waiting', page: null }), tab === 'waiting', all.filter(({ s }) => s.waiting.length).length, 'people-tab'],
      ['Needs you', to({ tab: 'needs', page: null }), tab === 'needs', all.filter(({ s }) => s.needs.length).length, 'people-tab'],
      ['Favorites', to({ tab: 'favorites', page: null }), tab === 'favorites', persons.filter((p) => p.favorite).length, 'people-tab'],
    ])),
    h('div', { class: 'local-toolbar' }, h('label', { class: 'search grow' }, icon('search'), find),
      select('Sort collection', [['activity', 'Most active ↓'], ['name', 'Name A–Z']], sort, (v) => { sort = v; draw(); }, { 'data-part': 'people-sort' })),
    cards, foot);
}
