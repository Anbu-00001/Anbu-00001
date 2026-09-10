#!/usr/bin/env python3
"""
Move light from a generated plate onto a master without moving any geometry.

The generator relights and redraws the interior every single time it is asked for
anything. Grafting its pixels imports the redraw (line boil on the coat folds, the
book shifting, the hat re-inked). Keeping the master's pixels loses the lighting
change we actually wanted.

So transfer only the LUMINANCE ENVELOPE: the ratio of plate luminance to master
luminance, blurred hard enough that no edge survives it, applied as a gain to the
master. Broad falloff crosses over; strokes do not. It is also colour-blind by
construction -- the plate's hue never enters -- so a plate that came back too warm
cannot drag its warmth along with the light.

  relight.py f08.png f09_raw.png out.png --poly interior --target-luma 19.0
"""
import argparse
import json
import cv2
import numpy as np
from PIL import Image


def lum(x):
    return 0.2126 * x[:, :, 0] + 0.7152 * x[:, :, 1] + 0.0722 * x[:, :, 2]


def poly_mask(shape, spec, key):
    m = np.zeros(shape[:2], np.uint8)
    pts = spec[key]
    if isinstance(pts, str):
        return 255 - poly_mask(shape, spec, pts.lstrip('~'))
    cv2.fillPoly(m, [np.array(pts, np.int32)], 255)
    return m


def main():
    p = argparse.ArgumentParser()
    p.add_argument('master'); p.add_argument('plate'); p.add_argument('out')
    p.add_argument('--poly', required=True)
    p.add_argument('--regions', default='regions.json')
    p.add_argument('--sigma', type=float, default=40.0,
                   help='blur on the ratio field; must exceed the width of any '
                        'stroke that must not transfer')
    p.add_argument('--clip', nargs=2, type=float, default=[0.6, 2.5])
    p.add_argument('--target-luma', type=float, default=None)
    p.add_argument('--feather', type=float, default=8.0)
    a = p.parse_args()

    M = np.array(Image.open(a.master).convert('RGB')).astype(np.float32)
    P = np.array(Image.open(a.plate).convert('RGB')).astype(np.float32)
    spec = json.load(open(a.regions))
    hard = poly_mask(M.shape, spec, a.poly)
    sel = hard > 127
    soft = cv2.GaussianBlur(hard.astype(np.float32) / 255.0, (0, 0), a.feather)[..., None]

    lm = cv2.GaussianBlur(lum(M), (0, 0), a.sigma)
    lp = cv2.GaussianBlur(lum(P), (0, 0), a.sigma)
    ratio = np.clip(lp / np.maximum(lm, 1.0), a.clip[0], a.clip[1])[..., None]

    out = np.clip(M * ratio, 0, 255)
    if a.target_luma is not None:
        g = a.target_luma / max(lum(out)[sel].mean(), 1e-6)
        out = np.clip(out * g, 0, 255)
        print('  normalised to target: gain x%.4f' % g)

    blend = np.clip(M * (1 - soft) + out * soft, 0, 255).astype(np.uint8)
    Image.fromarray(blend).save(a.out)
    b = blend.astype(np.float32)
    print('  %s luma %.2f -> %.2f  (plate was %.2f)'
          % (a.poly, lum(M)[sel].mean(), lum(b)[sel].mean(), lum(P)[sel].mean()))
    print('  ratio field: min %.3f max %.3f  -- geometry untouched' % (ratio.min(), ratio.max()))
    print('  wrote %s' % a.out)


if __name__ == '__main__':
    main()
