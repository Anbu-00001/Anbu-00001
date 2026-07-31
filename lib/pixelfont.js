/**
 * A 3x5 bitmap font rendered as SVG <rect>s.
 *
 * Why not a webfont: GitHub renders README images inside an <img>, which blocks
 * every external resource — the old `Press Start 2P` @import never actually
 * loaded there and silently fell back to generic monospace. Drawing glyphs as
 * rectangles removes the dependency entirely and lands each text pixel exactly
 * on the artwork's own pixel grid.
 *
 * Glyphs are variable width: most are 3 cells, M/W are 5 so they stay legible,
 * and the comma is 2. A '1' in a row string paints a cell.
 */
const G = {
  '0': ['111', '101', '101', '101', '111'],
  '1': ['010', '110', '010', '010', '111'],
  '2': ['111', '001', '111', '100', '111'],
  '3': ['111', '001', '111', '001', '111'],
  '4': ['101', '101', '111', '001', '001'],
  '5': ['111', '100', '111', '001', '111'],
  '6': ['111', '100', '111', '101', '111'],
  '7': ['111', '001', '001', '001', '001'],
  '8': ['111', '101', '111', '101', '111'],
  '9': ['111', '101', '111', '001', '111'],
  ',': ['00', '00', '00', '01', '10'],
  '.': ['0', '0', '0', '0', '1'],
  ':': ['0', '1', '0', '1', '0'],
  ' ': ['00', '00', '00', '00', '00'],
  A: ['111', '101', '111', '101', '101'],
  B: ['110', '101', '110', '101', '110'],
  C: ['111', '100', '100', '100', '111'],
  D: ['110', '101', '101', '101', '110'],
  E: ['111', '100', '111', '100', '111'],
  F: ['111', '100', '111', '100', '100'],
  G: ['111', '100', '101', '101', '111'],
  H: ['101', '101', '111', '101', '101'],
  I: ['111', '010', '010', '010', '111'],
  J: ['001', '001', '001', '101', '111'],
  K: ['101', '101', '110', '101', '101'],
  L: ['100', '100', '100', '100', '111'],
  M: ['10001', '11011', '10101', '10001', '10001'],
  N: ['101', '111', '111', '111', '101'],
  O: ['111', '101', '101', '101', '111'],
  P: ['111', '101', '111', '100', '100'],
  Q: ['111', '101', '101', '111', '001'],
  R: ['111', '101', '111', '110', '101'],
  S: ['111', '100', '111', '001', '111'],
  T: ['111', '010', '010', '010', '010'],
  U: ['101', '101', '101', '101', '111'],
  V: ['101', '101', '101', '101', '010'],
  W: ['10001', '10001', '10101', '11011', '10001'],
  X: ['101', '101', '010', '101', '101'],
  Y: ['101', '101', '010', '010', '010'],
  Z: ['111', '001', '010', '100', '111'],
};

/** Width in cells of `text` when rendered (including inter-glyph gaps). */
export function measure(text) {
  const glyphs = [...text.toUpperCase()].map((c) => G[c]).filter(Boolean);
  if (!glyphs.length) return { cells: 0, rows: 5 };
  const cells = glyphs.reduce((n, g) => n + g[0].length, 0) + (glyphs.length - 1);
  return { cells, rows: 5 };
}

/**
 * Renders `text` as <rect>s, horizontally centred on `cx` with its top at `y`.
 * `cell` is the size of one text pixel in the same units as the viewBox, so
 * passing an integer keeps the text aligned to the artwork's pixel grid.
 */
export function pixelText(text, { cx, y, cell, fill }) {
  const chars = [...text.toUpperCase()].map((c) => G[c]).filter(Boolean);
  const { cells } = measure(text);
  let x = cx - (cells * cell) / 2;
  const out = [];

  for (const g of chars) {
    g.forEach((row, ry) => {
      // Emit horizontal runs rather than one <rect> per pixel — same output,
      // markedly fewer nodes.
      let run = 0;
      [...row].forEach((bit, rx) => {
        if (bit === '1') {
          run += 1;
          return;
        }
        if (run) {
          out.push(rect(x + (rx - run) * cell, y + ry * cell, run * cell, cell, fill));
          run = 0;
        }
      });
      if (run) {
        out.push(rect(x + (row.length - run) * cell, y + ry * cell, run * cell, cell, fill));
      }
    });
    x += (g[0].length + 1) * cell;
  }
  return out.join('');
}

function rect(x, y, w, h, fill) {
  return `<rect x="${+x.toFixed(2)}" y="${+y.toFixed(2)}" width="${+w.toFixed(2)}" height="${h}" fill="${fill}"/>`;
}
