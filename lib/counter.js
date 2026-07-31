/**
 * View-count resolution for the Crimson Moon counter.
 *
 * Why this does not simply proxy Komarev and call it dynamic
 * ----------------------------------------------------------
 * Komarev de-duplicates by the *socket* IP of whoever requests the badge and
 * ignores X-Forwarded-For (verified: three requests carrying three different
 * XFF values all returned the same number). So a serverless function polling
 * Komarev always looks like one single visitor.
 *
 * Komarev's number only moves when GitHub's Camo image proxy fetches its URL
 * on behalf of a real page view. That is why the count froze at 2 here: the
 * Komarev <img> was deleted from the README, so nothing was driving it. The
 * README re-adds it as an invisible 1x1 pixel — no visible badge, but the
 * counting resumes and this endpoint reads the result.
 *
 * Layering:
 *   - KV (Upstash/Vercel KV), if configured: a genuine per-request INCR, so the
 *     number advances on literally every view. Optional; needs two env vars.
 *   - Komarev: always read, needs no setup, and acts as a floor so the number
 *     never regresses below the historical profile-view total.
 */

// Read lazily rather than at module load so the config is testable and so a
// late-bound platform env still applies.
const kvConfig = () => ({
  url: process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL || '',
  token: process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN || '',
  key: process.env.COUNTER_KEY || 'anbu:profile-views',
});

async function withTimeout(run, ms) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    return await run(ctl.signal);
  } finally {
    clearTimeout(timer);
  }
}

/** Atomically increments the KV counter and returns the new value. */
async function bumpKv() {
  const { url: base, token, key } = kvConfig();
  if (!base || !token) throw new Error('kv not configured');
  const url = `${base.replace(/\/$/, '')}/incr/${encodeURIComponent(key)}`;
  const res = await withTimeout(
    (signal) => fetch(url, { signal, headers: { Authorization: `Bearer ${token}` } }),
    2500
  );
  if (!res.ok) throw new Error(`kv ${res.status}`);
  const data = await res.json();
  const n = Number(data && data.result);
  if (!Number.isFinite(n)) throw new Error('kv: no result field');
  return n;
}

/** Reads Komarev's current number without ever showing its badge. */
async function readKomarev(username) {
  const url = `https://komarev.com/ghpvc/?username=${encodeURIComponent(username)}`;
  const res = await withTimeout(
    (signal) => fetch(url, { signal, headers: { 'user-agent': 'souls-counter' } }),
    4000
  );
  if (!res.ok) throw new Error(`komarev ${res.status}`);
  const svg = await res.text();
  // The count is the last <text> node in the badge; the label precedes it.
  const texts = svg.match(/<text[^>]*>([\d,]+)<\/text>/gi);
  if (!texts || texts.length === 0) throw new Error('komarev: no count node');
  const raw = texts[texts.length - 1].replace(/<[^>]+>/g, '').replace(/,/g, '');
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n)) throw new Error('komarev: unparseable count');
  return n;
}

// Last known-good count, kept in module scope. A serverless instance stays
// warm across bursts of nearby requests, so this survives exactly the
// scenario that matters: a traffic spike making the upstream services slow
// or briefly unreachable. Cold starts reset it to 0, which is harmless — the
// very next successful resolve repopulates it before any request needs it.
let lastGoodCount = 0;

/**
 * Resolves the number to display. Never throws — a counter that 500s shows
 * GitHub a broken image, which is worse than a slightly stale number. If
 * both upstreams fail at once, this holds the last successful count instead
 * of collapsing to 0 — a visible regression is worse than staleness.
 */
export async function resolveCount({
  username = 'Anbu-00001',
  offset = Number.parseInt(process.env.COUNTER_OFFSET || '0', 10) || 0,
} = {}) {
  const [kv, komarev] = await Promise.allSettled([bumpKv(), readKomarev(username)]);

  const kvVal = kv.status === 'fulfilled' ? kv.value : null;
  const komarevVal = komarev.status === 'fulfilled' ? komarev.value : null;

  const sources = [];
  if (kvVal !== null) sources.push('kv');
  if (komarevVal !== null) sources.push('komarev');

  const errors = {};
  const reason = (r) => String((r && r.message) || r);
  if (kv.status === 'rejected') errors.kv = reason(kv.reason);
  if (komarev.status === 'rejected') errors.komarev = reason(komarev.reason);

  const stale = sources.length === 0;
  const count = stale
    ? lastGoodCount + offset
    : Math.max(kvVal ?? 0, komarevVal ?? 0) + offset;

  if (!stale) lastGoodCount = Math.max(lastGoodCount, kvVal ?? 0, komarevVal ?? 0);

  return {
    count,
    kv: kvVal,
    komarev: komarevVal,
    source: stale ? 'stale-cache' : sources.join('+'),
    perViewCounting: kvVal !== null,
    stale,
    ...(Object.keys(errors).length ? { errors } : {}),
  };
}
