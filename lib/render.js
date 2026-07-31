import { FRAMES } from './frames.js';

/**
 * Formats a raw view count the way the HUD expects: zero-padded to at least
 * six digits and comma-grouped, e.g. 2 -> "000,002", 4192 -> "004,192".
 */
export function formatCount(n) {
  const safe = Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
  return String(safe).padStart(6, '0').replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// Each frame owns a 10% slice of the 8s loop, cross-fading into the next.
const frameKeyframes = FRAMES.map((_, i) => {
  const start = i * 10;
  return `
      .pf-${i} { animation: animF${i} 8s ease-in-out infinite alternate; }
      @keyframes animF${i} {
        0%, ${start}% { opacity: 0; }
        ${start === 0 ? 0 : start + 2}%, ${start + 8}% { opacity: 1; }
        ${start + 10}%, 100% { opacity: 0; }
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

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 740 370" width="100%" height="370" shape-rendering="crispEdges">
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
