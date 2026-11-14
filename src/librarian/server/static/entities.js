import * as api from './api.js';
import { h } from './dom.js';
import { btn, icon } from './ui.js';
import { openForm, closeDialog, toast } from './shell.js';
import { reason } from './actions.js';

/** The workspace's own settings row. Everything else is read from the item, person or tag itself. */
let settings = { sound: false };
export async function load() { settings = await api.get('/api/settings'); }
export const soundOn = () => settings.sound;
export async function setSound(on) { settings = await api.post('/api/settings', { sound: on }); }
export const refresh = () => window.librarianNavigate(location.pathname + location.search);
/** The star on a person (`kind` 'person') or a tag ('project'); it saves to that row's own `favorite`. */
export function favorite(kind, entity, title) {
  const on = !!entity.favorite;
  const url = kind === 'person' ? `/api/people/${entity.id}/favorite` : `/api/tags/${entity.id}`;
  return btn(icon('star'), { cls: `iconbtn ghost ${on ? 'starred' : ''}`,
    'aria-label': `${on ? 'Unfavorite' : 'Favorite'} ${title}`, 'aria-pressed': String(on),
    onClick: async () => { try { await api.post(url, { favorite: !on }); refresh(); } catch (e) { toast(reason(e)); } } });
}
export const priority = (item) => item.priority ?? 70;
export function priorityBadge(item) {
  const n = priority(item);
  return h('span', { class: 'today-priority' }, icon('flag', 'small'), `${n >= 80 ? 'High' : n >= 60 ? 'Medium' : 'Low'} priority · ${n}`);
}
const input = (name, value = '', extra = {}) => h('input', { name, value, ...extra });
const field = (label, node) => h('label', {}, label, node);

