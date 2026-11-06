import * as api from '../api.js';
import { h } from '../dom.js';
import * as filters from '../filters.js';

const SOURCES = { slack: 'Slack', session: 'Session', drive: 'Recording' };

const who = (item) => item.user ?? item.role ?? item.start ?? '';

function line(item, gloss) {
  return h('div', { class: item.evidence ? 'ln hl' : 'ln', 'data-part': item.evidence ? 'evidence-line' : 'source-line' },
    h('span', { class: 'who' }, who(item)),
    h('span', {},
      h('span', { dir: 'auto' }, item.text),
      item.evidence && gloss ? h('div', { class: 'gloss', 'data-part': 'gloss' }, gloss.gloss) : null));
}

/** "Open original": Slack opens the message itself; a session shows the copied `.jsonl` lines. */
function original(found, raw) {
  if (found.permalink) {
    return h('a', { href: found.permalink, target: '_blank', rel: 'noopener', 'data-part': 'open-original' }, 'Open original ↗');
  }
  if (found.source !== 'session') return null;
  const button = h('button', { type: 'button', class: 'chip', 'data-part': 'open-original' }, 'Open original');
  button.addEventListener('click', () => {
    raw.hidden = !raw.hidden;
    button.classList.toggle('on', !raw.hidden);
  });
  return button;
}

/** The bottom sheet for `?source=<locator>`: the passage around one Evidence line, which is marked. Closing is a
 * link back to the same page without `source`, so the stream underneath is never re-rendered. */
export async function render(host) {
  const { open, tab, source } = filters.current();
  if (!source) return host.replaceChildren();
  const { context: found } = await api.get(`/api/context?locator=${encodeURIComponent(source)}`);
  const raw = h('pre', { class: 'raw', 'data-part': 'raw-passage', hidden: true },
    found.items.map((i) => i.raw).filter(Boolean).join('\n'));
  const close = filters.href({ open, tab: tab === 'relations' ? tab : null });
  host.replaceChildren(h('div', { class: 'sheet', 'data-part': 'source-sheet' },
    h('div', { class: 'wrap' },
      h('a', { href: close, class: 'chip', 'data-link': true, 'data-part': 'close-sheet' }, 'Close'),
      h('b', {}, SOURCES[found.source] ?? found.source), ` · ${found.locator}`,
      h('div', { class: 'passage' }, found.items.map((i) => line(i, found.glosses[0]))),
      original(found, raw),
      raw)));
}
