import { itemForm, playSound } from '../entities.js';
import { act } from '../actions.js';
import * as api from '../api.js';
import { h } from '../dom.js';
import * as filters from '../filters.js';
import { shortDate } from '../format.js';
import { closeDialog, openDialog, openForm, toast } from '../shell.js';
import { btn, icon } from '../ui.js';

const UNKNOWN_SPEAKER = 'unknown_speaker';

/** The owner's name, or null when the owner is only a guess from an unknown speaker. */
export function ownerName(item) {
  const suggested = (item.suggested ?? []).some((s) => s.link === 'owner' && s.kind === UNKNOWN_SPEAKER);
  return suggested ? null : item.owner ?? null;
}

/** Who owns it, in a word: "You", a first name, or "No owner". */
export function ownerLabel(item) {
  if (item.owner_is_me) return 'You';
  return ownerName(item) ?? 'No owner';
}

/** What the sources say about an item in a sentence, or null when they say nothing beyond its title. */
export function summary(item) {
  if (item.body) return item.body;
  if (item.reasoning) return item.reasoning;
  const on = filters.waitingOn(item);
  return on ? `Waiting on ${on}.` : null;
}

/** One line for a card, which always has one: the summary, else the item's project and deadline, else when it was last mentioned. */
export function blurb(item) {
  const parts = [
    item.projects.length ? item.projects.map((p) => p.title).join(', ') : null,
    item.stated_deadline ? `Due ${item.stated_deadline}` : null,
  ].filter(Boolean);
  return summary(item) ?? (parts.join(' · ') || (item.last_evidence ? `Last mentioned ${shortDate(new Date(item.last_evidence))}.` : ownerLabel(item)));
}

/** Finish or reopen an item, confirmed by a toast whose Undo does the opposite. */
export async function complete(item) {
  const done = item.lifecycle === 'done';
  await act(item.id, done ? 'reopen' : 'done');
  if (!done) playSound();
  toast(done ? 'Item reopened' : 'Item complete · +20 XP', () => act(item.id, done ? 'done' : 'reopen'));
}

/** The reference's "Assign item" dialog: choosing an owner is a Person event; the source is never touched. */
export function assign(item, people) {
  const select = h('select', { name: 'owner', 'data-part': 'act-owner' },
    h('option', { value: '' }, 'Choose a person'),
    people.map((p) => h('option', { value: p.id, selected: p.name === item.owner }, p.is_me ? `${p.name} (you)` : p.name)));
  openForm('Assign item', [
    h('p', {}, item.title),
    h('label', {}, 'Who owns the next step?', select),
    h('p', { class: 'small' }, 'This is your own correction. Nothing changes in the source.'),
  ], () => (select.value ? act(item.id, 'owner', { person_id: Number(select.value) }) : closeDialog()));
}

/** The reference's "Item actions" dialog, with the corrections this Record allows. */
export function itemMenu(item, people, projects) {
  const move = h('select', { 'data-part': 'act-project', 'aria-label': 'Move to project' },
    h('option', { value: '' }, 'Move to project…'),
    projects.map((p) => h('option', { value: p.id, selected: p.id === item.projects[0]?.id }, p.title)));
  move.addEventListener('change', () => move.value && act(item.id, 'project', { project_id: Number(move.value) }));
  openDialog('Item actions', h('div', { class: 'stack' },
    btn([icon('doc'), 'Edit details'], { onClick: () => itemForm(item), 'data-part': 'menu-edit' }),
    !item.is_tag ? btn([icon('user'), 'Assign item'], { onClick: () => assign(item, people), 'data-part': 'menu-assign' }) : null,
    btn([icon('check'), item.lifecycle === 'done' ? 'Reopen' : 'Mark done'], { onClick: () => { closeDialog(); complete(item); }, 'data-part': 'menu-complete' }),
    h('label', {}, 'Project', move)));
}

/** What changed since the person last dismissed this strip; gone for good until something changes again. */
export function changedStrip({ last_visit: last, changed }) {
  if (!changed) return null;
  const strip = h('div', { class: 'panel filter-banner', 'data-part': 'changed-strip' },
    icon('spark', 'small'),
    h('span', {}, last ? `${changed} changed since your last visit` : `${changed} records so far`),
    btn('Dismiss ×', { cls: 'textbtn', 'data-part': 'changed-dismiss', onClick: async () => {
      await api.post('/api/visit/seen', {});
      strip.remove();
    } }));
  return strip;
}
