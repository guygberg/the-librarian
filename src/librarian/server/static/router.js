import * as api from './api.js';

/** Every view has its own URL. `routes` maps an exact path to a view; `notFound` renders anything else. */
export function start(routes, notFound, render) {
  const show = () => {
    api.forget();
    render(routes[location.pathname] ?? notFound);
  };
  addEventListener('popstate', show);
  document.addEventListener('click', (event) => {
    const link = event.target.closest?.('a[data-link]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
    event.preventDefault();
    navigate(link.getAttribute('href'));
  });
  window.librarianNavigate = navigate;
  show();

  function navigate(path) {
    if (path !== location.pathname) history.pushState(null, '', path);
    show();
  }
}
