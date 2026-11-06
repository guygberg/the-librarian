import * as api from '../api.js';
import { h } from '../dom.js';
import * as filters from '../filters.js';
import { position } from '../format.js';

const SOURCES = { slack: 'Slack', session: 'Session', drive: 'Recording' };

const HEBREW = /[֐-׿]/;

const who = (item) => item.user ?? item.role ?? (item.start === undefined ? '' : position(item.start));

/** The text with each uncertain span (character offsets from the server) dotted-underlined. */
function words(item) {
  const out = [];
  let at = 0;
  for (const { start, end } of item.uncertain_words ?? []) {
    out.push(item.text.slice(at, start), h('mark', { class: 'unc', 'data-part': 'uncertain-underline' }, item.text.slice(start, end)));
    at = end;
  }
  return [...out, item.text.slice(at)];
}

/** The English gloss under a quote: labelled machine translation, and it names the words transcription doubted. */
function glossLine(item, gloss) {
  const doubted = (item.uncertain_words ?? []).map((w) => `“${w.text}”`).join(', ');
  return h('div', { class: 'gloss', 'data-part': 'gloss' }, gloss.gloss,
    doubted ? ` (uncertain: ${doubted})` : null,
    h('span', { class: 'tag', 'data-part': 'gloss-label' }, gloss.label));
}

/** Who said a recording line: pick a Person, or type a name (it becomes an Alias). The server rewrites the owner of
 * every Record built from the line; drawing the page again shows it. */
function speakerMenu(item, people) {
  const set = async (body) => {
    await api.post('/api/speaker', { locator: item.locator, ...body });
    window.librarianNavigate(location.pathname + location.search);
  };
  const pick = h('select', { 'data-part': 'speaker-pick', 'aria-label': 'Set speaker' },
    h('option', { value: '' }, 'Set speaker'), people.map((p) => h('option', { value: p.id }, p.name)));
  pick.addEventListener('change', () => pick.value && set({ person_id: Number(pick.value) }));
  const typed = h('input', { type: 'text', placeholder: 'or type a name', 'aria-label': 'Speaker name', 'data-part': 'speaker-name' });
  typed.addEventListener('keydown', (e) => e.key === 'Enter' && typed.value.trim() && set({ name: typed.value.trim() }));
  return h('span', { class: 'speaker', 'data-part': 'speaker-menu' }, pick, typed);
}

function line(item, gloss, people) {
  const hebrew = HEBREW.test(item.text);
  return h('div', { class: item.evidence ? 'ln hl' : 'ln', 'data-part': item.evidence ? 'evidence-line' : 'source-line' },
    h('span', { class: 'who' }, who(item)),
    h('span', {},
      people ? speakerMenu(item, people) : null,
      h('span', { dir: hebrew ? 'rtl' : 'auto', lang: hebrew ? 'he' : null, class: hebrew ? 'he' : null, 'data-part': 'quote' }, words(item)),
      item.confidence ? h('span', { class: 'tag', 'data-part': 'low-confidence' }, item.confidence.label) : null,
      item.gone_from_source ? h('span', { class: 'tag', 'data-part': 'gone-from-source' }, 'gone from Slack') : null,
      item.evidence && gloss ? glossLine(item, gloss) : null));
}

/** A recording's original is the file itself, in a player already at the Evidence segment. The browser sends the
 * page's cookie with the media request, since a media element cannot carry the token header. */
function player(found) {
  const [fileId] = found.locator.slice('drive:'.length).split('/');
  const video = h('video', { controls: true, preload: 'metadata', src: `/media/drive/${encodeURIComponent(fileId)}`, 'data-part': 'player' });
  video.currentTime = found.items.find((i) => i.evidence).start;
  return video;
}

/** "Open original": Slack opens the message itself; a session shows the copied `.jsonl` lines. */
function original(found, raw) {
  if (found.source === 'drive') return player(found);
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
  const people = found.source === 'drive' ? (await api.get('/api/open-items?scope=all')).people : null;
  const raw = h('pre', { class: 'raw', 'data-part': 'raw-passage', hidden: true },
    found.items.map((i) => i.raw).filter(Boolean).join('\n'));
  const close = filters.href({ open, tab: tab === 'relations' ? tab : null });
  host.replaceChildren(h('div', { class: 'sheet', 'data-part': 'source-sheet' },
    h('div', { class: 'wrap' },
      h('a', { href: close, class: 'chip', 'data-link': true, 'data-part': 'close-sheet' }, 'Close'),
      h('b', {}, SOURCES[found.source] ?? found.source), ` · ${found.locator}`,
      h('div', { class: 'passage' }, found.items.map((i) => line(i, found.glosses[0], people))),
      original(found, raw),
      raw)));
}
