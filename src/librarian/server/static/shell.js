import * as api from './api.js';
import { h } from './dom.js';
import { icon } from './icons.js';

export const NAV = [
  { path: '/', label: 'Today', icon: 'home' },
  { path: '/items', label: 'Items', icon: 'items' },
  { path: '/people', label: 'People', icon: 'people' },
  { path: '/tags', label: 'Tags', icon: 'tags' },
  { path: '/review', label: 'Suggestions', icon: 'sparkle' },
];

const THEME_KEY = 'librarian-theme';
const $ = (part) => document.querySelector(`[data-part=${part}]`);

function remembered() {
  try { return localStorage.getItem(THEME_KEY); } catch { return null; }
}

function setTheme(theme) {
  document.body.classList.toggle('light', theme === 'light');
  try { localStorage.setItem(THEME_KEY, theme); } catch { /* the choice just does not persist */ }
  const toggle = $('theme-toggle');
  toggle.replaceChildren(icon('sun'), theme === 'light' ? 'Dark theme' : 'Light theme');
}

const PHONE = matchMedia('(max-width: 760px)');

/** On a phone the closed drawer is off screen, so it must not be reachable by Tab or a screen reader. */
function syncDrawer() {
  const open = document.body.classList.contains('drawer-open');
  document.getElementById('sidebar').inert = PHONE.matches && !open;
}

function setDrawer(open) {
  const was = document.body.classList.contains('drawer-open');
  document.body.classList.toggle('drawer-open', open);
  $('scrim').hidden = !open;
  $('menu').setAttribute('aria-expanded', String(open));
  syncDrawer();
  if (open) document.querySelector('#nav a.active, #nav a')?.focus();
  else if (was) $('menu').focus();
}

function active(path, here) {
  if (path === '/') return here === '/';
  return here === path || here.startsWith(`${path}/`) || (path === '/items' && here === '/import');
}

/** Mark the nav entry of the page being shown, and close the drawer a navigation came from. */
export function markActive() {
  for (const link of document.querySelectorAll('#nav a')) {
    const on = active(link.getAttribute('data-path'), location.pathname);
    link.classList.toggle('active', on);
    if (on) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  }
  setDrawer(false);
  showReviewCount();
}

/** The Review entry carries the same count as Today and the Review page: one answer, `/api/review`. */
async function showReviewCount() {
  try {
    const { count } = await api.get('/api/review');
    const link = document.querySelector('#nav a[data-path="/review"]');
    link.querySelector('[data-part=nav-review-count]')?.remove();
    if (count) link.append(h('span', { class: 'navcount', 'data-part': 'nav-review-count' }, String(count)));
  } catch { /* the badge is a convenience; the page reports its own failure */ }
}

export function bind() {
  $('menu').replaceChildren(icon('menu'));
  document.getElementById('nav').replaceChildren(
    ...NAV.map(({ path, label, icon: name }) => h('a', { class: 'nav', href: path, 'data-link': true, 'data-path': path }, icon(name), label)),
  );
  PHONE.addEventListener('change', syncDrawer);
  syncDrawer();
  setTheme(remembered() === 'light' ? 'light' : 'dark');
  $('theme-toggle').addEventListener('click', () => setTheme(document.body.classList.contains('light') ? 'dark' : 'light'));
  $('menu').addEventListener('click', () => setDrawer(!document.body.classList.contains('drawer-open')));
  $('scrim').addEventListener('click', () => setDrawer(false));
  addEventListener('keydown', (event) => {
    if (event.key === 'Escape') setDrawer(false);
  });
}

export function loading(text = 'Loading') {
  return h('p', { class: 'state loading', role: 'status', 'data-part': 'loading' }, text);
}

export function failure(text) {
  return h('p', { class: 'state error', role: 'alert', 'data-part': 'error' }, icon('alert', 'small'), text);
}

export function toast(text) {
  const el = document.getElementById('toast');
  el.textContent = text;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3500);
}

/** Open the page dialog with a heading and body nodes; Escape and the close button dismiss it. */
export function openDialog(title, ...body) {
  const dialog = document.getElementById('dialog');
  const close = h('button', { type: 'button', class: 'iconbtn ghost', 'aria-label': 'Close' }, icon('close'));
  close.addEventListener('click', () => dialog.close());
  dialog.replaceChildren(h('div', { class: 'between' }, h('h2', {}, title), close), ...body);
  dialog.showModal();
  return dialog;
}
