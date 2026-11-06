import { h } from '../dom.js';
import * as filters from '../filters.js';
import { aliasControls } from './alias.js';

export const KINDS = ['belongs_to', 'owner', 'waiting_on', 'blocks', 'supersedes', 'related_to', 'mentions', 'evidence'];
const NS = 'http://www.w3.org/2000/svg';
const W = 980, NODE = [190, 48];
// Radii of the ellipses: a 1-hop graph has one; a deeper one has an inner ring and an outer ring shared by hops 2 and 3.
const ringsFor = (hops) => (hops === 1 ? [[300, 140]] : [[230, 110], [385, 270]]);
const height = (hops) => (hops === 1 ? 430 : 640);
const label = (kind) => kind.replaceAll('_', '-');

/** The graph state lives in the URL: the centre node, the hop count and the edge kinds still shown. */
export function params(open) {
  const q = new URLSearchParams(location.search);
  const hops = Number(q.get('hops'));
  const picked = (q.get('kinds') ?? '').split(',').filter((k) => KINDS.includes(k));
  return { center: q.get('center') || `record:${open}`, hops: hops >= 1 && hops <= 3 ? hops : 1, kinds: picked.length ? picked : KINDS };
}

export const query = ({ center, hops, kinds }) => `/api/graph?center=${center}&hops=${hops}&kinds=${kinds.join(',')}`;

function svg(tag, attrs, ...children) {
  const el = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  el.append(...children);
  return el;
}

const text = (x, y, content, attrs) => {
  const el = svg('text', { x, y, 'text-anchor': 'middle', ...attrs });
  el.textContent = content;
  return el;
};

/** Each hop is an ellipse around the centre; a node sits near the angle of its parent so edges stay short. */
function place(graph, mid) {
  const hopOf = new Map(graph.nodes.map((n) => [n.id, n.hop]));
  const spot = new Map([[graph.center, mid]]);
  const angle = new Map([[graph.center, -Math.PI / 2]]);
  const parentAngle = (n) => {
    const parent = graph.edges.map((e) => (e.from === n.id ? e.to : e.to === n.id ? e.from : null))
      .find((other) => other && hopOf.get(other) === n.hop - 1);
    return angle.get(parent) ?? 0;
  };
  const rings = ringsFor(graph.hops);
  rings.forEach(([rx, ry], index) => {
    const ring = graph.nodes.filter((n) => n.hop > 0 && Math.min(n.hop, rings.length) === index + 1)
      .sort((a, b) => parentAngle(a) - parentAngle(b) || a.hop - b.hop);
    ring.forEach((n, i) => {
      // The outer ring is turned half a step so its nodes miss the inner ring's on the horizontal axis.
      const a = -Math.PI / 2 + (2 * Math.PI * (i + (index ? 0.5 : 0))) / ring.length;
      angle.set(n.id, a);
      spot.set(n.id, [mid[0] + rx * Math.cos(a), mid[1] + ry * Math.sin(a)]);
    });
  });
  return spot;
}

const clip = (s, n = 24) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
const heading = (n) => (n.type === 'source_item' ? n.title.split(':')[0].replace(/^./, (c) => c.toUpperCase()) : n.title ?? n.id);
const subtitle = (n) => {
  if (n.type === 'record') return [n.record_kind, n.lifecycle].filter(Boolean).join(' · ');
  return n.type === 'source_item' && n.quote ? `"${clip(n.quote, 28)}"` : n.type.replace('_', ' ');
};

/** Where the line from one node's centre toward another leaves the first node's box. */
function border([x, y], [tx, ty]) {
  const [dx, dy] = [tx - x, ty - y];
  const t = Math.min(NODE[0] / 2 / Math.abs(dx || 1e-9), NODE[1] / 2 / Math.abs(dy || 1e-9));
  return [x + dx * t, y + dy * t];
}

function labelSpot(a, b, mid) {
  const dist = ([x, y]) => Math.hypot(x - mid[0], y - mid[1]);
  const [near, far] = dist(a) <= dist(b) ? [a, b] : [b, a];
  return [near[0] + (far[0] - near[0]) * 0.65, near[1] + (far[1] - near[1]) * 0.65 - 4];
}

