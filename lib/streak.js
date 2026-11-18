/**
 * Streak + contribution totals for "The Indifferent World" banner.
 *
 * Source is GitHub's own public contributions calendar, the same HTML fragment the
 * profile page loads (github.com/users/<name>/contributions). It needs no token
 * and has no middleman.
 *
 * This used to proxy streak-stats.vercel.app. That is someone else's free Vercel
 * deployment, and in Nov 2026 it was paused (503 DEPLOYMENT_PAUSED); the banner
 * then read "0 days, 0 deeds" on the profile. Reading GitHub directly removes the
 * dependency that failed. The semantics are kept the same as streak-stats:
 *   - streak: consecutive days with at least one contribution, ending today; a
 *     today with nothing yet does not break it, it ends at yesterday instead.
 *   - commits: all contributions ever, summed across every calendar year.
 *
 * Each day's count is in the cell's tooltip ("3 contributions on March 8th.",
 * "No contributions on ..."), linked to the cell by id.
 *
 * The defensive shape is copied from lib/counter.js on purpose: a timeout so a
 * slow upstream cannot hang the image, and a last-good cache so a failed fetch
 * shows a slightly stale number rather than a zero. On a profile README a
 * visible regression to 0 is far worse than staleness.
 */
const CALENDAR = 'https://github.com/users';
const FIRST_YEAR = 2008;                 // GitHub launched in 2008; nothing older exists
const PAST_YEAR_TTL_MS = 6 * 3600 * 1000;

let lastGood = null;
const yearCache = new Map();             // `${user}:${year}` -> { days, at }

async function withTimeout(run, ms) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    return await run(ctl.signal);
  } finally {
    clearTimeout(timer);
  }
}

/** Parses one calendar fragment into Map<'YYYY-MM-DD', count>. */
export function parseCalendar(html) {
  const tips = new Map();
  for (const m of html.matchAll(/<tool-tip\b[^>]*\bfor="([^"]+)"[^>]*>([^<]*)<\/tool-tip>/g)) {
    tips.set(m[1], m[2].trim());
  }

  const days = new Map();
  let unread = 0;
  for (const m of html.matchAll(/<td\b[^>]*\bdata-date="(\d{4}-\d{2}-\d{2})"[^>]*>/g)) {
    const id = /\bid="([^"]+)"/.exec(m[0])?.[1];
    const text = id && tips.get(id);
    if (!text) { unread++; continue; }
    const count = /^no\b/i.test(text) ? 0 : Number.parseInt(text.replace(/,/g, ''), 10);
    if (!Number.isFinite(count)) { unread++; continue; }
    days.set(m[1], count);
  }
  //  A markup change on GitHub's side would otherwise read as a quiet run of zeros.
  if (days.size === 0 || unread > days.size / 10) {
    throw new Error(`calendar markup not understood (${days.size} read, ${unread} unread)`);
  }
  return days;
}

async function fetchYear(username, year, signal, currentYear) {
  const key = `${username}:${year}`;
  const hit = yearCache.get(key);
  //  Past years barely change, so a warm instance reuses them; the current year is
  //  always fetched fresh because that is where the streak lives.
  if (hit && year < currentYear && Date.now() - hit.at < PAST_YEAR_TTL_MS) return hit.days;

  const url = `${CALENDAR}/${encodeURIComponent(username)}/contributions` +
              `?from=${year}-01-01&to=${year}-12-31`;
  const res = await fetch(url, {
    signal,
    headers: { 'user-agent': 'indifferent-world', accept: 'text/html' },
  });
  if (!res.ok) throw new Error(`github calendar ${year}: ${res.status}`);
  const days = parseCalendar(await res.text());
  yearCache.set(key, { days, at: Date.now() });
  return days;
}

const sumOf = (days) => { let n = 0; for (const c of days.values()) n += c; return n; };

function isoDay(date) { return date.toISOString().slice(0, 10); }
function shift(day, by) {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + by);
  return isoDay(d);
}

/** Current streak from a merged day map, with streak-stats' grace for today. */
export function currentStreak(days, now = new Date()) {
  const today = isoDay(now);
  const tomorrow = shift(today, 1);
  //  A contributor east of UTC can already have a dated "tomorrow"; count it.
  let day = (days.get(tomorrow) ?? 0) > 0 ? tomorrow : today;
  if (!((days.get(day) ?? 0) > 0)) day = shift(day, -1);
  let streak = 0;
  while ((days.get(day) ?? 0) > 0) { streak++; day = shift(day, -1); }
  return streak;
}

async function readGitHub(username, signal, now = new Date()) {
  const currentYear = Math.max(now.getUTCFullYear(), new Date(now.getTime() + 86400000).getUTCFullYear());

  //  Four years in one parallel round covers most accounts; keep walking back only
  //  while the oldest year fetched still had activity.
  const years = [];
  for (let y = currentYear; y > currentYear - 4 && y >= FIRST_YEAR; y--) years.push(y);
  const merged = new Map();
  const add = (days) => { for (const [d, c] of days) merged.set(d, c); };

  const first = await Promise.all(years.map((y) => fetchYear(username, y, signal, currentYear)));
  first.forEach(add);
  let oldest = years[years.length - 1];
  let oldestDays = first[first.length - 1];
  while (sumOf(oldestDays) > 0 && oldest > FIRST_YEAR) {
    oldest--;
    oldestDays = await fetchYear(username, oldest, signal, currentYear);
    add(oldestDays);
  }

  return { streak: currentStreak(merged, now), commits: sumOf(merged) };
}

/** Resolves { streak, commits }, falling back to the last good pair. */
export async function resolveStreak({ username = 'Anbu-00001', timeoutMs = 6000 } = {}) {
  try {
    const { streak, commits } = await withTimeout((signal) => readGitHub(username, signal), timeoutMs);
    lastGood = { streak, commits };
    return { ...lastGood, source: 'github-calendar', stale: false };
  } catch (err) {
    if (lastGood) {
      return { ...lastGood, source: 'stale-cache', stale: true, error: String(err.message || err) };
    }
    //  Nothing cached yet and GitHub is unreachable. Zeros would read as a broken
    //  streak, so the renderer leaves the numbers off and lets the art stand.
    return { streak: null, commits: null, source: 'unavailable', stale: true,
             error: String(err.message || err) };
  }
}
