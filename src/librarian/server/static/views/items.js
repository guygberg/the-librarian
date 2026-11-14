import { itemForm } from '../entities.js';
import { justActed } from '../actions.js';
import * as api from '../api.js';
import { h } from '../dom.js';
import * as filters from '../filters.js';
import { ago, isToday } from '../format.js';
import { lastImport } from '../shell.js';
import { NEEDS, OTHER, WAITING, avatar, btn, clampPage, emblem, empty, first, icon, kindLabel, pageHead, pagination, select, statusPill, tabs, warnings } from '../ui.js';
import { blurb, complete, itemMenu, ownerName, summary } from './common.js';
import { detail } from './detail.js';
import { evidenceLine } from './evidence.js';
import { projectTools } from './project-tools.js';

const PAGE = 7;
const RANK = { [NEEDS]: 0, [WAITING]: 1, [OTHER]: 2 };

/** What the last action changed (see actions.js), so the matching parts settle on this one render. */
let acted = null;

// Finishing or reopening work moves the counts; they settle once, with no sound.
const countsMoved = () => ['done', 'reopen'].includes(acted?.name);

/** "N things need you, M waiting on someone else", in the subtitle's place. */
function headline(text) {
  const [, before, verb, after] = text.match(/^(.*?)(needs? you)(.*)$/);
  return h('span', { 'data-part': 'headline', class: countsMoved() ? 'settle' : null }, before, h('em', {}, verb), after);
}

/** Who the row is with: the person it waits on while it is waiting, else its owner. */
function ownerCell(item, me) {
  const waiting = item.group === WAITING ? filters.waitingOn(item) : null;
  const mine = item.owner_is_me && !waiting;
  const name = waiting ?? (mine ? me : ownerName(item));
  const label = mine ? 'You' : first(name) ?? 'No owner';
  return h('div', { class: 'row nowrap' }, avatar(name),
    name && !mine
      ? btn(label, { cls: 'textbtn', href: `/people?person=${encodeURIComponent(name)}`, 'data-part': 'row-owner', title: name })
      : h('span', { 'data-part': 'row-owner' }, label));
}

const projectChip = (item) => (item.projects.length
  ? btn(item.projects[0].title, { cls: 'tagchip', href: filters.href({ project: item.projects[0].title }), 'data-part': 'row-project' })
  : h('span', { class: 'tagchip muted', 'data-part': 'row-project' }, 'No project'));

function row(item, index, ctx) {
  const done = item.lifecycle === 'done';
  const to = filters.href({ open: item.id, page: ctx.state.page });
  const check = h('input', { class: 'check', type: 'checkbox', checked: done, 'aria-label': `${done ? 'Reopen' : 'Complete'} ${item.title}`, 'data-part': 'row-check' });
  check.addEventListener('change', () => complete(item));
  const cls = [index === 0 ? 'highlight' : null, acted?.id === item.id ? 'settle' : null].filter(Boolean).join(' ');
  return h('tr', { class: cls || null, 'data-part': 'item', 'data-id': item.id },
    h('td', {}, check),
    h('td', { class: 'title-cell', 'data-href': to },
      btn(item.title, { cls: 'item-title', href: to, 'data-part': 'item-title' }),
      summary(item) ? h('div', { class: 'item-sub', 'data-part': 'summary' }, summary(item)) : null,
      warnings(item).length ? h('div', { class: 'marks' }, warnings(item).map((warning) =>
        h('span', { class: 'tagchip w', 'data-part': 'warning' }, icon('alert', 'small'), warning))) : null,
      ctx.evidence.filter((e) => e.record_id === item.id).map((e) => evidenceLine(e))),
    h('td', {}, projectChip(item)),
    h('td', {}, statusPill(item, { 'data-part': 'row-lifecycle' })),
    h('td', {}, ownerCell(item, ctx.me)),
    h('td', { class: 'nowrap', 'data-part': 'updated' }, (item.last_evidence ?? item.updated_at) ? ago(new Date(item.last_evidence ?? item.updated_at)) : '—'),
    h('td', {}, h('div', { class: 'table-actions' }, index === 0
      ? [btn('Open', { href: to, 'data-part': 'row-open' }),
        btn(icon('check'), { cls: 'iconbtn', 'aria-label': done ? 'Reopen item' : 'Complete item', onClick: () => complete(item), 'data-part': 'row-done' })]
      : btn(icon('more'), { cls: 'iconbtn ghost', 'aria-label': `Actions for ${item.title}`, 'data-part': 'row-menu',
        onClick: () => itemMenu(item, ctx.people, ctx.projects) }))));
}

