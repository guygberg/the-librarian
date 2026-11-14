import { favorite, tagForm } from '../entities.js';
import { justActed } from '../actions.js';
import * as api from '../api.js';
import { h } from '../dom.js';
import { href, waitingOn } from '../filters.js';
import { openDialog } from '../shell.js';
import { NEEDS, btn, clampPage, empty, icon, pageHead, pagination, select, tabs } from '../ui.js';
import { projectTools } from './project-tools.js';

const PAGE = 6;
// The reference's tag icons and accents, given to projects in order.
const LOOKS = [['cube', '#dca666'], ['spark', '#c2ba7b'], ['compass', '#afc8c1'], ['items', '#ddad71'], ['people', '#c2acd2'], ['diamond', '#dfaa8f'], ['calendar', '#d4be83'], ['sliders', '#aac1b0']];

const newest = (list) => list.reduce((a, b) => ((b.last_evidence ?? '') > (a?.last_evidence ?? '') ? b : a), null);

/** Everything a project card says, read from the one open-items answer. */
export function standing(records, project) {
  const members = records.filter((r) => r.projects.some((p) => p.id === project.id));
  const open = members.filter((r) => r.group);
  return {
    open,
    needs: open.filter((r) => r.group === NEEDS),
    waiting: open.filter((r) => waitingOn(r) !== null),
    blocker: newest(open.filter((r) => r.links.some((l) => l.type === 'blocks'))),
    decision: newest(members.filter((r) => r.reasoning)),
    activity: newest(members)?.last_evidence ?? null,
  };
}

const itemHref = (item) => href({ open: item.id, project: null, owner: null, waiting: null, person: null });

function card(project, index, projects, s, accent, settled) {
  const [glyph, fallback] = LOOKS[index % LOOKS.length];
  const color = project.color ?? fallback;
  const needs = s.needs.length;
  // The blocker and the latest decision say most about where a project stands, so they lead the two lines.
  const lines = [];
  if (s.blocker) lines.push(['project-blocker', 'flag', s.blocker]);
  if (s.decision) lines.push(['project-decision', 'check', s.decision]);
  for (const item of s.open) if (!lines.some(([, , i]) => i.id === item.id)) lines.push(['project-item', 'doc', item]);
  const scope = href({ project: project.title, owner: null, waiting: null, person: null, group: null, kind: 'items' });
  return h('article', { class: ['panel tag-card', accent ? 'accent' : '', settled ? 'settle' : ''].join(' ').trim(), 'data-part': 'project' },
    h('div', { class: 'card-top' },
      h('div', { class: 'tag-icon', style: `--accent:${color}` }, icon(glyph)),
      h('div', { class: 'grow' },
        h('h3', {}, h('span', { 'data-part': 'project-name' }, project.title), ''),
        h('p', { 'data-part': 'project-summary' }, project.body || (s.blocker ? 'Blocked right now.' : 'All the work connected to this project.')),
        h('div', { class: 'card-counts' },
          btn([icon('doc', 'small'), h('span', { 'data-part': 'project-open' }, `${s.open.length} open ${s.open.length === 1 ? 'item' : 'items'}`)],
            { cls: 'pill', href: scope, 'data-part': 'project-items' }),
          h('span', { class: needs ? 'pill needs' : 'pill', 'data-part': 'project-needs' }, icon('target', 'small'), `${needs} ${needs === 1 ? 'needs' : 'need'} you`))),
      h('div', { class: 'card-actions' },
        favorite('project', project, project.title),
        btn(icon('more'), { cls: 'iconbtn ghost', 'aria-label': `Edit ${project.title}`, onClick: () => tagForm(project) }),
        btn(icon('sliders'), { cls: 'iconbtn ghost project-corrections', 'aria-label': `Correct ${project.title}`, 'data-part': 'project-correct',
          onClick: () => openDialog(`Correct ${project.title}`,
            h('p', { style: 'margin-bottom:14px' }, 'Confirm, rename, merge or split this project. These are your own corrections; no source changes.'),
            projectTools({ id: project.id, name: project.title }, projects, s.open, '/projects')) }))),
    h('div', { class: 'card-divider' }, lines.length
      ? lines.slice(0, 2).map(([part, glyph2, item]) => btn([icon(glyph2, 'small'), item.title, icon('arrow', 'small')], { cls: 'tag-item', href: itemHref(item), 'data-part': part }))
      : h('p', { class: 'small', style: 'padding:12px 0' }, 'No open items in this project.')));
}

