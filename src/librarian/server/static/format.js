const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAY_MS = 86400000;

const pad = (n) => String(n).padStart(2, '0');

/** "Nov 18" */
export const shortDate = (d) => `${MONTHS[d.getMonth()]} ${d.getDate()}`;

/** "Tue 3 Nov" */
export const dateLine = (d) => `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;

/** "09:12" */
export const clock = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;

/** "00:09:14", for a position in a recording given in seconds */
export const position = (seconds) => {
  const s = Math.floor(seconds);
  return [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60].map(pad).join(':');
};

export const isToday = (d) => d.toDateString() === new Date().toDateString();

/** Whole local days from `d` to today: 0 is today, 1 yesterday. */
export const daysAgo = (d) => Math.round((new Date().setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / DAY_MS);

/** "Today", "Yesterday", "5 days ago", then the date itself once it is more than a month old. */
export function ago(d) {
  const days = daysAgo(d);
  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  return days <= 30 ? `${days} days ago` : shortDate(d);
}

/** "2023-11-14", the local day `days` before today, as the `since` filter wants it. */
export function dayBefore(days) {
  const d = new Date(Date.now() - days * DAY_MS);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Import times arrive as local time without a zone ("2026-11-06 09:12:03"), which `Date` reads as local. */
export const parseLocal = (text) => new Date(text.replace(' ', 'T'));
