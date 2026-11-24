import { resolveLangs } from '../lib/langs.js';

/**
 * Top-languages card for the profile README.
 *
 * `/api/langs` serves the SVG; `/api/langs?debug=1` reports which source answered.
 * Any other query parameters are passed through to github-readme-stats' top-langs
 * API unchanged, so the README keeps the same layout/theme options as before.
 */
const DEFAULTS = { username: 'Anbu-00001', layout: 'compact', theme: 'tokyonight', langs_count: '8' };

export default async function handler(req, res) {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const params = new URLSearchParams(DEFAULTS);
  for (const [k, v] of url.searchParams) if (k !== 'debug') params.set(k, v);
  const debug = url.searchParams.get('debug') === '1';

  const result = await resolveLangs(params.toString());

  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Access-Control-Allow-Origin', '*');
  //  Languages move slowly, so let Vercel's CDN hold a good card for 30 minutes
  //  and keep serving it while it refreshes. A fallback card is cached only
  //  briefly, so a recovered upstream shows up again soon.
  res.setHeader('Cache-Control', result.stale
    ? 'public, max-age=300, s-maxage=300'
    : 'public, max-age=1800, s-maxage=1800, stale-while-revalidate=86400');

  if (debug) {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    res.statusCode = 200;
    const { svg, ...rest } = result;
    res.end(JSON.stringify({ ...rest, bytes: svg.length }, null, 2));
    return;
  }

  res.setHeader('Content-Type', 'image/svg+xml; charset=utf-8');
  res.statusCode = 200;
  res.end(result.svg);
}
