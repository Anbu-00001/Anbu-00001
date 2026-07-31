#!/usr/bin/env node
/**
 * Regenerates souls_view_counter.svg from the live count.
 *
 * This file is only a fallback/preview — a committed SVG cannot change per
 * view, which is exactly why the README points at /api/counter instead.
 */
import fs from 'node:fs';
import { buildSvg } from '../lib/render.js';
import { resolveCount } from '../lib/counter.js';

const r = await resolveCount({});
const stamp = new Date().toISOString().slice(0, 10);
const note =
  `<!-- Static snapshot generated ${stamp} (count=${r.count}, source=${r.source}).\n` +
  `     A committed file cannot change per view - the README uses the live endpoint\n` +
  `     at /api/counter instead. Regenerate with: npm run snapshot -->\n`;

fs.writeFileSync(new URL('../souls_view_counter.svg', import.meta.url), note + buildSvg(r.count));
console.log(`souls_view_counter.svg regenerated: count=${r.count} source=${r.source}`);
