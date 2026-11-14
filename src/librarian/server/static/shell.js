import { soundOn, setSound, playSound } from './entities.js';
import * as api from './api.js';
import { h } from './dom.js';
import * as filters from './filters.js';
import { clock, dateLine, dayBefore, isToday, parseLocal, shortDate } from './format.js';
import { btn, icon, select } from './ui.js';

export const NAV = [
  { path: '/', label: 'Today', icon: 'home' },
  { path: '/items', label: 'Items', icon: 'items' },
  { path: '/people', label: 'People', icon: 'people' },
  { path: '/projects', label: 'Tags', icon: 'tag' },
  { path: '/review', label: 'Suggestions', icon: 'spark' },
];

const THEME_KEY = 'librarian-theme';
const $ = (part) => document.querySelector(`[data-part=${part}]`);

function remembered() {
  try { return localStorage.getItem(THEME_KEY); } catch { return null; }
}

function setTheme(theme) {
  document.body.classList.toggle('light', theme === 'light');
  try { localStorage.setItem(THEME_KEY, theme); } catch { /* the choice just does not persist */ }
  $('theme-toggle').replaceChildren(icon('sun'), theme === 'light' ? 'Dark mode' : 'Light mode');
}

const toggleTheme = () => setTheme(document.body.classList.contains('light') ? 'dark' : 'light');

const PHONE = matchMedia('(max-width: 760px)');
const sidebar = () => document.getElementById('sidebar');

/** On a phone the closed drawer is off screen, so it must not be reachable by Tab or a screen reader. */
function syncDrawer() {
  sidebar().inert = PHONE.matches && !sidebar().classList.contains('open');
}

function setDrawer(open) {
  const was = sidebar().classList.contains('open');
  sidebar().classList.toggle('open', open);
  $('scrim').hidden = !open;
  $('menu').setAttribute('aria-expanded', String(open));
  syncDrawer();
  if (open) document.querySelector('#nav .nav.active, #nav .nav')?.focus();
  else if (was) $('menu').focus();
}

function active(path, here) {
  if (path === '/') return here === '/';
  return here === path || here.startsWith(`${path}/`) || (path === '/items' && here === '/import');
}

/** Mark the nav entry of the page being shown, and close the drawer a navigation came from. */
export function markActive() {
  for (const link of document.querySelectorAll('#nav .nav')) {
    const on = active(link.getAttribute('data-href'), location.pathname);
    link.classList.toggle('active', on);
    if (on) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  }
  setDrawer(false);
}

function openSettings() {
  openDialog('Settings',
    h('p', { style: 'margin-bottom:18px' }, 'Everything here stays on this computer. Sources are only ever read, never changed.'),
    h('div', { class: 'stack' },
      btn([icon('sun'), 'Switch theme'], { onClick: toggleTheme, 'data-part': 'settings-theme' }),
      btn([icon('download'), 'Import sources'], { href: '/import', onClick: closeDialog }),
      btn([icon('spark'), 'Review suggestions'], { href: '/review', onClick: closeDialog })));
}

export function bind() {
  $('menu').replaceChildren(icon('menu'));
  $('open-import').replaceChildren(icon('sound'));
  $('open-import').removeAttribute('data-href');
  $('open-import').removeAttribute('role');
  $('open-import').setAttribute('aria-label', 'Toggle completion sound');
  $('open-import').addEventListener('click', async () => {
    try {
      await setSound(!soundOn());
      $('open-import').setAttribute('aria-pressed', String(soundOn()));
      toast('Completion sound ' + (soundOn() ? 'on' : 'off')); playSound();
    } catch { toast('Could not save sound setting.'); }
  });
  $('settings').replaceChildren(icon('settings'));
  $('settings').addEventListener('click', openSettings);
  $('search').prepend(icon('search'));
  document.getElementById('nav').replaceChildren(...NAV.map(({ path, label, icon: name }) =>
    btn([icon(name), label, path === '/review' ? h('span', { class: 'counter', 'data-part': 'review-total', hidden: true }) : null],
      { cls: 'nav', href: path })));
  $('sidebar-bottom').replaceChildren(
    btn([], { cls: 'textbtn', 'data-part': 'theme-toggle', onClick: toggleTheme }),
    btn([icon('reset'), 'Import sources'], { cls: 'textbtn', href: '/import', 'data-part': 'sidebar-import' }),
    h('span', { class: 'demo-label', 'data-part': 'date-line' }));
  PHONE.addEventListener('change', syncDrawer);
  syncDrawer();
  setTheme(remembered() === 'light' ? 'light' : 'dark');
  $('menu').addEventListener('click', () => setDrawer(!sidebar().classList.contains('open')));
  $('scrim').addEventListener('click', () => setDrawer(false));
  addEventListener('keydown', (event) => {
    if (event.key === 'Escape') setDrawer(false);
  });
}

