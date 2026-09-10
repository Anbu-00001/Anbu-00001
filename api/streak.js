import { resolveStreak } from '../lib/streak.js';
import { buildSvg, formatCount } from '../lib/plague-render.js';

/**
 * "The Indifferent World" — live GitHub streak banner.
 *
 * GitHub serves README images through its Camo proxy, and Camo honours upstream
 * cache directives. The no-store headers below are what make it re-fetch on
 * every page view rather than pinning one frozen copy — without them the numbers
 * look static no matter how live the backend is.
 *
 * Serves `/api/streak` (SVG) and `/api/streak?debug=1` (JSON diagnostics).
 */
export default async function handler(req, res) {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const params = url.searchParams;

  const username = params.get('username') || 'Anbu-00001';
  const debug = params.get('debug') === '1';

  const result = await resolveStreak({ username });

  res.setHeader('Cache-Control', 'max-age=0, no-cache, no-store, must-revalidate');
  res.setHeader('Pragma', 'no-cache');
  res.setHeader('Expires', '0');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Access-Control-Allow-Origin', '*');

  if (debug) {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.statusCode = 200;
    res.end(JSON.stringify({
      ...result,
      formatted: { streak: formatCount(result.streak), commits: formatCount(result.commits) },
    }, null, 2));
    return;
  }

  res.setHeader('Content-Type', 'image/svg+xml; charset=utf-8');
  res.statusCode = 200;
  res.end(buildSvg(result.streak, result.commits));
}