export async function itemForm(item = null) {
  const { projects } = await api.get('/api/open-items?scope=all');
  const tag = h('select', { name: 'project', 'aria-label': 'Tag' }, h('option', { value: '' }, 'No tag'),
    projects.map((p) => h('option', { value: p.id, selected: item?.projects?.[0]?.id === p.id }, p.title)));
  openForm(item ? 'Edit item' : 'New item', [
    field('Title', input('title', item?.title ?? '', { required: true, maxlength: 120, placeholder: 'What needs to move forward?' })),
    field('Summary', h('textarea', { name: 'body', required: true }, item?.body ?? '')),
    h('div', { class: 'row' }, field('Tag', tag), field('Priority', h('select', { name: 'priority', 'aria-label': 'Priority' },
      [[94, 'High'], [70, 'Medium'], [40, 'Low']].map(([value, label]) => h('option', { value,
        selected: value === (item ? (priority(item) >= 80 ? 94 : priority(item) >= 60 ? 70 : 40) : 94) }, label))))),
    field('Due', input('due', item?.stated_deadline ?? '', { placeholder: 'Today, tomorrow, or a date', maxlength: 100 })),
  ], async (form, failed) => {
    const data = new FormData(form);
    const body = { title: data.get('title'), body: data.get('body'), due: data.get('due') };
    try {
      const id = item?.id ?? (await api.post('/api/create/item', { ...body,
        ...(tag.value ? { project_id: Number(tag.value) } : {}) })).id;
      await api.post(`/api/items/${id}/edit`, body);
      if (item && tag.value && Number(tag.value) !== item.projects?.[0]?.id)
        await api.post(`/api/items/${id}/project`, { project_id: Number(tag.value) });
      if (item && !tag.value && item.projects?.length) await api.post(`/api/items/${id}/unproject`, {});
      await api.post(`/api/items/${id}/priority`, { priority: Number(data.get('priority')) });
      closeDialog(); window.librarianNavigate(`/items/${id}`); toast('Saved');
    } catch (e) { failed.textContent = reason(e); }
  });
}
export function personForm(person = null) {
  openForm(person ? 'Edit person' : 'Add person', [
    field('Name', input('title', person?.name ?? '', { required: true, maxlength: 120, placeholder: 'Full name' })),
    field('Aliases (one per line)', h('textarea', { name: 'aliases' }, (person?.aliases ?? []).join('\n'))),
    field('Slack ID', input('slack_id', person?.slack_id ?? '', { maxlength: 100, placeholder: 'U0123456789' })),
    field('Email', input('email', person?.email ?? '', { type: 'email', maxlength: 254 })),
    field('Role', input('role', person?.role ?? '', { maxlength: 100, placeholder: 'Product designer' })),
    field('Department', input('department', person?.department ?? '', { maxlength: 100, placeholder: 'Design' })),
  ], async (form, failed) => {
    const data = Object.fromEntries(new FormData(form));
    const aliases = data.aliases.split('\n').map((s) => s.trim()).filter(Boolean);
    try {
      if (person) await api.post(`/api/people/${person.id}/profile`, { ...data, name: data.title, aliases });
      else {
        await api.post('/api/create/person', { ...data, aliases });
      }
      closeDialog(); refresh(); toast('Saved');
    } catch (e) { failed.textContent = reason(e); }
  });
}
export function tagForm(project = null) {
  openForm(project ? 'Edit tag' : 'New tag', [
    field('Name', input('title', project?.title ?? '', { required: true, maxlength: 120 })),
    field('Description', input('body', project?.body ?? '', { maxlength: 5000 })),
    field('Accent color', input('color', project?.color ?? '#dca666', { type: 'color' })),
  ], async (form, failed) => {
    const data = Object.fromEntries(new FormData(form));
    try {
      const { id } = await api.post(project ? `/api/items/${project.id}/edit` : '/api/create/project', data);
      await api.post(`/api/tags/${id}`, { color: data.color });
      closeDialog(); refresh(); toast('Saved');
    } catch (e) { failed.textContent = reason(e); }
  });
}
export function playSound() {
  if (!settings.sound) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = ctx.createOscillator(), gain = ctx.createGain();
    oscillator.frequency.setValueAtTime(660, ctx.currentTime);
    oscillator.frequency.setValueAtTime(880, ctx.currentTime + .09);
    gain.gain.setValueAtTime(.05, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(.001, ctx.currentTime + .3);
    oscillator.connect(gain); gain.connect(ctx.destination);
    oscillator.start(); oscillator.stop(ctx.currentTime + .3); oscillator.onended = () => ctx.close();
  } catch { /* Audio may be unavailable. */ }
}
export function checklist(item) {
  const rows = (item.subitems ?? []).map((child) => {
    const done = child.lifecycle === 'done';
    const box = input('complete', '', { type: 'checkbox', class: 'check', checked: done,
      'aria-label': `${done ? 'Reopen' : 'Complete'} ${child.title}` });
    box.addEventListener('change', async () => {
      box.disabled = true;
      try { await api.post(`/api/items/${child.id}/${box.checked ? 'done' : 'reopen'}`, {}); refresh(); }
      catch (e) { box.checked = done; box.disabled = false; toast(reason(e)); }
    });
    return h('div', { class: 'row subitem', 'data-part': 'subitem' }, box,
      btn(child.title, { cls: 'textbtn', href: `/items/${child.id}` }));
  });
  const title = input('title', '', { placeholder: 'Add a sub-item…', 'aria-label': 'New sub-item', required: true, maxlength: 120 });
  const submit = h('button', { type: 'submit', class: 'primary' }, icon('plus'), 'Add');
  const form = h('form', { class: 'row subitem-form' }, title, submit);
  const error = h('p', { class: 'w', role: 'alert' });
  form.addEventListener('submit', async (event) => {
    event.preventDefault(); if (!title.value.trim()) return;
    submit.disabled = true;
    try {
      await api.post('/api/create/item', { title: title.value.trim(), body: '', parent_id: item.id });
      refresh();
    } catch (e) { error.textContent = reason(e); submit.disabled = false; }
  });
  return h('div', { class: 'checklist', 'data-part': 'subitems' }, rows,
    rows.length ? null : h('p', { class: 'small' }, 'No sub-items yet.'), form, error);
}
export function notes(item) {
  const list = h('div', {});
  const draw = () => list.replaceChildren(...(item.notes ?? []).map((n) => h('div', { class: 'message' },
    h('div', { class: 'avatar me' }, 'You'), h('div', { class: 'message-body' },
      h('strong', {}, 'You ', h('time', {}, `· Private note · ${new Date(n.time).toLocaleString()}`)), h('p', { style: 'white-space:pre-wrap' }, n.text)))));
  draw();
  const area = h('textarea', { name: 'note', placeholder: 'Add a private note…', 'aria-label': 'Private note', required: true, maxlength: 5000 });
  const submit = h('button', { type: 'submit', class: 'primary' }, 'Save note');
  const form = h('form', { class: 'note-box' }, area, submit);
  form.addEventListener('submit', async (event) => {
    event.preventDefault(); if (!area.value.trim()) return;
    submit.disabled = true;
    try {
      ({ notes: item.notes } = await api.post(`/api/items/${item.id}/notes`, { text: area.value.trim() }));
      area.value = ''; draw(); toast('Private note saved');
    } catch (e) { toast(reason(e)); } finally { submit.disabled = false; }
  });
  return h('div', {}, list, form);
}