// The order the sources are read in.
const SOURCES = { slack: 'Slack', session: 'Claude sessions', drive: 'Recordings' };

function importedAt(state) {
  if (!state.last_import_finished_at) return 'never imported';
  const at = parseLocal(state.last_import_finished_at);
  return isToday(at) ? `${clock(at)} today` : `through ${shortDate(at)}`;
}

/** One source's Freshness in the sidebar, drawn as the reference draws a quest: its name, when it was last imported, and a full or empty track. */
function sourceRow(name, state) {
  const stale = !state.last_import_finished_at || state.overdue;
  return btn([
    h('span', { class: 'quest-label' }, h('span', {}, SOURCES[name]), h('span', { class: stale ? 'quest-ratio w' : 'quest-ratio' }, importedAt(state))),
    h('span', { class: 'quest-track', 'aria-hidden': 'true' }, h('span', { class: 'quest-fill', style: `width:${stale ? 0 : 100}%` })),
  ], { cls: 'quest', href: '/import', 'data-part': 'import-source-fresh', 'data-source': name });
}

/** "Last import 09:12." for the empty state; names the day when it was not today. */
export function lastImport(freshness) {
  if (!freshness.last_import_finished_at) return 'No import yet.';
  const at = parseLocal(freshness.last_import_finished_at);
  return `Last import ${isToday(at) ? '' : `${shortDate(at)} `}${clock(at)}.`;
}

const SINCE = [['0', 'Today'], ['1', 'Yesterday'], ['7', 'Last 7 days'], ['30', 'Last 30 days']];

/** The four filters of the top bar. Choosing one opens the Items list narrowed by it. */
function topFilters({ records, projects, people }, state) {
  const go = (change) => window.librarianNavigate(filters.href(change));
  const names = (list) => [...new Set(list.filter(Boolean))].sort();
  const owners = names(records.map((r) => r.owner));
  const waiting = names(records.map(filters.waitingOn));
  const person = h('select', { class: 'select filter-people', 'aria-label': 'Filter person', 'data-part': 'person-filter' },
    h('option', { value: '' }, 'People'),
    h('optgroup', { label: 'Owner' }, owners.map((n) => h('option', { value: `owner:${n}`, selected: state.owner === n, 'data-part': 'owner-option' }, n))),
    h('optgroup', { label: 'Waiting on' }, waiting.map((n) => h('option', { value: `waiting:${n}`, selected: state.waiting === n, 'data-part': 'waiting-option' }, n))),
    state.person ? h('option', { value: `person:${state.person}`, selected: true }, state.person) : null);
  person.addEventListener('change', () => {
    const [key, ...name] = person.value.split(':');
    go({ owner: null, waiting: null, person: null, ...(person.value ? { [key]: name.join(':') } : {}) });
  });
  const dates = SINCE.map(([days, label]) => [dayBefore(Number(days)), label]);
  const known = !state.since || dates.some(([day]) => day === state.since);
  return [
    select('Filter status', [['', 'Status & priority'], ...['open', 'pending', 'suspended', 'done', 'dropped', 'superseded'].map((l) => [l, l.replace(/^./, (c) => c.toUpperCase())]), ['priority:high', 'High priority'], ['priority:medium', 'Medium priority'], ['priority:low', 'Low priority']],
      state.priority ? `priority:${state.priority}` : state.lifecycle,
      (v) => go(v.startsWith('priority:') ? { priority: v.split(':')[1], lifecycle: null } : { priority: null, lifecycle: v || null }),
      { class: 'select filter-status', 'data-part': 'lifecycle-filter' }),
    select('Filter project', [['', 'Tags'], ...projects.map((p) => p.title)],
      state.project, (v) => go({ project: v || null }), { class: 'select filter-tags', 'data-part': 'project-filter' }),
    person,
    select('Filter date', [['', 'Date'], ...dates, ...(known ? [] : [[state.since, `Since ${state.since}`]])],
      state.since, (v) => go({ since: v || null }), { class: 'select filter-date', 'data-part': 'since-filter' }),
  ];
}

