const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const pad = (n) => String(n).padStart(2, '0');

/** "Nov 18" */
export const shortDate = (d) => `${MONTHS[d.getMonth()]} ${d.getDate()}`;

/** "Tue 3 Nov" */
export const dateLine = (d) => `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;

/** "09:12" */
export const clock = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;

export const isToday = (d) => d.toDateString() === new Date().toDateString();

/** Import times arrive as local time without a zone ("2026-11-06 09:12:03"), which `Date` reads as local. */
export const parseLocal = (text) => new Date(text.replace(' ', 'T'));
