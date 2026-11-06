const token = document.querySelector('meta[name="librarian-token"]').content;
let cache = new Map();

/** Both methods fail the same way: an Error carrying the response `status` and parsed `body`. */
async function request(path, init) {
  const resp = await fetch(path, { ...init, headers: { 'X-Librarian-Token': token, ...init.headers } });
  if (!resp.ok) throw Object.assign(new Error(`${path}: ${resp.status}`), { status: resp.status, body: await resp.json().catch(() => null) });
  return resp.json();
}

/** GET a JSON path with the page's token. Repeat calls within one navigation share a single request. */
export function get(path) {
  if (!cache.has(path)) cache.set(path, request(path, {}));
  return cache.get(path);
}

export function post(path, body) {
  return request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
}

/** Called by the router on every navigation so a view never shows another visit's answers. */
export function forget() {
  cache = new Map();
}