/** The parts of the shell that come from the Workspace: this week's progress, the Review count, Freshness and the top bar's filters. */
export async function render() {
  const [answer, { count }, status] = await Promise.all([
    api.get('/api/open-items?scope=all'), api.get('/api/review'), api.get('/api/status')]);
  $('open-import').setAttribute('aria-pressed', String(soundOn()));
  const finished = answer.records.filter((r) => r.lifecycle === 'done');
  const xp = finished.length * 20;
  const level = 1 + Math.floor(xp / 150);
  const dates = new Set(finished.filter((r) => r.done_at).map((r) => new Date(r.done_at).toLocaleDateString()));
  let streak = 0;
  const day = new Date();
  if (!dates.has(day.toLocaleDateString())) day.setDate(day.getDate() - 1);
  while (dates.has(day.toLocaleDateString())) { streak++; day.setDate(day.getDate() - 1); }
  $('week').replaceChildren(
    h('div', { class: 'between' }, h('span', {}, `▣ Lv ${level} · ${level < 3 ? 'Builder' : 'Chief Builder'}`), h('span', { class: 'gold' }, `♨ ${streak}d`)),
    h('div', { class: 'progress' }, h('span', { style: `width:${xp % 150 / 150 * 100}%` })),
    h('span', { class: 'micro' }, `${xp} XP · ${150 - xp % 150} to next level`));
  const total_ = $('review-total');
  total_.textContent = String(count);
  total_.hidden = !count;
  const sources = Object.keys(SOURCES).filter((name) => name in answer.freshness.sources);
  const history = answer.records.flatMap((r) => r.history ?? []).filter((e) => isToday(new Date(e.at)));
  const closed = finished.filter((r) => r.done_at && isToday(new Date(r.done_at))).length;
  const reviewed = history.filter((e) => ['accept_suggestion', 'reject_suggestion', 'confirm'].includes(e.event)).length;
  const tidied = history.filter((e) => ['project_move', 'rename', 'edit'].includes(e.event)).length;
  const quest = (label, n, target, href) => btn([
    h('span', { class: 'quest-label' }, h('span', {}, label), h('span', { class: 'quest-ratio' }, `${n}/${target}`)),
    h('span', { class: 'quest-track' }, h('span', { class: 'quest-fill', style: `width:${Math.min(100, n / target * 100)}%` })),
  ], { cls: 'quest', href });
  document.getElementById('freshness').replaceChildren(
    h('div', { class: 'section-label' }, 'DAILY QUESTS'),
    quest('Review 3 suggestions', reviewed, 3, '/review'),
    quest('Close 2 items', closed, 2, '/items'),
    quest('Tidy 5 things', tidied, 5, '/projects'));
  $('date-line').textContent = `${dateLine(new Date())} · ${status.workspace}`;
  // On a phone the sidebar is a closed drawer, so Freshness is repeated as one line under the top bar.
  const line = [];
  sources.forEach((name, i) => line.push(i ? ' · ' : 'Updated from ',
    h('span', { class: !answer.freshness.sources[name].last_import_finished_at || answer.freshness.sources[name].overdue ? 'w' : null },
      `${SOURCES[name].toLowerCase()} ${importedAt(answer.freshness.sources[name])}`)));
  document.getElementById('fresh-line').replaceChildren(h('a', { href: '/import', 'data-link': true }, ...line));
  const bar = $('topbar');
  bar.querySelectorAll('select').forEach((el) => el.remove());
  $('open-import').before(...topFilters(answer, filters.current()));
}

export function loading(text = 'Loading') {
  return h('p', { class: 'state loading', role: 'status', 'data-part': 'loading' }, text);
}

export function failure(text) {
  return h('p', { class: 'state error', role: 'alert', 'data-part': 'error' }, icon('alert', 'small'), text);
}

let toastTimer = null;

/** A short confirmation; `undo` adds the reference's Undo button. */
export function toast(text, undo = null) {
  const el = document.getElementById('toast');
  el.replaceChildren(icon('check'), h('span', {}, text),
    undo ? btn('Undo', { 'data-part': 'undo', onClick: () => { el.classList.remove('show'); undo(); } }) : null);
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 4500);
}

export function closeDialog() {
  const dialog = document.getElementById('dialog');
  if (dialog.open) dialog.close();
}

/** Open the page dialog with a heading and body nodes; Escape and the close button dismiss it. */
export function openDialog(title, ...body) {
  const dialog = document.getElementById('dialog');
  dialog.replaceChildren(
    h('div', { class: 'between', style: 'margin-bottom:17px' }, h('h2', {}, title),
      btn(icon('close'), { cls: 'iconbtn ghost', 'aria-label': 'Close dialog', onClick: closeDialog })),
    ...body);
  if (!dialog.open) dialog.showModal();
  return dialog;
}

/** A dialog that asks for something: its fields, then Cancel and Save. `save` gets the form and where to say why it failed. */
export function openForm(title, fields, save, label = 'Save') {
  const failed = h('p', { class: 'w', 'data-part': 'form-error', role: 'alert' });
  const form = h('form', {}, fields, failed, h('div', { class: 'modal-footer' },
    btn('Cancel', { onClick: closeDialog }), h('button', { class: 'primary', type: 'submit', 'data-part': 'form-save' }, label)));
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const submit = form.querySelector('[type=submit]');
    submit.disabled = true;
    try { await save(form, failed); }
    catch (error) { failed.textContent = error.body?.error ?? error.message; }
    finally { submit.disabled = false; }
  });
  return openDialog(title, form);
}
