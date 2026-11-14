/** Line icons from the Mission Control reference (docs/reference/mission-control-lime.html), drawn on a 24px grid. */
const PATHS = {
  sound: 'M3 9h4l5-5v16l-5-5H3V9ZM16 8a6 6 0 0 1 0 8M19 5a10 10 0 0 1 0 14',
  home: 'M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9',
  items: 'm3 8 9-5 9 5-9 5-9-5Zm0 5 9 5 9-5M3 18l9 5 9-5',
  people: 'M16 21v-3a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v3M17 5a4 4 0 0 1 0 8M22 21v-3a4 4 0 0 0-3-3.87M13 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  tag: 'M20 13 11 22 2 13V3h10l8 8a1.4 1.4 0 0 1 0 2ZM7 7h.01',
  spark: 'm12 2 2.7 7.3L22 12l-7.3 2.7L12 22l-2.7-7.3L2 12l7.3-2.7L12 2',
  search: 'M21 21l-5.2-5.2M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  chevron: 'm9 5 7 7-7 7',
  back: 'm15 5-7 7 7 7',
  down: 'm5 9 7 7 7-7',
  arrow: 'M3 12h18m-6-6 6 6-6 6',
  external: 'M6 18 20 4M9 4h11v11',
  check: 'm4 12 5 5L21 5',
  plus: 'M12 4v16M4 12h16',
  more: 'M4 12h.01M12 12h.01M20 12h.01',
  star: 'm12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.8-6.2-3.2L5.8 21 7 14.2 2 9.3l6.9-1L12 2',
  target: 'M21 3 12 12M15 3h6v6M20.5 11a9 9 0 1 1-8-8M16.8 11a5 5 0 1 1-4-4',
  hourglass: 'M5 3h14M5 21h14M6 3c0 6 6 6 6 9s-6 3-6 9M18 3c0 6-6 6-6 9s6 3 6 9',
  pulse: 'M2 12h5l3-9 4 18 3-9h5',
  user: 'M20 21v-3a5 5 0 0 0-5-5H9a5 5 0 0 0-5 5v3h16ZM16 5a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  sun: 'M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1M17 12a5 5 0 1 1-10 0 5 5 0 0 1 10 0',
  reset: 'M3 11a9 9 0 1 1 2 7M3 3v8h8',
  settings: 'm9 3-1 3-3 1-2 3 2 2-1 3 2 3 3-1 2 3 3-1 1-3 3-1 2-3-2-2 1-3-2-3-3 1-2-3-3 1ZM16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  list: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  board: 'M3 3h7v18H3V3ZM14 3h7v18h-7V3',
  doc: 'M14 2H4v20h16V8l-6-6Zm0 0v6h6M8 12h8M8 16h8',
  calendar: 'M3 5h18v17H3V5ZM3 10h18M7 2v6M17 2v6',
  flag: 'M4 22V3h15l-3 5 3 5H4',
  clip: 'm8 13 7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2M6 15l8-8',
  download: 'M12 3v13m-5-5 5 5 5-5M3 15v7h18v-7',
  sliders: 'M3 5h18M3 12h18M3 19h18M8 2v6M16 9v6M10 16v6',
  close: 'M5 5l14 14M19 5 5 19',
  menu: 'M3 5h18M3 12h18M3 19h18',
  cube: 'm12 2 10 6v10l-10 5-10-5V8l10-6ZM2 8l10 6 10-6M12 14v9M7 5l10 6',
  compass: 'm21 3-6 12-12 6L9 9l12-6ZM9 9l6 6',
  diamond: 'm12 2 10 10-10 10L2 12 10-10',
  alert: 'M12 3 2 21h20L12 3ZM12 10v5M12 18h.01',
};

const SVG = 'http://www.w3.org/2000/svg';

export function icon(name, cls = '') {
  const svg = document.createElementNS(SVG, 'svg');
  svg.setAttribute('class', `icon ${cls}`.trim());
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(SVG, 'path');
  path.setAttribute('d', PATHS[name] ?? PATHS.spark);
  svg.append(path);
  return svg;
}

/** The illustrated emblems of the reference. The markup is fixed drawing code, never data. */
function shapes(type) {
  if (type === 'items') {
    return [0, 20, 40].map((y) => `<path transform="translate(0 ${y})" d="M10 25 50 5 90 25 50 45Z" fill="url(#face)" stroke="url(#gold)" stroke-width="1.8"/><path transform="translate(0 ${y})" d="M10 25v7l40 20 40-20v-7L50 45Z" fill="#79421d" stroke="url(#gold)"/>`).reverse().join('');
  }
  if (type === 'people') {
    return '<ellipse cx="50" cy="49" rx="44" ry="25" transform="rotate(-35 50 49)" fill="none" stroke="url(#gold)" stroke-width="3"/>'
      + [[49, 47, 14], [18, 75, 9], [78, 14, 9]].map(([x, y, r]) => `<circle cx="${x}" cy="${y}" r="${r}" fill="url(#gold)" stroke="#e0ae70"/><circle cx="${x - 3}" cy="${y - 4}" r="${r / 3}" fill="#ffe8bb" opacity=".7"/>`).join('');
  }
  if (type === 'tags') {
    return '<path d="M10 58 61 8 88 5 96 15 92 41 42 92 11 65Z" fill="#68401f" stroke="#ca9555" stroke-width="2"/><path d="M10 52 61 3 87 2 92 12 88 37 40 84 10 58Z" fill="url(#face)" stroke="url(#gold)" stroke-width="2"/><ellipse cx="77" cy="15" rx="8" ry="6" transform="rotate(-30 77 15)" fill="#211a12" stroke="#e8b875" stroke-width="2"/>';
  }
  if (type === 'chip') {
    return '<rect x="20" y="20" width="60" height="60" fill="url(#face)" stroke="url(#gold)" stroke-width="3"/><rect x="30" y="30" width="40" height="40" fill="#9b6426" stroke="#f5c67e"/>'
      + Array.from({ length: 9 }, (_, i) => { const n = 22 + i * 7; return `<path d="M${n} 9v11M${n} 80v11M9 ${n}h11M80 ${n}h11" stroke="url(#gold)" stroke-width="3"/>`; }).join('');
  }
  if (type === 'rings') {
    return [20, 45, 70].map((y) => `<path d="M15 ${y}v9c0 18 70 18 70 0v-9" fill="url(#face)" stroke="url(#gold)"/><ellipse cx="50" cy="${y}" rx="35" ry="12" fill="#a96d2944" stroke="url(#gold)" stroke-width="4"/>`).join('');
  }
  return '<path d="M50 4 91 27 86 73 50 96 13 73 9 27Z" fill="url(#face)" stroke="url(#gold)" stroke-width="2"/><path d="m50 4 0 92M9 27l41 23 41-23M13 73l37-23 36 23M50 4 13 73 91 27 50 96 9 27 86 73Z" fill="none" stroke="#ffd897" stroke-width="1.1" opacity=".8"/>';
}

export function emblem(type, style = null) {
  const svg = document.createElementNS(SVG, 'svg');
  svg.setAttribute('class', 'emblem');
  svg.setAttribute('viewBox', '0 0 100 100');
  svg.setAttribute('aria-hidden', 'true');
  if (style) svg.setAttribute('style', style);
  svg.innerHTML = `<circle cx="50" cy="50" r="46" fill="url(#glow)"/>${shapes(type)}`;
  return svg;
}