function table(list, ctx) {
  const page = clampPage(Number(ctx.state.page ?? 1), list.length, PAGE);
  const shown = list.slice((page - 1) * PAGE, page * PAGE);
  return [
    h('div', { class: 'table-wrap' }, h('table', { class: 'items-table' },
      h('thead', {}, h('tr', {}, ['', 'Item', '', 'Status', 'Owner', 'Updated', ''].map((t) => h('th', {}, t)))),
      h('tbody', {}, shown.map((item, index) => row(item, index, ctx))))),
    list.length ? null : ctx.calm,
    pagination({ total: list.length, size: PAGE, page, noun: 'items', to: (n) => filters.href({ page: n > 1 ? String(n) : null }) }),
  ];
}

/** The same records in columns: the query's groups, and Completed when that is what is being looked at. Anything else that matched is never dropped. */
function board(list, ctx) {
  const card = (i) => btn([
    h('strong', {}, i.title),
    h('p', { class: 'small' }, blurb(i)),
    h('div', { class: 'between' }, avatar(i.owner_is_me ? ctx.me : ownerName(i)), h('span', { class: 'tagchip' }, i.projects[0]?.title ?? 'No project')),
  ], { cls: acted?.id === i.id ? 'board-item settle' : 'board-item', href: filters.href({ open: i.id }), 'data-part': 'item', 'data-id': i.id });
  const column = (part, pill, items) => h('section', { class: 'panel board-column', 'data-part': part },
    h('h3', { 'data-part': 'group' }, pill, ' ', h('span', { class: 'counter' }, String(items.length))),
    items.length ? items.map(card) : h('p', { class: 'small' }, 'Nothing here.'));
  const of = (group) => list.filter((r) => r.group === group);
  const done = list.filter((r) => r.group === null && r.lifecycle === 'done');
  const rest = list.filter((r) => r.group === null && r.lifecycle !== 'done');
  return h('div', { class: 'board', 'data-part': 'board' },
    column('col-needs', statusPill({ group: NEEDS }), of(NEEDS)),
    column('col-waiting', statusPill({ group: WAITING }), of(WAITING)),
    column('col-other', statusPill({ group: OTHER }), of(OTHER)),
    done.length || ctx.state.kind === 'done' ? column('col-done', statusPill({ lifecycle: 'done' }), done) : null,
    rest.length ? column('col-rest', h('span', { class: 'pill' }, 'Not open'), rest) : null);
}

const fact = (label, glyph, f) => (f && f !== 'not found'
  ? h('div', { class: 'detail-row' }, icon(glyph, 'small'), h('span', { class: 'label' }, label), h('span', {}, f.title ?? f.value))
  : null);

/** What a selected project stands at, what changed since the last meeting, and its corrections. */
async function statusHeader(name, projects, list) {
  const [{ project, resolved }, changes] = await Promise.all([
    api.get(`/api/project?name=${encodeURIComponent(name)}`),
    api.get(`/api/changes?project=${encodeURIComponent(name)}`),
  ]);
  if (!resolved.project) return null;
  return h('section', { class: 'panel detail-card status-header', 'data-part': 'status-header' },
    h('h3', {}, resolved.project.name),
    fact('Status', 'pulse', project.status),
    fact('Blocker', 'flag', project.main_blocker),
    fact('Latest decision', 'check', project.latest_decision),
    h('div', { class: 'detail-row', 'data-part': 'changes' }, icon('reset', 'small'), h('span', { class: 'label' }, 'Changed'),
      h('span', {}, `${changes.changes.length} changed`), h('span', { class: 'muted' }, changes.resolved.baseline)),
    projectTools(resolved.project, projects, list));
}

const SCOPE_TEXT = {
  project: 'All the work connected to this project.',
  person: 'Open work and shared next steps.',
  owner: 'Open work and shared next steps.',
  waiting: 'Open work and shared next steps.',
};

