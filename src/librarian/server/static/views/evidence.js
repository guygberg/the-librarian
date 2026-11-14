import { h } from '../dom.js';
import * as filters from '../filters.js';
import { btn, icon } from '../ui.js';

const SOURCES = { slack: ['spark', 'Slack'], session: ['doc', 'Session'], drive: ['clip', 'Recording'] };

export const sourceOf = (e) => SOURCES[e.source ?? e.locator.split(':')[0]] ?? ['doc', 'Source'];

/** Where a click on an Evidence quote goes: the same page, with the source sheet open on that quote. */
export function sheetHref(e, open = null) {
  const state = filters.current();
  return filters.href({ open, tab: open ? filters.tabParam(state.tab) : null, source: e.locator, quote: e.quote, page: open ? null : state.page });
}

/** One Evidence quote, drawn as the reference draws a message. The quote opens its source in the sheet;
 * `open` is the Record whose page to stay on, if any. */
export function evidenceLine(e, withRole = false, open = null) {
  const [glyph, label] = sourceOf(e);
  return h('div', { class: 'message evidence', 'data-part': 'evidence' },
    h('span', { class: 'avatar', 'aria-hidden': 'true' }, icon(glyph, 'small')),
    h('div', { class: 'message-body' },
      h('strong', {}, label, ' ', h('time', {}, `· ${withRole ? `${e.locator} · ${e.role}` : e.locator}`)),
      h('p', {},
        btn(h('span', { dir: 'auto' }, e.quote), { cls: 'textbtn quote', href: sheetHref(e, open), 'data-part': 'evidence-quote' }),
        e.gone_from_source ? h('span', { class: 'tag', 'data-part': 'gone-from-source' }, 'gone from Slack') : null)));
}

/** The same Evidence as one row of the "Linked sources" card. */
export function sourceRow(e, open) {
  const [glyph, label] = sourceOf(e);
  return btn([icon(glyph), h('span', {}, `${label} · `, h('span', { dir: 'auto' }, e.quote)), icon('external', 'small')],
    { cls: 'source-row', href: sheetHref(e, open), 'data-part': 'linked-source' });
}
