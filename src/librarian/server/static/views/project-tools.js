import { change } from '../actions.js';
import { h } from '../dom.js';
import * as filters from '../filters.js';

/** Confirm, rename, merge and split a project, from its status header. `items` are the Records that may leave it. */
export function projectTools(project, projects, items) {
  const failed = h('p', { class: 'w', 'data-part': 'project-error' });
  // A rename or merge changes the name the page is filtered by, so the page follows it.
  const go = (action, body, shownAs = project.name) =>
    change(`/api/projects/${project.id}/${action}`, action, project.id, body, failed, filters.href({ project: shownAs }));
  const field = (part, placeholder) => h('input', { type: 'text', placeholder, 'aria-label': placeholder, 'data-part': part });
  const button = (part, text, onClick) => {
    const el = h('button', { type: 'button', class: 'chip', 'data-part': part }, text);
    el.addEventListener('click', onClick);
    return el;
  };

  const name = field('project-name', 'New name');
  const merge = h('select', { 'data-part': 'project-merge', 'aria-label': 'Merge into' },
    h('option', { value: '' }, 'Merge into…'),
    projects.filter((p) => p.id !== project.id).map((p) => h('option', { value: p.id }, p.title)));
  merge.addEventListener('change', () => merge.value && go('merge', { into: Number(merge.value) }, merge.selectedOptions[0].textContent));

  const splitName = field('split-name', 'Name of the new project');
  const picks = items.map((i) => h('label', { class: 'm', 'data-part': 'split-item' },
    h('input', { type: 'checkbox', value: i.id }), i.title));
  const split = h('details', { 'data-part': 'project-split' }, h('summary', {}, 'Split…'), splitName, picks,
    button('split-go', 'Split off the ticked items', () => go('split', {
      name: splitName.value, record_ids: picks.map((p) => p.firstChild).filter((c) => c.checked).map((c) => Number(c.value)),
    })));

  return h('div', { class: 'acts', 'data-part': 'project-tools' },
    button('project-confirm', 'Confirm', () => go('confirm', {})),
    name, button('project-rename', 'Rename', () => go('rename', { name: name.value }, name.value)),
    merge, split, failed);
}
