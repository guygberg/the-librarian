import { checklist, notes, priority, itemForm } from '../entities.js';
import { act, justActed } from '../actions.js';
import * as api from '../api.js';
import { h } from '../dom.js';
import * as filters from '../filters.js';
import { ago, shortDate } from '../format.js';
import { avatar, btn, emblem, empty, first, icon, statusPill, warnings } from '../ui.js';
import { assign, complete, itemMenu, ownerLabel, ownerName, summary } from './common.js';
import { evidenceLine, sheetHref, sourceRow } from './evidence.js';
import * as relations from './graph.js';

const BASIS = {
  stated: 'Stated: a source says this outright.',
  inferred: 'Inferred: no source says this outright. Check the Evidence.',
  confirmed: 'Confirmed by you.',
};

const day = (iso) => shortDate(new Date(iso));

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

/** What is wrong with, or worth knowing about, this Record. */
function flags(r) {
  const flag = (text) => h('div', { class: 'panel filter-banner', 'data-part': 'flag' }, icon('alert', 'small'), h('span', {}, text));
  return [
    r.no_longer_found ? flag('No longer found in sources.') : null,
    r.stale && r.last_evidence ? flag(`Stale: not mentioned in any source since ${day(r.last_evidence)}.`) : null,
  ];
}

function disagreement(r) {
  if (!r.contradictions.length) return null;
  const [rival] = r.contradictions;
  // Whichever side is chosen, the item that settles is the one open on the page.
  const resolve = (id, other, outcome) => () => act(id, 'resolve', { other, outcome }, r.id);
  return h('section', { class: 'panel detail-card dis', 'data-part': 'disagreement' },
    h('h3', { class: 'w' }, icon('alert'), ' Sources disagree'),
    h('div', { class: 'sides' }, [r, ...r.contradictions].map((side) => h('div', { class: 'side', 'data-part': 'side' },
      btn(side.title, { cls: 'item-title', href: filters.href({ open: side.id }) }),
      side.evidence.map((e) => evidenceLine(e, true, r.id)),
      btn('This one holds', { onClick: resolve(side.id, side === r ? rival.id : r.id, 'holds'), 'data-part': 'act-holds' })))),
    btn('Both are wrong', { onClick: resolve(r.id, rival.id, 'both_wrong'), 'data-part': 'act-both-wrong' }));
}

const EVENT_ICONS = { status_change: 'check', owner_change: 'user', project_change: 'tag', resolve_disagreement: 'sliders' };

function history(r) {
  if (!r.history.length) return null;
  return h('div', { 'data-part': 'history' },
    r.history.map((e) => h('div', { class: 'message', 'data-part': 'event' }, icon(EVENT_ICONS[e.event] ?? 'doc'),
      h('div', {}, h('strong', {}, h('span', {}, e.event.replaceAll('_', ' '))), h('p', {}, `${day(e.at)} · You`)))));
}

const TAB_LABELS = { overview: 'Overview', activity: 'Activity', sources: 'Sources', relations: 'Relations' };

function detailTabs(r, tab) {
  return h('div', { class: 'tabs detail-tabs', 'data-part': 'expanded-tabs' }, filters.DETAIL_TABS.map((name) => btn(
    [TAB_LABELS[name], name === 'sources' ? [' ', h('span', { class: 'counter' }, String(r.evidence.length))] : null],
    { cls: tab === name ? 'tab active' : 'tab', href: filters.href({ open: r.id, tab: filters.tabParam(name) }), 'data-part': `tab-${name}` })));
}

/** What to do next, from the lifecycle and the Record's own relationships; there is no priority score behind it. */
function nextMove(r) {
  if (r.contradictions.length) return 'Settle which source is right.';
  if (r.lifecycle === 'done') return 'All done. Reopen it if it came back.';
  if (r.lifecycle === 'dropped' || r.lifecycle === 'superseded') return 'Nothing to do: it is no longer live.';
  if (r.lifecycle === 'suspended') return 'Wait until what suspended it clears.';
  if (r.lifecycle === 'pending') return filters.waitingOn(r) ? `Follow up with ${filters.waitingOn(r)}.` : 'Waiting on someone else.';
  if (!r.is_tag && !r.owner && !r.owner_is_me) return 'Give it an owner.';
  if (!r.is_tag) return 'Do it, then mark it done.';
  return 'Decide whether this still stands.';
}

const ROLE_TITLES = [['supports', 'Supporting'], ['completes', 'Completing'], ['contradicts', 'Contradicting']];

