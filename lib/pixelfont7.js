/**
 * A 5x7 bitmap font rendered as SVG <rect>s.
 *
 * The 3x5 face in pixelfont.js is right for the moon banner's numerals, but at the
 * label sizes this banner needs it gives chunky, uneven capitals next to the
 * inscriptional Roman letters in the reference art. Seven rows is the smallest grid
 * that carries a real letterform: proper bowls on B/D/P/R, a diagonal K, a jointed
 * S, an M that is not just a filled block.
 *
 * At cell 1 these are 7px tall — the reference sets its labels at about 8px in the
 * same 512x256 space, so one art pixel per text pixel lands almost exactly on it.
 *
 * Same contract as pixelfont.js: '1' paints a cell, glyphs are variable width, and
 * one blank cell separates them.
 */
const G = {
  A: ['01110','10001','10001','11111','10001','10001','10001'],
  B: ['11110','10001','10001','11110','10001','10001','11110'],
  C: ['01110','10001','10000','10000','10000','10001','01110'],
  D: ['11110','10001','10001','10001','10001','10001','11110'],
  E: ['11111','10000','10000','11110','10000','10000','11111'],
  F: ['11111','10000','10000','11110','10000','10000','10000'],
  G: ['01110','10001','10000','10111','10001','10001','01110'],
  H: ['10001','10001','10001','11111','10001','10001','10001'],
  I: ['11111','00100','00100','00100','00100','00100','11111'],
  J: ['00111','00010','00010','00010','00010','10010','01100'],
  K: ['10001','10010','10100','11000','10100','10010','10001'],
  L: ['10000','10000','10000','10000','10000','10000','11111'],
  M: ['10001','11011','10101','10101','10001','10001','10001'],
  N: ['10001','11001','10101','10101','10011','10001','10001'],
  O: ['01110','10001','10001','10001','10001','10001','01110'],
  P: ['11110','10001','10001','11110','10000','10000','10000'],
  Q: ['01110','10001','10001','10001','10101','10010','01101'],
  R: ['11110','10001','10001','11110','10100','10010','10001'],
  S: ['01111','10000','10000','01110','00001','00001','11110'],
  T: ['11111','00100','00100','00100','00100','00100','00100'],
  U: ['10001','10001','10001','10001','10001','10001','01110'],
  V: ['10001','10001','10001','10001','10001','01010','00100'],
  W: ['10001','10001','10001','10101','10101','11011','10001'],
  X: ['10001','10001','01010','00100','01010','10001','10001'],
  Y: ['10001','10001','01010','00100','00100','00100','00100'],
  Z: ['11111','00001','00010','00100','01000','10000','11111'],
  '0': ['01110','10001','10011','10101','11001','10001','01110'],
  '1': ['00100','01100','00100','00100','00100','00100','01110'],
  '2': ['01110','10001','00001','00010','00100','01000','11111'],
  '3': ['11111','00010','00100','00010','00001','10001','01110'],
  '4': ['00010','00110','01010','10010','11111','00010','00010'],
  '5': ['11111','10000','11110','00001','00001','10001','01110'],
  '6': ['00110','01000','10000','11110','10001','10001','01110'],
  '7': ['11111','00001','00010','00100','01000','01000','01000'],
  '8': ['01110','10001','10001','01110','10001','10001','01110'],
  '9': ['01110','10001','10001','01111','00001','00010','01100'],
  ',': ['00','00','00','00','01','01','10'],
  '.': ['0','0','0','0','0','0','1'],
  ' ': ['00','00','00','00','00','00','00'],
};

/** Width in cells of `text` when rendered (including inter-glyph gaps). */
export function measure(text) {
  const glyphs = [...text.toUpperCase()].map((c) => G[c]).filter(Boolean);
  if (!glyphs.length) return { cells: 0, rows: 7 };
  return { cells: glyphs.reduce((n, g) => n + g[0].length, 0) + (glyphs.length - 1), rows: 7 };
}

/** Renders `text` as <rect>s, centred on `cx` with its top at `y`. */
export function pixelText(text, { cx, y, cell, fill }) {
  const chars = [...text.toUpperCase()].map((c) => G[c]).filter(Boolean);
  const { cells } = measure(text);
  let x = Math.round(cx - (cells * cell) / 2);
  const out = [];
  for (const g of chars) {
    for (let ry = 0; ry < g.length; ry++) {
      const row = g[ry];
      let rx = 0;
      while (rx < row.length) {
        if (row[rx] === '1') {
          let run = 1;
          while (rx + run < row.length && row[rx + run] === '1') run++;   // merge runs
          out.push(`<rect x="${x + rx * cell}" y="${y + ry * cell}" ` +
                   `width="${run * cell}" height="${cell}" fill="${fill}"/>`);
          rx += run;
        } else rx++;
      }
    }
    x += (g[0].length + 1) * cell;
  }
  return out.join('');
}
