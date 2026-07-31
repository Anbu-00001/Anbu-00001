import { FRAMES } from './frames.js';
import { measure, pixelText } from './pixelfont.js';

// Native art size. The viewBox uses these units directly so every text pixel
// lands exactly on the artwork's own grid — that is what keeps the inscription
// looking drawn-in rather than overlaid.
const ART_W = 256;
const ART_H = 128;

// Flat inscription zone reserved in the art: 90x28 centred on the disc.
// Verified against frame10 — frames 08-10 are a single solid #D42350 here.
const ZONE = { cx: 128, cy: 64, w: 90, h: 28 };

const CAPTION = process.env.COUNTER_CAPTION || 'BEHELD BY WANDERERS';

// Eclipse colourway: the numerals read as scorched into the disc. Both tones
// are drawn from the artwork's own 18-colour palette, so the composite image
// never introduces a colour the pixel art doesn't already contain.
const INK = '#2E0A1A';
const INK_CAPTION = '#4E0F27';

/**
 * Formats a raw view count: zero-padded to at least six digits and
 * comma-grouped, e.g. 2 -> "000,002", 4192 -> "004,192".
 */
export function formatCount(n) {
  const safe = Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
  return String(safe).padStart(6, '0').replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * Largest integer cell size at which `text` still fits `maxCells` wide.
 * Integer-only so text pixels stay aligned to the art grid; without this a
 * count past 999,999 gains a second comma and overflows the zone.
 *
 * TODO(easter-egg): past 1,000,000 this quietly shrinks to cell=2. That
 * milestone deserves something better than smaller text — hook a special
 * treatment in here when the time comes.
 */
function fitCell(text, maxWidth, preferred) {
  const { cells } = measure(text);
  for (let c = preferred; c >= 1; c--) {
    if (cells * c <= maxWidth) return c;
  }
  return 1;
}

// One-shot cumulative reveal.
//
// The original faded each frame OUT before the next faded IN, so mid-transition
// no layer was fully opaque and the page background showed through — that was
// the black flash. Here each frame fades in on top of the stack and stays
// opaque, so the canvas is always covered. `forwards` with a single iteration
// plays it once and holds the revealed moon.
const REVEAL_SECONDS = 6;
const STEPS = FRAMES.length - 1;
const STEP = 100 / STEPS;
const FADE = 0.45;

const frameKeyframes = FRAMES.map((_, i) => {
  if (i === 0) {
    return `
      .pf-0 { opacity: 1; }`;
  }
  const start = (i - 1) * STEP;
  const done = start + STEP * FADE;
  return `
      .pf-${i} { opacity: 0; animation: animF${i} ${REVEAL_SECONDS}s linear forwards; }
      @keyframes animF${i} {
        0%, ${start.toFixed(2)}% { opacity: 0; }
        ${done.toFixed(2)}%, 100% { opacity: 1; }
      }`;
}).join('');

const frameImages = FRAMES.map((data, i) =>
  `  <image class="pf-${i}" x="0" y="0" width="${ART_W}" height="${ART_H}" ` +
  `href="data:image/png;base64,${data}" preserveAspectRatio="none" image-rendering="pixelated"/>`
).join('\n');

// The inscription only appears once the disc is wide open. Frames 04-06 still
// carry banding inside the zone, so the fade starts at 70% (~frame 7) rather
// than earlier, and completes while frames 09-10 hold — where the zone is a
// single flat colour.
const inscriptionCss = `
      .inscription { opacity: 0; animation: inscribe ${REVEAL_SECONDS}s ease-out forwards; }
      @keyframes inscribe {
        0%, 70% { opacity: 0; }
        92%, 100% { opacity: 1; }
      }`;

/** Builds the full banner SVG with `count` inscribed on the moon. */
export function buildSvg(count) {
  const formatted = formatCount(count);

  const numCell = fitCell(formatted, ZONE.w, 3);
  const capCell = fitCell(CAPTION, ZONE.w, 1);

  const capH = 5 * capCell;
  const numH = 5 * numCell;
  const gap = 3;
  const blockH = capH + gap + numH;

  const top = ZONE.cy - blockH / 2;
  const capY = Math.round(top);
  const numY = Math.round(top + capH + gap);

  const caption = pixelText(CAPTION, { cx: ZONE.cx, y: capY, cell: capCell, fill: INK_CAPTION });
  const numerals = pixelText(formatted, { cx: ZONE.cx, y: numY, cell: numCell, fill: INK });

  // Concrete width/height give a 2:1 intrinsic ratio so an <img width="100%">
  // in the README scales edge-to-edge and derives its own height.
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${ART_W} ${ART_H}" width="1024" height="512" shape-rendering="crispEdges">
  <defs>
    <style>${frameKeyframes}
${inscriptionCss}
    </style>
  </defs>

  <!-- 10-frame Crimson Moon reveal, native 256x128 -->
  <g>
${frameImages}
  </g>

  <!-- Count inscribed on the moon's flat zone -->
  <g class="inscription">
${caption}
${numerals}
  </g>
</svg>`;
}