function sources(r) {
  if (!r.evidence.length) return h('p', { class: 'empty', 'data-part': 'empty' }, 'No sources.');
  return ROLE_TITLES.map(([role, title]) => {
    const list = r.evidence.filter((e) => e.role === role);
    return list.length
      ? h('div', { class: 'role', 'data-part': `sources-${role}` }, h('div', { class: 'eyebrow' }, title.toUpperCase()), list.map((e) => evidenceLine(e, true, r.id)))
      : null;
  });
}

function overview(r) {
  return [
    h('h2', {}, 'The brief'),
    h('p', { class: 'brief', 'data-part': 'brief' }, summary(r) ?? 'The sources give no summary beyond the title. The Evidence below is what the Librarian has.'),
    h('h2', {}, `Sub-items (${(r.subitems ?? []).filter((i) => i.lifecycle === 'done').length}/${(r.subitems ?? []).length})`),
    checklist(r),
    h('section', { class: 'conversation' },
      h('div', { class: 'between' }, h('h2', {}, 'Latest conversation'),
        r.evidence.length > 1 ? btn(['All sources ', icon('arrow', 'small')], { cls: 'tagchip', href: filters.href({ open: r.id, tab: 'sources' }) }) : null),
      r.evidence.length ? r.evidence.slice(-3).map((e) => evidenceLine(e, true, r.id)) : h('p', { class: 'small', 'data-part': 'empty' }, 'No sources.'), notes(r)),
    r.history.length ? h('section', { class: 'conversation' }, h('h2', {}, 'Your changes'), history(r)) : null,
  ];
}

function details(r, ctx) {
  const on = filters.waitingOn(r);
  const owner = r.owner_is_me ? ctx.me : ownerName(r);
  const row = (glyph, label, ...value) => h('div', { class: 'detail-row' }, icon(glyph, 'small'), h('span', { class: 'label' }, label), ...value);
  return h('div', { class: 'panel detail-card', 'data-part': 'details' },
    h('h3', {}, 'Details'),
    warnings(r).map((warning) => h('p', { class: 'w', 'data-part': 'warning' }, warning)),
    row('pulse', 'Status', h('span', { 'data-part': 'lifecycle' }, lifecycle(r))),
    row('user', 'Owner', !r.is_tag
      ? btn(ownerLabel(r), { cls: 'textbtn', onClick: () => assign(r, ctx.people), 'data-part': 'owner' })
      : h('span', { 'data-part': 'owner' }, ownerLabel(r))),
    row('hourglass', 'Waiting on', h('span', {}, r.lifecycle === 'done' ? 'Nothing: done' : on ?? (r.group === 'needs_attention' ? 'You' : 'No one'))),
    row('flag', 'Priority', btn(priority(r) >= 80 ? 'High' : priority(r) >= 60 ? 'Medium' : 'Low', { cls: 'pill needs', onClick: () => itemForm(r) })),
    row('calendar', 'Due', btn(r.stated_deadline || 'No due date', { cls: 'textbtn', onClick: () => itemForm(r) })),
    row('tag', 'Tags', h('div', { class: 'row', style: 'gap:6px;flex-wrap:wrap' }, r.projects.length
      ? r.projects.map((p) => btn(p.title, { cls: 'tagchip', href: `/projects?project=${encodeURIComponent(p.title)}`, 'data-part': 'detail-project' }))
      : h('span', { class: 'muted' }, 'None'))),
    row('people', 'People', h('div', { class: 'row small', style: 'gap:7px;flex-wrap:wrap' },
      owner ? [avatar(owner), r.owner_is_me ? 'You' : first(owner)] : null,
      on && on !== owner ? [avatar(on), first(on)] : null,
      owner || on ? null : h('span', { class: 'muted' }, 'None'))));
}

function linkedSources(r) {
  return h('div', { class: 'panel detail-card', 'data-part': 'linked-sources' },
    h('h3', {}, 'Linked sources'),
    r.evidence.length ? r.evidence.map((e) => sourceRow(e, r.id)) : h('p', { class: 'small' }, 'No sources.'),
    r.last_evidence ? h('p', { class: 'source-date' }, `Last mentioned ${ago(new Date(r.last_evidence)).replace(/^(Today|Yesterday)$/, (w) => w.toLowerCase())}`) : null);
}

