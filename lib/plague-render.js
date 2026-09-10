import { ART_W, ART_H, LAYERS } from './plague-frames.js';
import { measure, pixelText } from './pixelfont7.js';

// "The Indifferent World" — 15-frame streak banner, native 512x256.
//
// Why 512x256 when the moon banner is 256x128: this art is a graded render, not
// flat pixel art. Measured, the sill carving stops being legible below 512 wide.

// Per-frame hold times, straight off the exposure sheet in sequence.json.
const HOLDS = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5];        // six frames, a 3.0s cycle
const CYCLE = Math.round(HOLDS.reduce((a, b) => a + b, 0) * 100) / 100;   // 6.1s

// The whole sequence loops, as one cumulative pass.
//
// It used to reveal once with `forwards` and hold. That was wrong twice over: the
// reveal finished in 4.3s, and a 1MB SVG decodes its images asynchronously, so the
// transition was routinely over before anything was on screen — you opened it and
// got a static end frame. Thematically it was wrong too: the piece argues that none
// of this resolves, so holding on the last frame was the one ending it should not
// have had.
//
// Within a cycle layers only ever switch ON, in order. At the wrap they all reset
// together, and frame 0 — permanently opaque underneath — keeps the canvas covered
// through the reset, so there is no black flash.

// The reserved sky zone, kept deliberately calm in every frame so the readout never
// crawls. Measured at luminance std ~9 across the sequence.
//  y=31, not centred. Scanned every offset against the darkest cloud band each line
//  actually sits on across all six frames: 31 gives a worst line of 1.93:1, which
//  beats reference.png's own baked readout at 1.82:1. Centring gave 1.53:1.
const ZONE = { x: 278, y: 31, w: 101, h: 72 };
const SCALE = ART_W / 512;                            // readout geometry is authored at 512x256
const ZONE_CX = Math.round((ZONE.x + ZONE.w / 2) * SCALE);

// The reference's ink, deepened.
//
// reference.png sets rgb(26,12,27) — luma 16. Measured against the darkest cloud
// band the readout ever sits on (22.5), that is a contrast of 8.3, which is exactly
// the "submerged" look. It works in the reference because those capitals are large
// and smoothly antialiased; ours are 7px with hard edges and need more separation.
//
// So: same plum-black hue family, taken deeper. Contrast 18.7 instead of 8.3.
const INK = '#0C0510';          // numerals
const INK_LABEL = '#14091C';    // labels sit back a touch

const L_STREAK = process.env.STREAK_LABEL || 'DAYS UNBROKEN';
const L_COMMITS_1 = 'GIT DEEDS';
const L_COMMITS_2 = 'COMMITTED';

export function formatCount(n) {
  const safe = Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
  return String(safe).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** Largest integer cell size at which `text` still fits `maxWidth` cells. */
function fitCell(text, maxWidth, preferred) {
  const { cells } = measure(text);
  for (let c = preferred; c >= 1; c--) if (cells * c <= maxWidth) return c;
  return 1;
}

// Hard switches, not cross-fades. The moon dissolves because it is a reveal of one
// growing shape; this is an animation where the world moves between frames, so a
// dissolve would double-expose the trees and the birds.
function frameCss() {
  let css = '';
  let t = 0;
  for (let i = 0; i < LAYERS.length; i++) {
    if (!LAYERS[i]) continue;
    if (i === 0) { css += `\n      .pl-0 { opacity: 1; }`; t += HOLDS[0]; continue; }
    //  Distinct stops, exactly as the moon banner writes them. Two keyframe blocks
    //  sharing one percentage is legal but leaves the switch ambiguous; a short
    //  ramp is what the working banner does and it costs nothing here.
    const on = (t / CYCLE) * 100;
    const done = Math.min(100, on + 1.2);
    css += `
      .pl-${i} { opacity: 0; animation: plF${i} ${CYCLE}s linear infinite; }
      @keyframes plF${i} {
        0%, ${on.toFixed(2)}% { opacity: 0; }
        ${done.toFixed(2)}%, 100% { opacity: 1; }
      }`;
    t += HOLDS[i];
  }
  return css;
}

// Up in every frame. There is no forest any more — all six frames are the lit
// valley, so the sky behind the readout is bright throughout, which is the
// condition the reference's ink was drawn for.
const readoutCss = `
      .pl-readout { opacity: 0; animation: plInscribe ${CYCLE}s ease-out infinite; }
      @keyframes plInscribe { 0%, 100% { opacity: 1; } }`;

const images = LAYERS.map((l, i) => l &&
  `  <image class="pl-${i}" x="${l.x}" y="${l.y}" width="${l.w}" height="${l.h}" ` +
  `href="data:image/png;base64,${l.data}" preserveAspectRatio="none" image-rendering="pixelated"/>`
).filter(Boolean).join('\n');

/** Builds the streak banner SVG. */
export function buildSvg(streak, commits) {
  const s = formatCount(streak);
  const c = formatCount(commits);

  const zw = Math.round(ZONE.w * SCALE);
  const labelCell = Math.min(
    fitCell(L_STREAK, zw, Math.round(1 * SCALE)),
    fitCell(L_COMMITS_1, zw, Math.round(1 * SCALE)),
    fitCell(L_COMMITS_2, zw, Math.round(1 * SCALE)));
  const numCell = Math.min(fitCell(s, zw, Math.round(3 * SCALE)),
                           fitCell(c, zw, Math.round(3 * SCALE)));

  const labelH = 7 * labelCell;
  const numH = 7 * numCell;
  const inner = Math.round(2 * SCALE);
  const lead = Math.max(1, Math.round(1 * SCALE));
  const between = Math.round(4 * SCALE);

  const blockA = labelH + inner + numH;
  const blockB = labelH + lead + labelH + inner + numH;
  const top = Math.round(ZONE.y * SCALE);
  const bTop = top + blockA + between;
  const at = (text, y, cell, fill) => pixelText(text, { cx: ZONE_CX, y, cell, fill });

  const parts = [
    at(L_STREAK, top, labelCell, INK_LABEL),
    at(s, top + labelH + inner, numCell, INK),
    at(L_COMMITS_1, bTop, labelCell, INK_LABEL),
    at(L_COMMITS_2, bTop + labelH + lead, labelCell, INK_LABEL),
    at(c, bTop + labelH + lead + labelH + inner, numCell, INK),
  ];

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${ART_W} ${ART_H}" width="1024" height="512" shape-rendering="crispEdges">
  <defs>
    <style>${frameCss()}
${readoutCss}
    </style>
  </defs>

  <!-- 15 frames, looping: it does not resolve -->
  <g>
${images}
  </g>

  <!-- Readout, cut into the glass -->
  <g class="pl-readout">
${parts.join('\n')}
  </g>
</svg>`;
}