/** Projects, drawn as the reference draws tags: what is open in each, what needs you, and the corrections behind the menu. `?project=` shows one. */
export async function projects() {
  const settled = justActed() !== null;
  const { records, projects: all } = await api.get('/api/open-items?scope=all');
  const q = new URLSearchParams(location.search);
  const chosen = q.get('project');
  const tab = ['favorites', 'unconfirmed'].includes(q.get('tab')) ? q.get('tab') : 'all';
  const to = (change) => {
    const next = new URLSearchParams(location.search);
    for (const [k, v] of Object.entries(change)) { if (v) next.set(k, v); else next.delete(k); }
    return `/projects${next.size ? `?${next}` : ''}`;
  };
  const rows = all.map((project, index) => ({ project, index, s: standing(records, project) }));
  const unconfirmed = rows.filter(({ project }) => project.basis !== 'confirmed');
  const unassigned = records.filter((r) => r.group && !r.projects.length);
  const cards = h('div', { class: 'cards' });
  const foot = h('div', {});
  const find = h('input', { 'aria-label': 'Find a tag…', placeholder: 'Find a tag…', 'data-part': 'project-find' });
  let sort = 'activity';
  const draw = () => {
    const text = find.value.trim().toLowerCase();
    const list = (tab === 'unconfirmed' ? unconfirmed : rows)
      .filter(({ project }) => tab !== 'favorites' || project.favorite)
      .filter(({ project }) => (chosen ? project.title === chosen : `${project.title} ${project.body ?? ''}`.toLowerCase().includes(text)))
      .sort(sort === 'name' ? (a, b) => a.project.title.localeCompare(b.project.title) : (a, b) => b.s.open.length - a.s.open.length);
    const page = clampPage(Number(q.get('page') ?? 1), list.length, PAGE);
    cards.replaceChildren(...list.slice((page - 1) * PAGE, page * PAGE)
      .map(({ project, index, s }, i) => card(project, index, all, s, i === 0 && page === 1, settled)));
    foot.replaceChildren(
      list.length ? '' : empty(all.length ? 'No matches found.' : 'No projects to show yet.', all.length ? 'Try another search or clear your filters.' : null),
      h('div', { class: 'panel bottom-strip row' }, icon('tag'),
        h('div', { class: 'grow' }, h('strong', {}, 'A place for everything'), h('p', {}, 'A little sorting makes things easier to find.')),
        btn(['Review items ', icon('arrow', 'small')], { cls: 'textbtn', href: '/items' })),
      pagination({ total: list.length, size: PAGE, page, noun: 'projects', to: (n) => to({ page: n > 1 ? String(n) : null }) }));
  };
  find.addEventListener('input', draw);
  draw();
  return h('section', { 'data-part': 'projects' },
    pageHead(chosen ?? 'Tags', 'Bring related work together.', 'tags', btn([icon('plus'), 'New tag'], { cls: 'primary', onClick: () => tagForm() })),
    h('div', { class: 'tabs view-tabs' }, tabs([
      ['All tags', to({ tab: null, page: null, project: null }), tab === 'all' && !chosen, all.length, 'all-projects'],
      ['Favorites', to({ tab: 'favorites', page: null, project: null }), tab === 'favorites' && !chosen, all.filter((p) => p.favorite).length, 'projects-tab'],
      ['Untagged', '/items?untagged=1', false, unassigned.length, 'projects-tab'],
    ])),
    chosen ? null : h('div', { class: 'local-toolbar' }, h('label', { class: 'search grow' }, icon('search'), find),
      select('Sort collection', [['activity', 'Most active ↓'], ['name', 'Name A–Z']], sort, (v) => { sort = v; draw(); }, { 'data-part': 'projects-sort' })),
    cards, foot);
}