function canvas(graph, open) {
  const H = height(graph.hops);
  const mid = [W / 2, H / 2];
  const spot = place(graph, mid);
  const hopOf = new Map(graph.nodes.map((n) => [n.id, n.hop]));
  const recentre = (id) => filters.href({ open, tab: 'relations', center: id === `record:${open}` ? null : id });
  const edges = graph.edges.map((e) => {
    const [from, to] = [spot.get(e.from), spot.get(e.to)];
    const [x1, y1] = border(from, to);
    const [x2, y2] = border(to, from);
    return svg('g', { class: `edge hop-${Math.max(hopOf.get(e.from), hopOf.get(e.to))}`, 'data-part': 'graph-edge', 'data-kind': e.kind },
      svg('line', { x1, y1, x2, y2, stroke: '#9A95AD', 'stroke-width': 1.5, 'marker-end': 'url(#arrow)' }),
      // Nearer the outer node: edges converge on the centre, so midpoint labels pile up there.
      text(...labelSpot([x1, y1], [x2, y2], mid), label(e.kind), { fill: '#9A95AD', 'font-size': 12 }));
  });
  const arrow = svg('defs', {}, svg('marker', { id: 'arrow', markerWidth: 8, markerHeight: 8, refX: 7, refY: 4, orient: 'auto' },
    svg('path', { d: 'M0,0 L8,4 L0,8z', fill: '#9A95AD' })));
  const nodes = graph.nodes.map((n) => {
    const [x, y] = spot.get(n.id);
    const tip = svg('title', {});
    tip.textContent = n.title ?? n.id;
    return svg('a', { href: recentre(n.id), 'data-link': '', class: `node hop-${n.hop} ${n.type}${n.id === graph.center ? ' center' : ''}`, 'data-part': 'graph-node', 'data-id': n.id },
      tip,
      svg('rect', { x: x - NODE[0] / 2, y: y - NODE[1] / 2, width: NODE[0], height: NODE[1], rx: n.type === 'person' ? 24 : 12 }),
      text(x, y - 3, clip(heading(n)), { fill: '#EDEAF5', 'font-size': 14 }),
      text(x, y + 14, subtitle(n), { fill: '#9A95AD', 'font-size': 11 }));
  });
  return svg('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': 'Relations', 'data-part': 'relations-graph' }, arrow, ...edges, ...nodes);
}

const chip = (content, to, on, part, extra = {}) =>
  h('a', { href: to, class: on ? 'chip on' : 'chip', 'data-link': true, 'data-part': part, ...extra }, content);

/** A person node's menu: one of its Aliases (the first, until edited) can move to another Person or split off. */
function personMenu(node, open, people) {
  const alias = h('input', { type: 'text', value: node.aliases[0] ?? node.title, 'aria-label': 'Alias', 'data-part': 'person-alias' });
  return h('details', { class: 'pmenu', 'data-part': 'person-menu', 'data-id': node.id },
    h('summary', {}, node.title),
    alias, aliasControls({ alias: () => alias.value, from: Number(node.id.split(':')[1]), recordId: open, people }));
}

/** The Relations tab: the hop control, the edge-kind filters and the graph itself. */
export function view(graph, open, state, people) {
  const link = (change) => filters.href({ open, tab: 'relations', ...change });
  const toggled = (kind) => {
    const kinds = state.kinds.includes(kind) ? state.kinds.filter((k) => k !== kind) : [...state.kinds, kind];
    return kinds.length === KINDS.length ? null : KINDS.filter((k) => kinds.includes(k)).join(',');
  };
  const all = state.kinds.length === KINDS.length;
  return h('div', { 'data-part': 'relations' },
    canvas(graph, open),
    graph.nodes.filter((n) => n.type === 'person').map((n) => personMenu(n, open, people)),
    h('div', { class: 'legend', 'data-part': 'graph-legend' },
      h('small', {}, 'solid = 1 hop'),
      h('small', {}, 'faded = 2 hops'),
      h('small', {}, 'click a node to re-centre'),
      h('details', { class: 'kind-filter', 'data-part': 'kind-filter', open: !all },
        h('summary', {}, `filter: ${all ? 'all edge kinds' : `${state.kinds.length} of ${KINDS.length} edge kinds`} ▾`),
        h('div', { class: 'tabs' }, KINDS.map((k) => chip(label(k), link({ kinds: toggled(k) }), state.kinds.includes(k), 'kind', { 'data-kind': k })))),
      h('span', { class: 'tabs', 'data-part': 'hop-control' },
        h('small', {}, 'hops:'),
        [1, 2, 3].map((n) => chip(String(n), link({ hops: n === 1 ? null : String(n) }), state.hops === n, 'hop', { 'data-hops': n })))));
}
