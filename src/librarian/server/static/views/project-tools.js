import { change } from '../actions.js';
import { h } from '../dom.js';
import * as filters from '../filters.js';
import { btn } from '../ui.js';

/** Confirm, rename, merge and split a project. `items` are the Records that may leave it. */
export function projectTools(project, projects, items, stay = null) {
  const failed = h('p', { class: 'w', 'data-part': 'project-error' });
  // On Items a rename or merge changes the name the page is filtered by, so the page follows it; `stay` keeps another page put.
  const go = (action, body, shownAs = project.name) =>
    change(`/api/projects/${project.id}/${action}`, action, project.id, body, failed, stay ?? filters.href({ project: shownAs }));
  const field = (part, placeholder) => h('input', { type: 'text', class: 'select field', placeholder, 'aria-label': placeholder, 'data-part': part });

  const name = field('project-name', 'New name');
  const merge = h('select', { class: 'select', 'data-part': 'project-merge', 'aria-label': 'Merge into' },
    h('option', { value: '' }, 'Merge into…'),
    projects.filter((p) => p.id !== project.id).map((p) => h('option', { value: p.id }, p.title)));
  merge.addEventListener('change', () => merge.value && go('merge', { into: Number(merge.value) }, merge.selectedOptions[0].textContent));

  const splitName = field('split-name', 'Name of the new project');
  const picks = items.map((i) => h('label', { class: 'pick', 'data-part': 'split-item' },
    h('input', { type: 'checkbox', class: 'check', value: i.id }), i.title));
  const split = h('details', { class: 'split', 'data-part': 'project-split' }, h('summary', {}, 'Split…'), splitName, picks,
    btn('Split off the ticked items', { 'data-part': 'split-go', onClick: () => go('split', {
      name: splitName.value, record_ids: picks.map((p) => p.firstChild).filter((c) => c.checked).map((c) => Number(c.value)),
    }) }));

  return h('div', { class: 'tools', 'data-part': 'project-tools' },
    h('div', { class: 'row tools-row' },
      btn('Confirm', { 'data-part': 'project-confirm', onClick: () => go('confirm', {}) }),
      name, btn('Rename', { 'data-part': 'project-rename', onClick: () => go('rename', { name: name.value }, name.value) }),
      merge),
    split, failed);
}
