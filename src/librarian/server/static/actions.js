import * as api from './api.js';

/** What the last action changed, read once by the next render so it can settle: `{ id, name }`. */
let last = null;

export function justActed() {
  const out = last;
  last = null;
  return out;
}

/** Run a Record action, then draw the page again from the server's answers. The UI never marks anything for Claude. */
export async function act(id, name, body = {}, settles = id) {
  await api.post(`/api/records/${id}/${name}`, body);
  last = { id: settles, name };
  window.librarianNavigate(location.pathname + location.search);
}
