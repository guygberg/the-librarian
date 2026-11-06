import { h } from './dom.js';
import * as freshness from './freshness.js';
import { start } from './router.js';
import { stream } from './views/stream.js';
import * as sheet from './views/sheet.js';
import * as search from './search.js';

search.bind(document.getElementById('search'));

const routes = { '/': stream, '/items/:id': stream };
const notFound = async () => h('p', { class: 'empty' }, 'Nothing here.');

let visit = 0;
let shown = null;

/** The page and its sheet, told apart: opening or closing the sheet leaves the stream (and its scroll position) alone. */
function where() {
  const q = new URLSearchParams(location.search);
  const source = q.get('source');
  q.delete('source');
  return { page: `${location.pathname}?${q}`, source };
}

async function render(view) {
  const mine = ++visit;
  const now = where();
  const sheetOnly = shown?.page === now.page && shown.source !== now.source;
  const [node] = await Promise.all([
    sheetOnly ? null : view(), freshness.render(document.getElementById('freshness')),
    search.render(document.getElementById('search'), document.getElementById('results')),
  ]);
  if (mine !== visit) return;
  await sheet.render(document.getElementById('sheet'));
  if (mine !== visit) return;
  if (!sheetOnly) document.getElementById('view').replaceChildren(node);
  shown = now;
}

start(routes, notFound, render);
