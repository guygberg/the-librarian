import { justActed } from '../actions.js';
import * as api from '../api.js';
import { h } from '../dom.js';
import { shortDate } from '../format.js';
import { href, waitingOn } from '../filters.js';
import { projectTools } from './project-tools.js';

const NEEDS = 'needs_attention';
const BASIS = { confirmed: 'Confirmed', stated: 'Stated' };

const newest = (list) => list.reduce((a, b) => ((b.last_evidence ?? '') > (a?.last_evidence ?? '') ? b : a), null);

/** Everything a project card says, read from the one open-items answer. */
export function standing(records, project) {
  const members = records.filter((r) => r.projects.some((p) => p.id === project.id));
  const open = members.filter((r) => r.group);
  return {
    open,
    needs: open.filter((r) => r.group === NEEDS),
    waiting: open.filter((r) => waitingOn(r) !== null),
    blocker: newest(open.filter((r) => r.kind === 'blocker')),
    decision: newest(members.filter((r) => r.kind === 'decision')),
    owners: [...new Set(open.map((r) => r.owner).filter(Boolean))].sort(),
    activity: newest(members)?.last_evidence ?? null,
  };
}

const fact = (part, label, value) => h('div', { class: 'm', 'data-part': part }, h('span', {}, label), value);
const itemLink = (item) => h('a', { href: href({ open: item.id, project: null }), 'data-link': true }, item.title);

function card(project, projects, records, settled) {
  const s = standing(records, project);
  const basis = BASIS[project.basis] ?? 'Inferred';
  return h('section', { class: settled ? 'panel settle' : 'panel', 'data-part': 'project' },
    h('div', { class: 't' },
      h('a', { href: `/projects?project=${encodeURIComponent(project.title)}`, 'data-link': true, 'data-part': 'project-name' }, project.title),
      h('span', { class: project.basis === 'confirmed' ? 'conf' : 'inf', 'data-part': 'project-basis' }, basis)),
    project.body ? h('p', { class: 'sum', 'data-part': 'project-summary' }, project.body) : null,
    fact('project-blocker', 'Blocker', s.blocker ? itemLink(s.blocker) : 'None'),
    fact('project-decision', 'Latest decision', s.decision ? itemLink(s.decision) : 'None'),
    h('div', { class: 'm' },
      h('span', { 'data-part': 'project-open' }, `${s.open.length} open`),
      h('span', { 'data-part': 'project-needs' }, `${s.needs.length} need you`),
      h('span', { 'data-part': 'project-waiting' }, `${s.waiting.length} waiting`)),
    fact('project-owners', 'Owners', s.owners.length
      ? s.owners.map((name) => h('a', { href: `/people?person=${encodeURIComponent(name)}`, 'data-link': true }, name))
      : 'None'),
    fact('project-activity', 'Last activity', s.activity ? shortDate(new Date(s.activity)) : 'None'),
    h('div', { class: 'acts' },
      h('a', { class: 'chip', href: href({ project: project.title }), 'data-link': true, 'data-part': 'project-items' }, 'Open its items')),
    h('details', { 'data-part': 'project-correct' }, h('summary', {}, 'Correct'),
      projectTools({ id: project.id, name: project.title }, projects, s.open, '/projects')));
}

/** Projects with their status; confirm, rename, merge and split sit on each card. `?project=` shows one. */
export async function projects() {
  const settled = justActed() !== null;
  const { records, projects: all } = await api.get('/api/open-items?scope=all');
  const chosen = new URLSearchParams(location.search).get('project');
  const shown = chosen ? all.filter((p) => p.title === chosen) : all;
  return h('section', { class: 'page', 'data-part': 'projects' },
    h('h1', {}, 'Projects'),
    chosen ? h('a', { class: 'chip', href: '/projects', 'data-link': true, 'data-part': 'all-projects' }, 'All projects') : null,
    shown.length
      ? shown.map((p) => card(p, all, records, settled))
      : h('p', { class: 'empty small', 'data-part': 'empty' }, 'No projects to show yet.'));
}
