import * as api from './api.js';

/** What the last action changed, read once by the next render so it can settle: `{ id, name }`. */
let last = null;

export function justActed() {
  const out = last;
  last = null;
  return out;
}

/** What a failed request says: the server's reason, or the error text (an expired token is a 403). */
export const reason = (e) => (e.status === 403 ? 'This page has expired. Reload it.' : e.body?.error ?? e.message);

/** Post a change, then draw the page again from the server's answers. The UI never marks anything for Claude.
 * On failure nothing changed: the reason is shown in `into` (when given) and the page stays as it was.
 * `to` is where the page goes afterwards, when the change moved what it was showing. */
export async function change(path, name, settles, body = {}, into = null, to = location.pathname + location.search) {
  try {
    await api.post(path, body);
  } catch (e) {
    if (!into) throw e;
    into.replaceChildren(reason(e));
    return;
  }
  last = { id: settles, name };
  window.librarianNavigate(to);
}

export const act = (id, name, body = {}, settles = id) => change(`/api/records/${id}/${name}`, name, settles, body);
