import * as api from './api.js';

const CONTROLS = 'button, a, input, select, textarea, label';

/** Every view has its own URL. `routes` maps an exact path to a view (a numeric segment matches `:id`);
 * `notFound` renders anything else. Anything carrying `data-href` navigates in place when clicked. */
export function start(routes, notFound, render) {
  const show = () => {
    api.forget();
    render(routes[location.pathname] ?? routes[location.pathname.replace(/\/\d+$/, '/:id')] ?? notFound);
  };
  addEventListener('popstate', show);
  document.addEventListener('click', (event) => {
    if (event.defaultPrevented || event.button !== 0) return;
    const link = event.target.closest?.('[data-href], a[data-link]');
    if (!link || link.disabled) return;
    // A control inside a clickable card does its own job; the card does not also navigate.
    const inner = event.target.closest(CONTROLS);
    if (inner && inner !== link && link.contains(inner)) return;
    const to = link.getAttribute('data-href') ?? link.getAttribute('href');
    if (event.metaKey || event.ctrlKey || event.shiftKey) {
      if (link.tagName !== 'A') window.open(to, '_blank', 'noopener');
      return;
    }
    event.preventDefault();
    navigate(to);
  });
  window.librarianNavigate = navigate;
  show();

  function navigate(path) {
    if (path !== location.pathname + location.search) history.pushState(null, '', path);
    show();
  }
}
