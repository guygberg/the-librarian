import { h } from '../dom.js';
import * as filters from '../filters.js';

export const KINDS = ['belongs_to', 'owner', 'waiting_on', 'blocks', 'supersedes', 'related_to', 'mentions', 'evidence'];
const NS = 'http://www.w3.org/2000/svg';
const W = 980, H = 430, MID = [W / 2, H / 2], NODE = [190, 48];
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
function place(graph) {
  const hopOf = new Map(graph.nodes.map((n) => [n.id, n.hop]));
  const spot = new Map([[graph.center, MID]]);
  const angle = new Map([[graph.center, -Math.PI / 2]]);
  const parentAngle = (n) => {
    const parent = graph.edges.map((e) => (e.from === n.id ? e.to : e.to === n.id ? e.from : null))
      .find((other) => other && hopOf.get(other) === n.hop - 1);
    return angle.get(parent) ?? 0;
  };
  for (let hop = 1; hop <= graph.hops; hop++) {
    const ring = graph.nodes.filter((n) => n.hop === hop).sort((a, b) => parentAngle(a) - parentAngle(b));
    ring.forEach((n, i) => {
      const a = -Math.PI / 2 + (2 * Math.PI * i) / ring.length;
      angle.set(n.id, a);
      const t = graph.hops === 1 ? 1 : 0.6 + (0.4 * (hop - 1)) / (graph.hops - 1); // share of the outer ellipse
      spot.set(n.id, [MID[0] + (graph.hops === 1 ? 300 : 380 * t) * Math.cos(a), MID[1] + (graph.hops === 1 ? 140 : 175 * t) * Math.sin(a)]);
    });
  }
  return spot;
}

const clip = (s, n = 24) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
const subtitle = (n) => (n.type === 'record' ? [n.record_kind, n.lifecycle].filter(Boolean).join(' · ') : n.type);

/** Where the line from one node's centre toward another leaves the first node's box. */
function border([x, y], [tx, ty]) {
  const [dx, dy] = [tx - x, ty - y];
  const t = Math.min(NODE[0] / 2 / Math.abs(dx || 1e-9), NODE[1] / 2 / Math.abs(dy || 1e-9));
  return [x + dx * t, y + dy * t];
}

function canvas(graph, open) {
  const spot = place(graph);
  const hopOf = new Map(graph.nodes.map((n) => [n.id, n.hop]));
  const recentre = (id) => filters.href({ open, tab: 'relations', center: id === `record:${open}` ? null : id });
  const edges = graph.edges.map((e) => {
    const [from, to] = [spot.get(e.from), spot.get(e.to)];
    const [x1, y1] = border(from, to);
    const [x2, y2] = border(to, from);
    return svg('g', { class: `edge hop-${Math.max(hopOf.get(e.from), hopOf.get(e.to))}`, 'data-part': 'graph-edge', 'data-kind': e.kind },
      svg('line', { x1, y1, x2, y2, stroke: '#9A95AD', 'stroke-width': 1.5, 'marker-end': 'url(#arrow)' }),
      text((x1 + x2) / 2, (y1 + y2) / 2 - 4, label(e.kind), { fill: '#9A95AD', 'font-size': 12 }));
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
      text(x, y - 3, clip(n.title ?? n.id), { fill: '#EDEAF5', 'font-size': 14 }),
      text(x, y + 14, subtitle(n), { fill: '#9A95AD', 'font-size': 11 }));
  });
  return svg('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': 'Relations', 'data-part': 'relations-graph' }, arrow, ...edges, ...nodes);
}

const chip = (content, to, on, part, extra = {}) =>
  h('a', { href: to, class: on ? 'chip on' : 'chip', 'data-link': true, 'data-part': part, ...extra }, content);

/** The Relations tab: the hop control, the edge-kind filters and the graph itself. */
export function view(graph, open, state) {
  const link = (change) => filters.href({ open, tab: 'relations', ...change });
  const toggled = (kind) => {
    const kinds = state.kinds.includes(kind) ? state.kinds.filter((k) => k !== kind) : [...state.kinds, kind];
    return kinds.length === KINDS.length ? null : KINDS.filter((k) => kinds.includes(k)).join(',');
  };
  return h('div', { 'data-part': 'relations' },
    h('div', { class: 'tabs', 'data-part': 'hop-control' },
      h('small', {}, 'hops'),
      [1, 2, 3].map((n) => chip(String(n), link({ hops: n === 1 ? null : String(n) }), state.hops === n, 'hop', { 'data-hops': n }))),
    h('div', { class: 'tabs', 'data-part': 'kind-filter' },
      KINDS.map((k) => chip(label(k), link({ kinds: toggled(k) }), state.kinds.includes(k), 'kind', { 'data-kind': k }))),
    canvas(graph, open),
    h('small', { class: 'legend', 'data-part': 'graph-legend' }, 'solid = 1 hop · faded = further out · click a node to re-centre'));
}
