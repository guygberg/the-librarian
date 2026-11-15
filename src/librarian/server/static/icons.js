/** Line icons from the Mission Control reference (docs/reference/mission-control-lime.html), drawn on a 24px grid. */
const PATHS = {
  home: 'M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9',
  items: 'm3 8 9-5 9 5-9 5-9-5Zm0 5 9 5 9-5M3 18l9 5 9-5',
  people: 'M16 21v-3a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v3M17 5a4 4 0 0 1 0 8M22 21v-3a4 4 0 0 0-3-3.87M13 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  tags: 'M3 3h7v18H3V3ZM14 3h7v18h-7V3',
  review: 'm4 12 5 5L21 5',
  sparkle: 'M12 2c.6 5.5 4.5 9.4 10 10-5.5.6-9.4 4.5-10 10-.6-5.5-4.5-9.4-10-10 5.5-.6 9.4-4.5 10-10Z',
  search: 'M21 21l-5.2-5.2M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  menu: 'M3 5h18M3 12h18M3 19h18',
  close: 'M5 5l14 14M19 5 5 19',
  sun: 'M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1M17 12a5 5 0 1 1-10 0 5 5 0 0 1 10 0',
  alert: 'M12 3 2 21h20L12 3ZM12 10v5M12 18h.01',
};

const SVG = 'http://www.w3.org/2000/svg';

export function icon(name, cls = '') {
  const svg = document.createElementNS(SVG, 'svg');
  svg.setAttribute('class', `icon ${cls}`.trim());
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(SVG, 'path');
  path.setAttribute('d', PATHS[name] ?? PATHS.items);
  svg.append(path);
  return svg;
}
