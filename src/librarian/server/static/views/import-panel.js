import * as api from '../api.js';
import { h } from '../dom.js';
import { clock, isToday, parseLocal, shortDate } from '../format.js';

const SOURCES = { slack: 'Slack', session: 'Claude sessions', drive: 'Recordings' };
const COUNTERS = ['fetched', 'transcribed', 'extracted', 'failed'];
const POLL_MS = 1000;

const fresh = (path) => {
  api.forget();
  return api.get(path);
};

/** The answer of a refused or failed request: the server's JSON body, or the error text. */
const reply = (promise) => promise.catch((e) => e.body ?? { error: e.message });

function lastImport(state) {
  if (!state.last_import_finished_at) return 'never imported';
  const at = parseLocal(state.last_import_finished_at);
  return isToday(at) ? `last import ${clock(at)} today` : `last import ${shortDate(at)}`;
}

function sources(progress) {
  return h('div', { 'data-part': 'import-sources' },
    Object.entries(progress.freshness.sources).map(([name, state]) =>
      h('div', { class: state.overdue ? 'm w' : 'm', 'data-part': 'import-source' },
        h('span', {}, SOURCES[name] ?? name), h('span', {}, lastImport(state)))));
}

/** One line per source, in the CLI's wording, so the two can be compared. */
function counters(progress) {
  const status = progress.running ? 'Import running' : progress.run ? `Last import ${progress.run.status}` : 'No import yet';
  return h('div', { 'data-part': 'import-progress' },
    h('div', { class: 'grp' }, status),
    Object.entries(progress.sources).map(([name, n]) =>
      h('div', { class: 'm', 'data-part': 'import-counts' }, `${name}: ${COUNTERS.map((c) => `${c} ${n[c]}`).join(', ')}`)),
    progress.calls ? h('div', { class: 'm' }, `${progress.calls} Claude calls`) : null);
}

function failedItems(progress) {
  return h('div', { 'data-part': 'failed-items' },
    h('div', { class: 'grp' }, 'Failed, retried by the next Import'),
    progress.failed.length
      ? progress.failed.map((f) => h('div', { class: 'm', 'data-part': 'failed-item' },
        h('span', {}, `${f.source}/${f.item}`), h('span', { 'data-part': 'failed-stage' }, f.stage), h('span', { class: 'w' }, f.error)))
      : h('p', { class: 'empty' }, 'Nothing failed.'));
}

function forgetControl(row, say, reload) {
  const slot = h('span', {});
  const ask = () => {
    const typed = h('input', { type: 'text', placeholder: `type ${row.name}`, 'data-part': 'forget-text' });
    const go = h('button', { type: 'button', disabled: true, 'data-part': 'forget-confirm' }, 'Forget for good');
    typed.addEventListener('input', () => { go.disabled = typed.value !== row.name; });
    go.addEventListener('click', async () => {
      const done = await reply(api.post('/api/forget', { conversation: row.id, confirm: true }));
      say(done.error ?? `Forgot ${row.name}.`);
      reload();
    });
    slot.replaceChildren(typed, go);
  };
  const button = h('button', { type: 'button', 'data-part': 'forget' }, 'Forget');
  button.addEventListener('click', ask);
  return h('span', {}, button, slot);
}

function olderControl(row, say, started) {
  const ask = async () => {
    const { count, error } = await reply(fresh(`/api/slack/import-older?conversation=${encodeURIComponent(row.id)}`));
    if (error) return say(error);
    const go = h('button', { type: 'button', 'data-part': 'older-confirm' }, `Fetch ${count} older messages`);
    go.addEventListener('click', async () => {
      go.remove();
      const done = await reply(api.post('/api/slack/import-older', { conversation: row.id, confirm: true }));
      say(done.error ?? `Fetching older history of ${row.name}.`);
      started();
    });
    say(`${count} older messages in ${row.name}. `, go);
  };
  const button = h('button', { type: 'button', 'data-part': 'older' }, 'Import older');
  button.addEventListener('click', ask);
  return button;
}

export async function importPanel() {
  const message = h('p', { class: 'pnote', 'data-part': 'panel-message' });
  const say = (...parts) => message.replaceChildren(...parts);
  const top = h('div', {});
  const picker = h('div', { 'data-part': 'slack-picker' });
  const root = h('div', { 'data-part': 'import-panel' });
  let timer = null;

  const showProgress = async () => {
    const progress = await fresh('/api/import');
    top.replaceChildren(sources(progress), counters(progress), failedItems(progress));
    if (!progress.running) {
      clearInterval(timer);
      timer = null;
    }
    return progress;
  };
  // The panel polls only while it is on screen and an Import runs.
  const watch = () => {
    if (timer) return;
    timer = setInterval(() => (root.isConnected ? showProgress() : clearInterval(timer)), POLL_MS);
  };
  const started = async () => {
    if ((await showProgress()).running) watch();
  };

  const importButton = h('button', { type: 'button', 'data-part': 'import-button' }, 'Import');
  importButton.addEventListener('click', async () => {
    const done = await reply(api.post('/api/import/start', {}));
    say(done.error ?? 'Import started.');
    await started();
  });
  const dryRun = h('button', { type: 'button', 'data-part': 'dry-run-button' }, 'Dry run');
  dryRun.addEventListener('click', async () => {
    const done = await reply(api.post('/api/import/dry-run', {}));
    say(done.error ?? `${done.calls} Claude calls would be made; nothing was sent.`);
  });

  const drawPicker = ({ conversations, note }) => {
    picker.replaceChildren(
      h('div', { class: 'grp' }, 'Slack conversations'),
      h('p', { class: 'pnote', 'data-part': 'picked-note' }, note),
      ...conversations.map((row) => {
        const box = h('input', { type: 'checkbox', checked: row.picked, 'data-part': 'pick-box', 'aria-label': row.name });
        box.addEventListener('change', async () => {
          drawPicker(await api.post('/api/slack/picks', { [box.checked ? 'pick' : 'unpick']: [row.id] }));
        });
        return h('div', { class: 'm', 'data-part': 'pick-row' },
          box, h('span', {}, row.name), h('span', {}, `${row.kind}, ${row.members} members`),
          row.picked ? olderControl(row, say, started) : null,
          forgetControl(row, say, loadPicker));
      }));
  };
  // Slack may be unreachable (no login yet); the rest of the panel still works.
  const loadPicker = () => fresh('/api/slack/picks').then(drawPicker, (e) => picker.replaceChildren(
    h('div', { class: 'grp' }, 'Slack conversations'), h('p', { class: 'pnote w', 'data-part': 'picker-error' }, `Cannot list conversations: ${e.message}`)));

  root.append(h('div', { class: 'grp' }, 'Import'), top, h('div', { class: 'm' }, importButton, dryRun), message, picker);
  await Promise.all([started(), loadPicker()]);
  return root;
}
