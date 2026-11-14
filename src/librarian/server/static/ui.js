import { h } from './dom.js';
import { shortDate } from './format.js';
import { emblem, icon } from './icons.js';

export { emblem, icon };

export const NEEDS = 'needs_attention';
export const WAITING = 'waiting_on_others';
export const OTHER = 'other_open';

/** A button as the reference draws it. With `href` it navigates in place (the router listens for `data-href`). */
export function btn(content, { cls = '', href = null, onClick = null, ...attrs } = {}) {
  const el = h('button', { type: 'button', class: cls || null, 'data-href': href, role: href ? 'link' : null, ...attrs }, content);
  if (onClick) el.addEventListener('click', onClick);
  return el;
}

export const initials = (name) => (name ? name.split(/\s+/).slice(0, 2).map((s) => s[0]).join('').toUpperCase() : '–');

export function avatar(name, large = false) {
  return h('span', { class: large ? 'avatar large' : 'avatar', 'aria-hidden': 'true' }, initials(name));
}

/** The first name, as the reference shows owners. */
export const first = (name) => name?.split(/\s+/)[0] ?? null;

const STATUS = {
  [NEEDS]: ['needs', 'target', 'Needs you'],
  [WAITING]: ['waiting', 'hourglass', 'Waiting'],
  [OTHER]: ['progress', 'pulse', 'Open'],
};

const capital = (text) => text.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());

/** The status pill of an item: its open-items group while it is open, else its lifecycle. */
export function statusPill(item, attrs = {}) {
  const [cls, name, text] = item.lifecycle === 'done'
    ? ['completed', 'check', 'Completed']
    : STATUS[item.group] ?? ['', 'pulse', capital(item.lifecycle)];
  return h('span', { class: `pill ${cls}`.trim(), 'data-lifecycle': item.lifecycle, ...attrs }, icon(name, 'small'), text);
}

export const kindLabel = (kind) => capital(kind);

/** A Record's warnings, in words. The query core decides them; the browser only reads the flags. */
export function warnings(item) {
  const out = [];
  if (item.contradictions?.length) out.push('Sources disagree');
  if (item.transcription_uncertain) out.push('Transcription uncertain');
  if (item.stale && item.last_evidence) out.push(`Not mentioned since ${shortDate(new Date(item.last_evidence))}`);
  for (const s of item.suggested ?? []) out.push(s.mark);
  return out;
}

const BASIS = { inferred: ['inf', 'Inferred'], confirmed: ['conf', 'Confirmed'], stated: ['', 'Stated'] };

export function basisMark(basis) {
  const [cls, label] = BASIS[basis] ?? ['', basis];
  return h('span', { class: `tagchip basis ${cls}`.trim(), 'data-part': `basis-${basis}` }, label);
}

/** The page heading: emblem, title, subtitle and the page's one primary action. */
export function pageHead(title, subtitle, type, action = null, attrs = {}) {
  return h('div', { class: 'page-head', ...attrs }, emblem(type),
    h('div', { class: 'grow' }, h('h1', {}, title), h('p', { class: 'subtitle' }, subtitle)), action);
}

export function tabs(list) {
  return list.map(([text, to, on, n, part]) => btn([text, n === undefined ? null : [' ', h('span', { class: 'counter' }, String(n))]],
    { cls: on ? 'tab active' : 'tab', href: to, 'data-part': part, 'aria-current': on ? 'true' : null }));
}

/** "Showing 1–7 of 26 items" and the page buttons; `to(n)` is the URL of page n. */
export function pagination({ total, size, page, to, noun }) {
  const pages = Math.max(1, Math.ceil(total / size));
  return h('div', { class: 'pagination', 'data-part': 'pagination' },
    h('span', { 'data-part': 'page-range' }, `Showing ${total ? (page - 1) * size + 1 : 0}–${Math.min(page * size, total)} of ${total} ${noun}`),
    h('div', { class: 'pages' },
      btn(icon('back'), { cls: 'iconbtn', href: to(page - 1), disabled: page === 1, 'aria-label': 'Previous page', 'data-part': 'page-prev' }),
      Array.from({ length: pages }, (_, i) => btn(String(i + 1), { cls: page === i + 1 ? 'active' : '', href: to(i + 1), 'data-part': 'page' })),
      btn(icon('chevron'), { cls: 'iconbtn', href: to(page + 1), disabled: page === pages, 'aria-label': 'Next page', 'data-part': 'page-next' })));
}

export const clampPage = (page, total, size) => Math.min(Math.max(1, page), Math.max(1, Math.ceil(total / size)));

export function empty(title, text, attrs = {}) {
  return h('div', { class: 'empty', 'data-part': 'empty', ...attrs }, h('h2', {}, title), text ? h('p', {}, text) : null);
}

/** A labelled select in the reference's style; `choices` are values or [value, label] pairs, `on(value)` runs on change. */
export function select(label, choices, selected, on, attrs = {}) {
  const el = h('select', { class: 'select', 'aria-label': label, ...attrs },
    choices.map((c) => [].concat(c)).map(([value, text = value]) => h('option', { value, selected: (selected ?? '') === value }, text)));
  el.addEventListener('change', () => on(el.value));
  return el;
}
