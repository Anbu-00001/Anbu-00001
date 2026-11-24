/**
 * Top-languages card, served from this project instead of linked straight from a
 * public github-readme-stats deployment.
 *
 * Why: those public deployments are other people's free Vercel projects running
 * on other people's GitHub tokens. In Nov 2026 three of them failed in three ways
 * (eight-theta: 402 DEPLOYMENT_DISABLED; sigma-five: 200 with a "Something went
 * wrong / Maximum retries exceeded" card; the official one: 503 for a while), and
 * each failure showed on the profile as a broken image or an error card, held for
 * up to two hours by their cache header.
 *
 * So this tries each upstream in order, accepts only a real languages card, keeps
 * the last good one in memory, and finally falls back to a snapshot bundled with
 * the deployment. It never returns an error card.
 */
import { SNAPSHOT } from './langs-snapshot.js';

const UPSTREAMS = [
  'https://github-readme-stats.vercel.app',
  'https://github-readme-stats-one-bice.vercel.app',
];

let lastGood = null;   // { svg, from, at }

/** A real card lists languages; an error card carries a message node instead. */
export function isGoodCard(svg) {
  return typeof svg === 'string' && svg.includes('<svg') &&
    svg.includes('data-testid="lang-name"') &&
    !svg.includes('data-testid="message"') && !/something went wrong/i.test(svg);
}

async function fetchCard(base, query, timeoutMs) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(`${base}/api/top-langs/?${query}`, {
      signal: ctl.signal, headers: { 'user-agent': 'souls-langs' },
    });
    if (!res.ok) throw new Error(`${res.status}`);
    const svg = await res.text();
    if (!isGoodCard(svg)) throw new Error('error card');
    return svg;
  } finally {
    clearTimeout(timer);
  }
}

/** Resolves { svg, source, stale, errors? }. Never throws. */
export async function resolveLangs(query, { timeoutMs = 5000 } = {}) {
  const errors = {};
  for (const base of UPSTREAMS) {
    try {
      const svg = await fetchCard(base, query, timeoutMs);
      lastGood = { svg, from: base, at: Date.now() };
      return { svg, source: base, stale: false };
    } catch (err) {
      errors[base] = String(err.message || err);
    }
  }
  if (lastGood) return { svg: lastGood.svg, source: 'memory', stale: true, errors };
  return { svg: SNAPSHOT, source: 'snapshot', stale: true, errors };
}
