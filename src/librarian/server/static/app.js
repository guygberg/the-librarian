import * as entities from './entities.js';
import { h } from './dom.js';
import { start } from './router.js';
import { items } from './views/items.js';
import { today } from './views/today.js';
import * as sheet from './views/sheet.js';
import { importPanel } from './views/import-panel.js';
import { people } from './views/people.js';
import { projects } from './views/projects.js';
import { review } from './views/review.js';
import * as search from './search.js';
import * as shell from './shell.js';

shell.bind();
search.bind(document.getElementById('search'));

const routes = {
  '/': today,
  '/items': items,
  '/items/:id': items,
  '/people': people,
  '/projects': projects,
  '/import': importPanel,
  '/review': review,
};
const notFound = async () => h('p', { class: 'empty' }, 'Nothing here.');

let visit = 0;
let shown = null;

/** The page and its sheet, told apart: opening or closing the sheet leaves the page (and its scroll position) alone. */
function where() {
  const q = new URLSearchParams(location.search);
  const sheetKey = JSON.stringify([q.get('source'), q.get('quote')]);
  q.delete('source');
  q.delete('quote');
  return { page: `${location.pathname}?${q}`, path: location.pathname, sheetKey };
}

async function render(view) {
  const mine = ++visit;
  shell.markActive();
  const now = where();
  const sheetOnly = shown?.page === now.page && shown.sheetKey !== now.sheetKey;
  await entities.load();
  const [node] = await Promise.all([
    sheetOnly ? null : view(), shell.render(),
    search.render(document.getElementById('search'), document.getElementById('results')),
  ]);
  if (mine !== visit) return;
  await sheet.render(document.getElementById('sheet'));
  if (mine !== visit) return;
  if (!sheetOnly) document.getElementById('view').replaceChildren(node);
  // A different page starts at its top; the same page drawn again (an action, a filter) stays where it was.
  if (shown && shown.path !== now.path) scrollTo(0, 0);
  shown = now;
}

start(routes, notFound, render);
