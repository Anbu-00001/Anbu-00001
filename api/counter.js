import { resolveCount } from '../lib/counter.js';
import { buildSvg, formatCount } from '../lib/render.js';

/**
 * Live Crimson Moon view counter.
 *
 * GitHub serves README images through its Camo proxy. Camo honours upstream
 * cache directives, so the no-store headers below are what make it re-fetch on
 * every page view instead of pinning one frozen copy — the same technique
 * Komarev itself uses. Without them the counter looks static no matter how
 * dynamic the backend is.
 *
 * Serves `/api/counter` (SVG) and `/api/counter?debug=1` (JSON diagnostics).
 * Uses only setHeader/statusCode/end so the identical code path runs both on
 * Vercel and under the plain-Node dev server.
 */
export default async function handler(req, res) {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const params = url.searchParams;

  const username = params.get('username') || 'Anbu-00001';
  const offset = Number.parseInt(params.get('offset') || '0', 10) || 0;
  const debug = params.get('debug') === '1';

  const result = await resolveCount({ username, offset });

  res.setHeader('Cache-Control', 'max-age=0, no-cache, no-store, must-revalidate');
  res.setHeader('Pragma', 'no-cache');
  res.setHeader('Expires', '0');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  // The GitHub Pages demo reads the JSON form cross-origin.
  res.setHeader('Access-Control-Allow-Origin', '*');

  if (debug) {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.statusCode = 200;
    res.end(JSON.stringify({ ...result, formatted: formatCount(result.count) }, null, 2));
    return;
  }

  res.setHeader('Content-Type', 'image/svg+xml; charset=utf-8');
  res.statusCode = 200;
  res.end(buildSvg(result.count));
}