/** An item's own page, laid out as the reference's detail view: heading and corrections, the next move, the four tabs and the facts beside them. */
export async function detail(state) {
  const acted = justActed();
  const answer = await api.get('/api/open-items?scope=all');
  let r;
  try {
    ({ item: r } = await api.get(`/api/items/${state.open}`));
  } catch {
    return empty('Nothing here.', 'This item is not in the Workspace.');
  }
  const tab = state.tab;
  const graphState = tab === 'relations' ? relations.params(state.open) : null;
  const graph = graphState && await api.get(relations.query(graphState));
  const ctx = { people: answer.people, projects: answer.projects, me: answer.people.find((p) => p.is_me)?.name ?? null };
  // Previous and Next walk the list the item was opened from, or every record when the filters no longer hold it.
  let list = answer.records.filter((x) => filters.matches(x, state));
  if (!list.some((x) => x.id === r.id)) list = answer.records;
  const at = list.findIndex((x) => x.id === r.id);
  const step = (dir) => (at < 0 || list.length < 2 ? null : filters.href({ open: list[(at + dir + list.length) % list.length].id }));
  const done = r.lifecycle === 'done';
  const latest = r.evidence.at(-1);
  const body = {
    overview: () => overview(r),
    activity: () => [h('h2', {}, 'Item activity'), history(r) ?? h('p', { class: 'small', 'data-part': 'empty' }, 'No activity yet.')],
    sources: () => [h('h2', {}, 'Linked sources'), sources(r)],
    relations: () => relations.view(graph, r.id, graphState, answer.people),
  }[tab]();

  return h('div', { class: acted?.id === r.id ? 'detail settle' : 'detail', 'data-part': 'item-expanded', 'data-id': r.id },
    h('div', { class: 'breadcrumb' },
      h('div', { class: 'row' }, btn([icon('back'), 'Items'], { cls: 'textbtn', href: filters.href({}), 'data-part': 'back-to-items' }),
        r.parent ? [h('span', { class: 'muted' }, '/'), btn(r.parent.title, { cls: 'textbtn', href: `/items/${r.parent.id}`, 'aria-label': 'Open parent item' })] : null,
        h('span', { class: 'muted' }, '/'), h('span', { 'data-part': 'crumb-title' }, r.title)),
      h('div', { class: 'row' },
        btn([icon('back'), h('span', { class: 'hide-mobile' }, 'Previous item')], { href: step(-1), disabled: !step(-1), 'aria-label': 'Previous item', 'data-part': 'item-prev' }),
        btn([h('span', { class: 'hide-mobile' }, 'Next item'), icon('chevron')], { href: step(1), disabled: !step(1), 'aria-label': 'Next item', 'data-part': 'item-next' }))),
    h('div', { class: 'page-head detail-head' }, emblem('cube'),
      h('div', { class: 'grow' }, h('h1', { 'data-part': 'detail-title' }, r.title), h('p', { class: 'subtitle' }, summary(r) ?? ownerLabel(r)),
        h('div', { class: 'pills' }, statusPill(r),
          r.projects.slice(0, 2).map((p) => h('span', { class: 'tagchip' }, p.title)))),
      h('div', { class: 'header-actions', 'data-part': 'actions' },
        btn([icon('check'), done ? 'Reopen' : 'Mark done'], { cls: 'primary', onClick: () => complete(r), 'data-part': done ? 'act-reopen' : 'act-done' }),
        !r.is_tag ? btn([icon('user'), 'Assign to…'], { onClick: () => assign(r, ctx.people), 'data-part': 'assign' }) : null,
        btn(icon('more'), { cls: 'iconbtn', 'aria-label': 'More item actions', onClick: () => itemMenu(r, ctx.people, ctx.projects), 'data-part': 'more-actions' }))),
    h('section', { class: 'panel accent next-move' }, icon('target'),
      h('div', { class: 'grow' },
        h('div', { class: 'eyebrow' }, done ? 'MISSION COMPLETE' : 'YOUR NEXT MOVE'),
        h('h2', { 'data-part': 'next-move' }, nextMove(r)),
        h('p', { 'data-part': 'basis-text' }, BASIS[r.basis] ?? r.basis)),
      latest ? btn(['Open context', icon('external')], { cls: 'primary', href: sheetHref(latest, r.id), 'data-part': 'open-context' }) : null),
    flags(r),
    disagreement(r),
    h('div', { class: tab === 'relations' ? 'detail-grid wide' : 'detail-grid' },
      h('section', { class: 'panel detail-content' }, detailTabs(r, tab), h('div', { class: 'detail-body', 'data-part': `body-${tab}` }, body)),
      h('aside', { class: 'stack' }, details(r, ctx), linkedSources(r))));
}
