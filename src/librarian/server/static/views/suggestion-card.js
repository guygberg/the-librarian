import { change } from '../actions.js';
import { h } from '../dom.js';
import { evidenceLine } from './expanded.js';

const LABELS = { new_tag: 'Suggested new tag', new_item: 'Suggested new item', link: 'Suggested link' };
const NEW = { new_tag: 'new tag', new_item: 'new item' };
const LINKS = {
  belongs_to: 'belongs to', owner: 'is owned by', waiting_on: 'is waiting on', blocks: 'blocks',
  supersedes: 'supersedes', related_to: 'is related to', mentions: 'mentions', contradicts: 'contradicts',
};
/** A low grade is said out loud: the number alone reads as a verdict. */
const BAND_NOTE = { high: 'High confidence', medium: 'Medium confidence', low: 'Low confidence: this may well be wrong' };

const end = (e) => h('span', { class: 'sg-end', dir: 'auto', 'data-part': 'suggestion-end' }, e.title ?? 'unknown',
  NEW[e.type] ? h('small', {}, ` (${NEW[e.type]})`) : null);

/** What the card is about, naming both ends of a link. */
function subject(row) {
  if (row.kind !== 'link') return h('span', { dir: 'auto' }, row.title);
  return [end(row.from), h('small', { class: 'sg-rel' }, ` ${LINKS[row.link_type] ?? row.link_type} `), end(row.to)];
}

function button(part, text, onClick) {
  const el = h('button', { type: 'button', class: part === 'suggestion-accept' ? 'chip primary' : 'chip', 'data-part': part }, text);
  el.addEventListener('click', onClick);
  return el;
}

/** One Suggestion with its grade, reasoning and verbatim Evidence. Nothing exists until Accept. */
export function suggestionCard(row) {
  const failed = h('p', { class: 'w', 'data-part': 'review-error' });
  const settle = (name) => () => change(`/api/suggestions/${row.id}/${name}`, name, row.id, {}, failed);
  return h('article', { class: `it sg ${row.band}`, 'data-part': 'suggestion', 'data-kind': row.kind, 'data-band': row.band },
    h('div', { class: 'sg-label', 'data-part': 'suggestion-label' }, LABELS[row.kind]),
    h('div', { class: 't', 'data-part': 'suggestion-title' }, subject(row)),
    h('div', { class: 'sg-grade', 'data-part': 'suggestion-grade', title: BAND_NOTE[row.band] },
      h('span', { 'data-part': 'suggestion-confidence' }, `${row.confidence}% confident`),
      h('span', { class: 'sg-bar', role: 'img', 'aria-label': BAND_NOTE[row.band] }, h('i', { style: `width:${row.confidence}%` })),
      h('small', { 'data-part': 'suggestion-band' }, BAND_NOTE[row.band])),
    h('p', { class: 'pnote', dir: 'auto', 'data-part': 'suggestion-reasoning' }, row.reasoning),
    row.evidence.map((e) => evidenceLine(e)),
    h('div', { class: 'acts' },
      button('suggestion-dismiss', 'Dismiss', settle('reject')),
      button('suggestion-accept', 'Accept', settle('accept'))),
    failed);
}

/** The compact Today line: the same label and grade, opening the full card on Review. */
export const suggestionLine = (row) => h('div', { class: 'it', 'data-part': 'today-suggestion', 'data-band': row.band },
  h('div', { class: 'm' }, h('span', {}, LABELS[row.kind]), h('span', {}, `${row.confidence}% confident`)),
  h('div', { class: 't' }, h('a', { href: '/review', 'data-link': true, dir: 'auto' }, subject(row))));
