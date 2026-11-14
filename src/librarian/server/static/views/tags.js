import { justActed } from '../actions.js';
import * as api from '../api.js';
import { h } from '../dom.js';
import { shortDate } from '../format.js';
import { href, waitingOn } from '../filters.js';
import { tagTools } from './tag-tools.js';

const NEEDS = 'needs_attention';
const BASIS = { confirmed: 'Confirmed', stated: 'Stated' };

const newest = (list) => list.reduce((a, b) => ((b.last_evidence ?? '') > (a?.last_evidence ?? '') ? b : a), null);

/** Everything a tag card says, read from the one open-items answer. */
export function standing(records, tag) {
  const members = records.filter((r) => r.tags.some((p) => p.id === tag.id));
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
const itemLink = (item) => h('a', { href: href({ open: item.id, tag: null }), 'data-link': true }, item.title);

function card(tag, tags, records, settled) {
  const s = standing(records, tag);
  const basis = BASIS[tag.basis] ?? 'Inferred';
  return h('section', { class: settled ? 'panel settle' : 'panel', 'data-part': 'tag' },
    h('div', { class: 't' },
      h('a', { href: `/tags?tag=${encodeURIComponent(tag.title)}`, 'data-link': true, 'data-part': 'tag-name' }, tag.title),
      h('span', { class: tag.basis === 'confirmed' ? 'conf' : 'inf', 'data-part': 'tag-basis' }, basis)),
    tag.body ? h('p', { class: 'sum', 'data-part': 'tag-summary' }, tag.body) : null,
    fact('tag-blocker', 'Blocker', s.blocker ? itemLink(s.blocker) : 'None'),
    fact('tag-decision', 'Latest decision', s.decision ? itemLink(s.decision) : 'None'),
    h('div', { class: 'm' },
      h('span', { 'data-part': 'tag-open' }, `${s.open.length} open`),
      h('span', { 'data-part': 'tag-needs' }, `${s.needs.length} need you`),
      h('span', { 'data-part': 'tag-waiting' }, `${s.waiting.length} waiting`)),
    fact('tag-owners', 'Owners', s.owners.length
      ? s.owners.map((name) => h('a', { href: `/people?person=${encodeURIComponent(name)}`, 'data-link': true }, name))
      : 'None'),
    fact('tag-activity', 'Last activity', s.activity ? shortDate(new Date(s.activity)) : 'None'),
    h('div', { class: 'acts' },
      h('a', { class: 'chip', href: href({ tag: tag.title }), 'data-link': true, 'data-part': 'tag-items' }, 'Open its items')),
    h('details', { 'data-part': 'tag-correct' }, h('summary', {}, 'Correct'),
      tagTools({ id: tag.id, name: tag.title }, tags, s.open, '/tags')));
}

/** Tags with their status; confirm, rename, merge and split sit on each card. `?tag=` shows one. */
export async function tags() {
  const settled = justActed() !== null;
  const { records, tags: all } = await api.get('/api/open-items?scope=all');
  const chosen = new URLSearchParams(location.search).get('tag');
  const shown = chosen ? all.filter((p) => p.title === chosen) : all;
  return h('section', { class: 'page', 'data-part': 'tags' },
    h('h1', {}, 'Tags'),
    chosen ? h('a', { class: 'chip', href: '/tags', 'data-link': true, 'data-part': 'all-tags' }, 'All tags') : null,
    shown.length
      ? shown.map((p) => card(p, all, records, settled))
      : h('p', { class: 'empty small', 'data-part': 'empty' }, 'No tags to show yet.'));
}
