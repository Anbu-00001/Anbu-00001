#!/usr/bin/env python3
"""
Stamp the readout labels onto a frame, taken from the art lock itself.

Text must never come from the generator. It cannot spell reliably, it re-letters
between frames, and a label that is re-drawn every frame CRAWLS -- which is fatal
here, because these words sit in the same place for the whole loop.

So the glyphs are lifted straight out of reference.png, where they were approved,
and composited as a PROPORTIONAL DARKENING (the letters measure 0.479x their own
local background) rather than as absolute pixels. That way the same glyphs sit
correctly on frames far darker than the reference, and they are bit-identical in
every frame they appear in.

The NUMBERS are deliberately not stamped here -- they change daily and belong to
the renderer. Only the fixed labels are baked.

  stamp.py in.png out.png --band 114 142 990 1290 --band 233 262 935 1300 --opacity 0.6
"""
import argparse
import cv2
import numpy as np
from PIL import Image


def lum(x):
    return 0.2126 * x[:, :, 0] + 0.7152 * x[:, :, 1] + 0.0722 * x[:, :, 2]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('src'); p.add_argument('out')
    p.add_argument('--ref', default='reference.png')
    p.add_argument('--band', nargs=4, type=int, action='append', required=True,
                   metavar=('Y0', 'Y1', 'X0', 'X1'))
    p.add_argument('--opacity', type=float, default=1.0)
    p.add_argument('--ratio', type=float, default=0.479,
                   help='glyph luminance as a fraction of its local background, '
                        'measured off the reference')
    p.add_argument('--sigma', type=float, default=25.0)
    p.add_argument('--cut', type=float, default=28.0)
    p.add_argument('--min-area', type=int, default=12)
    a = p.parse_args()

    F = np.array(Image.open(a.src).convert('RGB')).astype(np.float32)
    R = np.array(Image.open(a.ref).convert('RGB')).astype(np.float32)
    alpha = np.zeros(F.shape[:2], np.float32)

    for (y0, y1, x0, x1) in a.band:
        sub = lum(R)[y0:y1, x0:x1]
        bg = cv2.GaussianBlur(sub, (0, 0), a.sigma)
        al = np.clip((bg - sub) / a.cut, 0, 1)

        #  Drop cloud texture that happens to be darker than its surroundings:
        #  glyph strokes are solid and connected, cloud is speckle.
        seed = (al > 0.45).astype(np.uint8)
        seed = cv2.morphologyEx(seed, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        n, lab, st, _ = cv2.connectedComponentsWithStats(seed, 8)
        keep = np.zeros_like(seed)
        for i in range(1, n):
            if st[i, cv2.CC_STAT_AREA] >= a.min_area:
                keep[lab == i] = 1
        keep = cv2.dilate(keep, np.ones((3, 3), np.uint8))
        alpha[y0:y1, x0:x1] = al * keep
        print('  band y%d-%d x%d-%d: %d glyph px' % (y0, y1, x0, x1, int(keep.sum())))

    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.6)[..., None] * a.opacity
    out = np.clip(F * (1.0 - alpha * (1.0 - a.ratio)), 0, 255)
    Image.fromarray(out.astype(np.uint8)).save(a.out)
    print('  stamped at opacity %.2f -> %s' % (a.opacity, a.out))


if __name__ == '__main__':
    main()
