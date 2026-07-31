#!/usr/bin/env node
/**
 * Local harness for the counter endpoint.
 *
 * Runs the exact handler Vercel invokes, so "it increments here" is evidence
 * about production rather than a parallel mock implementation.
 *
 *   node scripts/dev-server.js              # serve on :3000
 *   node scripts/dev-server.js --selftest   # assert the count advances per request
 *
 * The selftest stands up a throwaway server speaking the Upstash REST protocol
 * (GET /incr/<key> -> {"result":N}) and points the handler at it, so the real
 * KV code path is exercised without needing a live account.
 */
import http from 'node:http';
import handler from '../api/counter.js';

const PORT = Number(process.env.PORT) || 3000;

function makeServer() {
  return http.createServer(async (req, res) => {
    try {
      await handler(req, res);
    } catch (err) {
      res.statusCode = 500;
      res.setHeader('Content-Type', 'text/plain');
      res.end(`counter failed: ${err && err.stack ? err.stack : err}`);
    }
  });
}

function listen(server, port = 0) {
  return new Promise((resolve) => server.listen(port, () => resolve(server.address().port)));
}

async function selftest() {
  // Stand-in for Upstash/Vercel KV. Seeded above the live Komarev value so the
  // displayed max(kv, komarev) actually advances during the test instead of
  // sitting pinned to the Komarev floor.
  let stored = 1000;
  const kv = http.createServer((req, res) => {
    if (req.url.startsWith('/incr/')) {
      stored += 1;
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ result: stored }));
      return;
    }
    res.statusCode = 404;
    res.end('{}');
  });
  const kvPort = await listen(kv);
  process.env.KV_REST_API_URL = `http://127.0.0.1:${kvPort}`;
  process.env.KV_REST_API_TOKEN = 'selftest-token';

  const server = makeServer();
  const port = await listen(server);
  const base = `http://127.0.0.1:${port}`;
  const seen = [];
  const kvSeen = [];

  for (let i = 1; i <= 4; i++) {
    const res = await fetch(`${base}/api/counter?debug=1`);
    const b = await res.json();
    seen.push(b.count);
    kvSeen.push(b.kv);
    console.log(
      `request ${i}: count=${b.count} (${b.formatted})  kv=${b.kv} komarev=${b.komarev} ` +
      `source=${b.source} perView=${b.perViewCounting}` +
      (b.errors ? `  errors=${JSON.stringify(b.errors)}` : '')
    );
  }

  const svgRes = await fetch(`${base}/api/counter`);
  const svg = await svgRes.text();
  const frames = (svg.match(/<image /g) || []).length;

  // The count is drawn as bitmap <rect>s inside .inscription, not as a <text>
  // node, so verify the group exists and is populated rather than scraping a
  // string out of it.
  const group = svg.match(/<g class="inscription">([\s\S]*?)<\/g>/);
  const inkRects = group ? (group[1].match(/<rect /g) || []).length : 0;
  const shown = inkRects > 0;

  // Every rect must land inside the flat zone (x 83..173, y 50..78).
  const coords = group ? [...group[1].matchAll(/x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="(\d+)"/g)] : [];
  const outside = coords.filter(([, x, y, w, h]) =>
    +x < 83 || +x + +w > 173 || +y < 50 || +y + +h > 78).length;

  console.log(
    `\ncontent-type : ${svgRes.headers.get('content-type')}` +
    `\ncache-control: ${svgRes.headers.get('cache-control')}` +
    `\nsize         : ${(svg.length / 1024).toFixed(1)} KB, ${frames} animation frames` +
    `\ninscription  : ${inkRects} rects, ${outside} outside the 90x28 flat zone`
  );

  // The per-view proof is that KV advances on every single request. The
  // displayed count is max(kv, komarev), so early values legitimately sit on
  // the Komarev floor before KV overtakes it — assert non-decreasing there.
  const kvRising = kvSeen.every((v, i) => i === 0 || v > kvSeen[i - 1]);
  const shownMonotonic = seen.every((v, i) => i === 0 || v >= seen[i - 1]);
  const shownAdvanced = seen[seen.length - 1] > seen[0];
  const noStore = /no-store/.test(svgRes.headers.get('cache-control') || '');
  const ok = kvRising && shownMonotonic && shownAdvanced && frames === 10 &&
    shown && outside === 0 && noStore;

  console.log(
    ok
      ? `\nPASS: KV advanced ${kvSeen.join(' -> ')} (one per request); displayed ` +
        `${seen.join(' -> ')}; 10 frames intact; ${inkRects} inscription rects all ` +
        `inside the flat zone; no-store set.`
      : `\nFAIL: kvRising=${kvRising} (${kvSeen.join(', ')}) shown=${seen.join(', ')} ` +
        `monotonic=${shownMonotonic} advanced=${shownAdvanced} frames=${frames} ` +
        `inscription=${inkRects} outsideZone=${outside} noStore=${noStore}`
  );

  server.close();
  kv.close();
  process.exit(ok ? 0 : 1);
}

if (process.argv.includes('--selftest')) {
  selftest();
} else {
  const server = makeServer();
  server.listen(PORT, () => {
    console.log(`counter dev server: http://localhost:${PORT}/api/counter`);
    console.log(`diagnostics:        http://localhost:${PORT}/api/counter?debug=1`);
  });
}
