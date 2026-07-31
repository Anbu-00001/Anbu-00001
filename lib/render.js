import { FRAMES } from './frames.js';

/**
 * Formats a raw view count the way the HUD expects: zero-padded to at least
 * six digits and comma-grouped, e.g. 2 -> "000,002", 4192 -> "004,192".
 */
export function formatCount(n) {
  const safe = Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
  return String(safe).padStart(6, '0').replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// One-shot cumulative reveal.
//
// The previous version faded each frame OUT before the next faded IN, so for a
// moment mid-transition no layer was fully opaque and the page background
// showed through — that was the black flash between frames. Here every frame
// fades in on top of the stack and then stays opaque forever, so the canvas is
// covered at all times. `forwards` with a single iteration means it plays once
// and holds the fully-revealed moon instead of looping back.
const REVEAL_SECONDS = 6;
const STEPS = FRAMES.length - 1;   // 9 transitions across 10 frames
const STEP = 100 / STEPS;
const FADE = 0.45;                 // fraction of each step spent cross-fading

const frameKeyframes = FRAMES.map((_, i) => {
  if (i === 0) {
    // Base plate: opaque from first paint so nothing ever shows through.
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
  `  <image id="pf${i}" class="piskel-frame pf-${i}" x="0" y="0" width="740" height="370" ` +
  `href="data:image/png;base64,${data}" preserveAspectRatio="none" image-rendering="pixelated"/>`
).join('\n');

/**
 * Builds the full Crimson Moon counter SVG with `count` burned into the HUD.
 *
 * Note: GitHub renders README SVGs inside an <img>, which blocks external
 * resources — the Google Fonts @import will not load there, so the font stacks
 * below carry real local fallbacks rather than relying on the webfont.
 */
export function buildSvg(count) {
  const formatted = formatCount(count);

  // Concrete width/height give the file a 2:1 intrinsic aspect ratio, so an
  // <img width="100%"> in the README scales edge-to-edge and derives its own
  // height. With width="100%" here the intrinsic size is ambiguous and GitHub
  // letterboxes it instead.
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 740 370" width="740" height="370" shape-rendering="crispEdges">
  <defs>
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&amp;family=Cinzel:wght@700&amp;display=swap');
${frameKeyframes}

      .pixel-count-small {
        font-family: 'Press Start 2P', 'Courier New', monospace;
        font-size: 11px;
        fill: #f5eedc;
        letter-spacing: 2px;
        dominant-baseline: middle;
      }
      .gothic-header-small {
        font-family: 'Cinzel', Georgia, serif;
        font-weight: 700;
        font-size: 8px;
        letter-spacing: 2.5px;
        fill: #d4af37;
      }
    </style>
  </defs>

  <!-- PISKEL 10-FRAME PIXEL ART ANIMATION -->
  <g>
${frameImages}
  </g>

  <!-- COMPACT HUD BANNER STUCK TO TOP-LEFT CORNER -->
  <g transform="translate(16, 16)">
    <rect x="0" y="0" width="195" height="46" fill="#08101d" rx="3" opacity="0.95"/>
    <rect x="2" y="2" width="191" height="42" fill="#121e30" stroke="#3d2f1c" stroke-width="1.5"/>
    <rect x="5" y="5" width="185" height="36" fill="#080c14"/>

    <path d="M 5,12 L 5,5 L 12,5" stroke="#d4af37" stroke-width="1.5" fill="none"/>
    <path d="M 190,12 L 190,5 L 183,5" stroke="#d4af37" stroke-width="1.5" fill="none"/>
    <path d="M 5,34 L 5,41 L 12,41" stroke="#d4af37" stroke-width="1.5" fill="none"/>
    <path d="M 190,34 L 190,41 L 183,41" stroke="#d4af37" stroke-width="1.5" fill="none"/>

    <text class="gothic-header-small" x="12" y="17">&#10022; VISIONS WITNESSED &#10022;</text>

    <rect x="12" y="22" width="171" height="15" fill="#1a080c" stroke="#8a051d" stroke-width="1"/>

    <text class="pixel-count-small" x="21" y="32" fill="#4d000c">${formatted}</text>
    <text class="pixel-count-small" x="20" y="31">${formatted}</text>
  </g>
</svg>`;
}
