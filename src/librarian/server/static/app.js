import { h } from './dom.js';
import * as freshness from './freshness.js';
import { start } from './router.js';
import { stream } from './views/stream.js';

const routes = { '/': stream };
const notFound = async () => h('p', { class: 'empty' }, 'Nothing here.');

let visit = 0;

async function render(view) {
  const mine = ++visit;
  const [node] = await Promise.all([view(), freshness.render(document.getElementById('freshness'))]);
  if (mine === visit) document.getElementById('view').replaceChildren(node);
}

start(routes, notFound, render);
