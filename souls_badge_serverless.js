/**
 * Souls-Like Pixel View Counter - Serverless SVG Badge Endpoint
 * Suitable for Vercel Serverless Functions, Cloudflare Workers, or Deno Deploy.
 * 
 * Usage:
 *  - Deploy to Vercel (/api/counter.js) or Cloudflare Worker.
 *  - In GitHub README:
 *    ![Souls Observed](https://your-vercel-domain.vercel.app/api/counter?username=Anbu-00001)
 */

export default async function handler(req, res) {
  const { username = 'Anbu-00001' } = req.query || {};

  // 1. Fetch dynamic view count (From KV store, Redis, or fallback counter API)
  let viewCount = 4192; // Default baseline
  try {
    // Example: Fetch live count from KV or public counter proxy if available
    const kvFetch = await fetch(`https://komarev.com/ghpvc/?username=${username}&format=json`);
    if (kvFetch.ok) {
      const data = await kvFetch.json();
      if (data.value) viewCount = data.value;
    }
  } catch (err) {
    console.log('Using baseline view count:', err.message);
  }

  // Format count with leading zeros (e.g. 0 0 4 , 1 9 2)
  const countStr = String(viewCount).padStart(6, '0').replace(/\B(?=(\d{3})+(?!\d))/g, " , ");

  // 2. Render dynamic SVG badge
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 230" width="100%" height="230" shape-rendering="crispEdges">
  <defs>
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&amp;family=Cinzel:wght@700&amp;display=swap');
      .bg-sky { fill: #0d1b33; }
      .ember { animation: emberFloat 4.5s infinite linear; opacity: 0; }
      .e1 { animation-delay: 0.0s; }
      .e2 { animation-delay: 0.9s; }
      .e3 { animation-delay: 1.8s; }
      .e4 { animation-delay: 2.7s; }
      .e5 { animation-delay: 3.6s; }

      @keyframes emberFloat {
        0% { transform: translateY(0px) translateX(0px); opacity: 0; }
        20% { opacity: 1; }
        80% { opacity: 0.8; }
        100% { transform: translateY(-85px) translateX(18px); opacity: 0; }
      }
      .cloud-top-bank { animation: partTopClouds 7s ease-in-out infinite alternate; }
      .cloud-bottom-bank { animation: partBottomClouds 7s ease-in-out infinite alternate; }
      @keyframes partTopClouds {
        0% { transform: translateY(0px) translateX(0px); }
        100% { transform: translateY(-16px) translateX(-28px); }
      }
      @keyframes partBottomClouds {
        0% { transform: translateY(0px) translateX(0px); }
        100% { transform: translateY(14px) translateX(24px); }
      }
      .moon-pulse { animation: moonGlow 3.5s ease-in-out infinite alternate; transform-origin: 340px 90px; }
      @keyframes moonGlow {
        0% { transform: scale(0.96); opacity: 0.7; }
        100% { transform: scale(1.06); opacity: 1.0; }
      }
      .pixel-readout { font-family: 'Press Start 2P', monospace; font-size: 16px; fill: #f5eedc; letter-spacing: 4px; text-anchor: middle; dominant-baseline: middle; }
      .gothic-header { font-family: 'Cinzel', serif; font-weight: 700; font-size: 11px; letter-spacing: 5px; fill: #d4af37; text-anchor: middle; }
      .runic-sub { font-family: 'Press Start 2P', monospace; font-size: 7px; fill: #4c83b6; letter-spacing: 2px; text-anchor: middle; }
    </style>
    <radialGradient id="crimsonAura" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ff1d70" stop-opacity="0.9"/>
      <stop offset="40%" stop-color="#b8004b" stop-opacity="0.5"/>
      <stop offset="100%" stop-color="#0d1b33" stop-opacity="0"/>
    </radialGradient>
    <pattern id="skyDither" width="4" height="4" patternUnits="userSpaceOnUse">
      <rect x="0" y="0" width="2" height="2" fill="#132747"/>
      <rect x="2" y="2" width="2" height="2" fill="#132747"/>
    </pattern>
  </defs>

  <rect class="bg-sky" width="680" height="230"/>
  <rect x="0" y="40" width="680" height="150" fill="url(#skyDither)" opacity="0.45"/>

  <g fill="#89ccf7" opacity="0.7">
    <rect x="35" y="20" width="3" height="3"/>
    <rect x="110" y="35" width="2" height="2"/>
    <rect x="190" y="15" width="3" height="3"/>
    <rect x="490" y="25" width="2" height="2"/>
    <rect x="580" y="40" width="3" height="3"/>
  </g>

  <g>
    <circle class="moon-pulse" cx="340" cy="90" r="80" fill="url(#crimsonAura)"/>
    <g transform="translate(302, 52)">
      <rect x="16" y="0" width="44" height="76" fill="#ff1d70"/>
      <rect x="8" y="8" width="60" height="60" fill="#ff1d70"/>
      <rect x="0" y="16" width="76" height="44" fill="#ff1d70"/>
      <g fill="#b8004b">
        <rect x="12" y="12" width="16" height="12"/>
        <rect x="44" y="24" width="20" height="8"/>
        <rect x="0" y="20" width="76" height="6"/>
        <rect x="0" y="38" width="76" height="8"/>
        <rect x="0" y="56" width="76" height="5"/>
      </g>
    </g>
  </g>

  <g class="cloud-top-bank">
    <g fill="#1a3b68">
      <rect x="0" y="0" width="290" height="75"/>
      <rect x="25" y="75" width="230" height="25"/>
    </g>
    <g fill="#2d6bb3">
      <rect x="0" y="0" width="260" height="55"/>
      <rect x="40" y="55" width="190" height="25"/>
    </g>
    <g fill="#4faae6">
      <rect x="0" y="0" width="220" height="35"/>
    </g>
    <g fill="#1a3b68">
      <rect x="400" y="0" width="280" height="75"/>
      <rect x="430" y="75" width="220" height="25"/>
    </g>
    <g fill="#2d6bb3">
      <rect x="420" y="0" width="260" height="55"/>
    </g>
  </g>

  <g class="cloud-bottom-bank">
    <g fill="#132747">
      <rect x="0" y="135" width="270" height="95"/>
    </g>
    <g fill="#1a3b68">
      <rect x="0" y="150" width="240" height="80"/>
    </g>
    <g fill="#2d6bb3">
      <rect x="0" y="170" width="200" height="60"/>
    </g>
    <g fill="#132747">
      <rect x="410" y="140" width="270" height="90"/>
    </g>
    <g fill="#1a3b68">
      <rect x="430" y="155" width="250" height="75"/>
    </g>
  </g>

  <g>
    <rect class="ember e1" x="320" y="155" width="3" height="3" fill="#ff1d70"/>
    <rect class="ember e2" x="350" y="165" width="2" height="2" fill="#ff6699"/>
    <rect class="ember e3" x="300" y="145" width="3" height="3" fill="#ff1d70"/>
    <rect class="ember e4" x="365" y="160" width="2" height="2" fill="#ffd166"/>
  </g>

  <g transform="translate(155, 145)">
    <rect x="0" y="0" width="370" height="70" fill="#090e17" rx="4"/>
    <rect x="3" y="3" width="364" height="64" fill="#131c2b" stroke="#3d2f1c" stroke-width="2"/>
    <rect x="7" y="7" width="356" height="56" fill="#090d14"/>

    <path d="M 7,17 L 7,7 L 17,7" stroke="#d4af37" stroke-width="2" fill="none"/>
    <path d="M 353,17 L 353,7 L 343,7" stroke="#d4af37" stroke-width="2" fill="none"/>

    <text class="gothic-header" x="185" y="24">✦ SOULS OBSERVED ✦</text>

    <rect x="50" y="32" width="270" height="25" fill="#1f090e" stroke="#8a051d" stroke-width="1.5"/>

    <text class="pixel-readout" x="187" y="46" fill="#4d000c">${countStr}</text>
    <text class="pixel-readout" x="185" y="45">${countStr}</text>
  </g>

  <text class="runic-sub" x="340" y="224">ᚠ ᛁ ᚱ ᛖ ᛫ ᚴ ᛖ ᛖ ᛈ ᛖ ᛱ ᛫ ᚨ ᚢ ᚱ ᚨ</text>
</svg>`;

  if (res) {
    res.setHeader('Content-Type', 'image/svg+xml');
    res.setHeader('Cache-Control', 'max-age=0, no-cache, no-store, must-revalidate');
    res.status(200).send(svg);
  }
  return svg;
}
