#!/usr/bin/env python3
"""
Compress the readout zone's luminance range toward its bright end.

The readout ground cannot be contrasted against: it runs from near-black cloud
bands (rgb 53,24,49) to bright crimson, and no ink contrasts with both ends. Even
pure black reaches only 1.30:1 against the dark bands.

So fix the GROUND, which is what the Crimson Moon banner does -- its inscription
zone is a flat single colour precisely so the text can be read. Flattening sky to
a solid would read as a pasted panel, so instead the dark bands are lifted toward
the bright end while the bright end is left alone: the cloud texture survives at
low amplitude, the near-black bands do not.

  zonecalm.py in.png out.png --lift 0.75
"""
import argparse
import cv2
import numpy as np
from PIL import Image

ZONE = (86, 344, 958, 1322)          # y0 y1 x0 x1 -- must COVER the text block
                                     # (y 90-340) with margin, not merely overlap it


def main():
    p = argparse.ArgumentParser()
    p.add_argument('src'); p.add_argument('out')
    p.add_argument('--lift', type=float, default=0.88,
                   help='0 = untouched, 1 = fully flat at the zone bright level')
    p.add_argument('--pad', type=int, default=90)
    a = p.parse_args()

    F = np.array(Image.open(a.src).convert('RGB')).astype(np.float32)
    y0, y1, x0, x1 = ZONE
    lum = lambda x: 0.2126*x[:,:,0] + 0.7152*x[:,:,1] + 0.0722*x[:,:,2]

    sub = F[y0:y1, x0:x1].copy()
    L = lum(sub)

    #  Genuinely flatten, not merely lift. Measured under the actual text lines the
    #  ground ran rgb(65,26,54) to rgb(236,7,37): dark ink fails the dark bands
    #  (1.38:1) and light ink fails the bright ones (2.78:1). Nothing contrasts with
    #  both ends, so the ground must become one value -- which is precisely what the
    #  Crimson Moon banner does with its inscription zone, and what reference.png
    #  happens to have naturally where its lettering sits.
    #
    #  Flat BRIGHT with dark ink, not flat dark with light ink: that is the master's
    #  look, and it is the version that does not read as foreign.
    target_L = float(np.percentile(L, 85))
    hue = sub / np.maximum(L, 1.0)[..., None]          # keep each pixel's own colour
    hue = np.clip(hue, 0, 6)
    flat = np.clip(hue * target_L, 0, 255)

    #  Leave a little of the original banding so it still reads as cloud, not a panel.
    keep = 1.0 - a.lift
    sub = np.clip(flat * (1 - keep) + sub * keep, 0, 255)
    out = F.copy()
    out[y0:y1, x0:x1] = sub

    #  A raised-cosine (Hann) falloff, not a feathered rectangle.
    #
    #  A blurred rect still shows its edge: the lifted cloud bands meet unlifted ones
    #  along a straight line, and the eye finds that line instantly -- it read as a
    #  glass panel pasted into the sky. A separable Hann window has no boundary at
    #  all; the correction simply goes to nothing at the edges.
    cy, cx = (y0 + y1) / 2.0, (x0 + x1) / 2.0
    ry, rx = (y1 - y0) / 2.0 + a.pad, (x1 - x0) / 2.0 + a.pad
    yy = np.arange(F.shape[0], dtype=np.float32)[:, None]
    xx = np.arange(F.shape[1], dtype=np.float32)[None, :]
    ty = np.clip(np.abs(yy - cy) / ry, 0, 1)
    tx = np.clip(np.abs(xx - cx) / rx, 0, 1)
    m = (0.5 * (1 + np.cos(np.pi * ty))) * (0.5 * (1 + np.cos(np.pi * tx)))
    m = m[..., None].astype(np.float32)
    blend = np.clip(F * (1 - m) + out * m, 0, 255)

    z = lum(blend[y0:y1, x0:x1])
    print('  zone luma  p5 %.1f -> %.1f   median %.1f -> %.1f   p95 %.1f -> %.1f'
          % (np.percentile(L,5), np.percentile(z,5), np.median(L), np.median(z),
             np.percentile(L,95), np.percentile(z,95)))
    Image.fromarray(blend.astype(np.uint8)).save(a.out)


if __name__ == '__main__':
    main()
