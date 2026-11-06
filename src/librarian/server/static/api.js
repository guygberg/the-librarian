const token = document.querySelector('meta[name="librarian-token"]').content;
let cache = new Map();

/** GET a JSON path with the page's token. Repeat calls within one navigation share a single request. */
export function get(path) {
  if (!cache.has(path)) {
    cache.set(path, fetch(path, { headers: { 'X-Librarian-Token': token } }).then((resp) => {
      if (!resp.ok) throw new Error(`${path}: ${resp.status}`);
      return resp.json();
    }));
  }
  return cache.get(path);
}

export async function post(path, body) {
  const resp = await fetch(path, {
    method: 'POST', headers: { 'X-Librarian-Token': token, 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`${path}: ${resp.status}`);
  return resp.json();
}

/** Called by the router on every navigation so a view never shows another visit's answers. */
export function forget() {
  cache = new Map();
}
