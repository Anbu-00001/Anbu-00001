/**
 * Streak + contribution totals for "The Indifferent World" banner.
 *
 * Source is github-readme-streak-stats in JSON mode — the same service the
 * README already trusted for its streak widget, so the numbers cannot disagree
 * with what was there before. It needs no token, which is the reason to prefer
 * it over GitHub's GraphQL contributions API here.
 *
 * The defensive shape is copied from lib/counter.js on purpose: a timeout so a
 * slow upstream cannot hang the image, and a last-good cache so a failed fetch
 * shows a slightly stale number rather than a zero. On a profile README a
 * visible regression to 0 is far worse than staleness.
 */
const ENDPOINT = 'https://streak-stats.vercel.app';

let lastGood = null;

async function withTimeout(run, ms) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    return await run(ctl.signal);
  } finally {
    clearTimeout(timer);
  }
}

/** Resolves { streak, commits }, falling back to the last good pair. */
export async function resolveStreak({ username = 'Anbu-00001', timeoutMs = 6000 } = {}) {
  try {
    const url = `${ENDPOINT}?user=${encodeURIComponent(username)}&type=json`;
    const res = await withTimeout(
      (signal) => fetch(url, { signal, headers: { 'user-agent': 'indifferent-world' } }),
      timeoutMs,
    );
    if (!res.ok) throw new Error(`upstream ${res.status}`);
    const j = await res.json();

    const streak = Number(j?.currentStreak?.length);
    const commits = Number(j?.totalContributions);
    if (!Number.isFinite(streak) || !Number.isFinite(commits)) {
      throw new Error('unexpected payload shape');
    }

    lastGood = { streak, commits };
    return { ...lastGood, source: 'streak-stats', stale: false };
  } catch (err) {
    if (lastGood) {
      return { ...lastGood, source: 'stale-cache', stale: true, error: String(err.message || err) };
    }
    //  Nothing cached yet and the upstream is down. Zeros would read as a broken
    //  streak, so send the banner with no numbers at all and let the art stand.
    return { streak: null, commits: null, source: 'unavailable', stale: true,
             error: String(err.message || err) };
  }
}
