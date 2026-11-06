import { change } from '../actions.js';
import { h } from '../dom.js';

/** Move an Alias (`alias()` reads it, so a field can supply it) to another Person or split it off to a new one. `recordId` is the Record whose wrong link
 * prompted it; it settles when the page is drawn again. Used by a review row and by a person node in Relations. */
export function aliasControls({ alias, from, recordId, people }) {
  const failed = h('span', { class: 'w', 'data-part': 'alias-error' });
  const body = (extra) => ({ alias: alias(), from_person_id: from, record_id: recordId, ...extra });
  const move = h('select', { 'data-part': 'alias-move', 'aria-label': 'Move this Alias to' },
    h('option', { value: '' }, 'Move to…'),
    people.filter((p) => p.id !== from).map((p) => h('option', { value: p.id }, p.name)));
  move.addEventListener('change', () => move.value && change('/api/aliases/move', 'move_alias', recordId, body({ to_person_id: Number(move.value) }), failed));
  const split = h('button', { type: 'button', class: 'chip', 'data-part': 'alias-split' }, 'Split off');
  split.addEventListener('click', () => change('/api/aliases/split', 'split', recordId, body({}), failed));
  return h('span', { class: 'acts', 'data-part': 'alias-controls' }, move, split, failed);
}