/** The Items page: the reference's tabs, table and board over the one open-items answer, every filter in the URL. */
export async function items() {
  const state = filters.current();
  if (state.open) return detail(state);
  acted = justActed();
  const answer = await api.get('/api/open-items?scope=all');
  const list = answer.records.filter((r) => !r.parent_id && filters.matches(r, state));
  if (state.sort === 'name') list.sort((a, b) => a.title.localeCompare(b.title));
  else list.sort((a, b) => (RANK[a.group] ?? 3) - (RANK[b.group] ?? 3));
  const header = state.project ? await statusHeader(state.project, answer.projects, list) : null;
  const open = answer.records.filter((r) => r.group && !r.parent_id);
  const doneToday = answer.records.filter((r) => r.lifecycle === 'done' && r.done_at && isToday(new Date(r.done_at))).length;
  const scope = ['project', 'person', 'owner', 'waiting'].find((k) => state[k]);
  const narrowed = filters.FILTER_KEYS.filter((k) => state[k]);
  const go = (change) => window.librarianNavigate(filters.href(change));
  const ctx = {
    state, people: answer.people, projects: answer.projects, me: answer.people.find((p) => p.is_me)?.name ?? null,
    evidence: state.kind === 'done' ? answer.evidence : [],
    calm: state.kind === 'items' && !narrowed.length && !state.group
      ? empty(`Nothing needs you today. ${lastImport(answer.freshness)}`, null)
      : empty('Nothing here.', 'Try another filter or clear your filters.'),
  };
  const tab = state.kind === 'done' ? 'done' : state.kind === 'items' ? state.group ?? 'all' : null;

  return h('div', { 'data-part': 'items' },
    pageHead(scope ? state[scope] : 'Items', scope ? SCOPE_TEXT[scope] : headline(answer.headline.text), 'items',
      btn([icon('plus'), 'New item'], { cls: 'primary', onClick: () => itemForm(), 'data-part': 'items-new' })),
    h('div', { class: 'tabs view-tabs', 'data-part': 'kind-tabs' },
      tabs([
        ['All items', filters.href({ kind: 'items', group: null }), tab === 'all', open.length, 'kind-tab'],
        ['Needs you', filters.href({ kind: 'items', group: 'needs' }), tab === 'needs', open.filter((r) => r.group === NEEDS).length, 'kind-tab'],
        ['Waiting on others', filters.href({ kind: 'items', group: 'waiting' }), tab === 'waiting', open.filter((r) => r.group === WAITING).length, 'kind-tab'],
        ['Completed', filters.href({ kind: 'done', group: null }), tab === 'done', undefined, 'kind-tab'],
      ]),
      h('div', { class: 'tabs view-toggle', style: 'margin-left:auto', 'data-part': 'view-toggle' },
        btn([icon('list'), 'List'], { cls: state.view === 'list' ? 'active' : '', href: filters.href({ view: 'list', page: state.page }), 'data-part': 'view-tab' }),
        btn([icon('board'), 'Board'], { cls: state.view === 'board' ? 'active' : '', href: filters.href({ view: 'board' }), 'data-part': 'view-tab' }))),
    narrowed.length ? h('div', { class: 'panel filter-banner', 'data-part': 'filter-banner' }, icon('sliders', 'small'),
      h('span', {}, `${list.length} matching ${list.length === 1 ? 'item' : 'items'} · ${narrowed.map((k) => state[k]).join(' · ')}`),
      btn('Clear filters ×', { cls: 'textbtn', href: filters.cleared(), 'data-part': 'clear-filters' })) : null,
    header,
    state.view === 'board'
      ? board(list, ctx)
      : h('section', { class: 'panel table-panel' },
        h('div', { class: 'between table-toolbar' },
          select('Item status', filters.KINDS, state.kind, (v) => go({ kind: v, group: null }), { 'data-part': 'kind-filter' }),
          h('div', { class: 'row toolbar-more', 'data-part': 'more-filters' },
            select('Basis', [['', 'Basis: any'], ...['stated', 'inferred', 'confirmed'].map((b) => [b, kindLabel(b)])],
              state.basis, (v) => go({ basis: v || null }), { 'data-part': 'basis-filter' }),
            select('Warning', [['', 'Warning: any'], ...Object.entries(filters.WARNINGS).map(([k, [text]]) => [k, text])],
              state.warn, (v) => go({ warn: v || null }), { 'data-part': 'warn-filter' }),
            select('Sort items', [['', 'Ranked ↓'], ['name', 'Name A–Z']], state.sort, (v) => go({ sort: v || null }), { 'data-part': 'sort' }))),
        table(list, ctx)),
    h('div', { class: 'panel bottom-strip row' }, emblem('cube', 'width:55px;height:48px'),
      h('div', { class: 'grow' }, h('strong', {}, 'A little progress, every day.')),
      h('span', { 'data-part': 'done-today' }, `${doneToday} ${doneToday === 1 ? 'item' : 'items'} completed today`)));
}
