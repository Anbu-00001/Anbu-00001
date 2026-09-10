#!/usr/bin/env python3
"""
Strengthen the crimson gleam already inside the carriage.

Not a flat wash: a wash lifts the shadows and flattens the figure, which is the
one thing the interior cannot afford -- his silhouette against a brighter window
is what the whole piece rests on. Instead this AMPLIFIES the light that is
already there. Pixels that are already crimson-leaning and already catching some
light get more of it; flat black stays flat black.

Falls off with distance from the window, because that is where the light is
coming from.

  gleam.py in.png out.png --poly interior --amount 0.5
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
    p.add_argument('src'); p.add_argument('out')
    p.add_argument('--poly', default='interior')
    p.add_argument('--regions', default='regions.json')
    p.add_argument('--amount', type=float, default=0.5)
    p.add_argument('--window-x', type=float, default=950.0,
                   help='light source edge; the gleam falls off away from it')
    p.add_argument('--falloff', type=float, default=900.0)
    p.add_argument('--floor', type=float, default=6.0,
                   help='luma below which a pixel is unlit and stays unlit')
    p.add_argument('--knee', type=float, default=55.0,
                   help='luma above which a pixel is already fully lit')
    a = p.parse_args()

    F = np.array(Image.open(a.src).convert('RGB')).astype(np.float32)
    spec = json.load(open(a.regions))
    reg = (poly_mask(F.shape, spec, a.poly) > 127).astype(np.float32)
    reg = cv2.GaussianBlur(reg, (0, 0), 6.0)

    L = lum(F)
    #  Already catching light -- ramps in above the floor, saturates at the knee.
    lit = np.clip((L - a.floor) / max(a.knee - a.floor, 1e-6), 0, 1)
    #  Already crimson-leaning: red ahead of the other two channels.
    warm = np.clip((F[:, :, 0] - 0.5 * (F[:, :, 1] + F[:, :, 2])) / 35.0, 0, 1)

    H, W = L.shape
    xs = np.arange(W, dtype=np.float32)[None, :].repeat(H, 0)
    dist = np.clip((a.window_x - xs) / a.falloff, 0, 1)     # 0 at the glass, 1 far from it
    near = (1.0 - dist) ** 1.5

    k = (lit * warm * near * reg * a.amount)[..., None]
    crimson = np.array([1.00, 0.20, 0.26], np.float32)
    out = np.clip(F + F * k * crimson[None, None, :] * 1.35, 0, 255)

    sel = reg > 0.5
    print('  interior luma %.2f -> %.2f   gleam on %.1f%% of it'
          % (lum(F)[sel].mean(), lum(out)[sel].mean(), (k[:, :, 0][sel] > 0.03).mean() * 100))
    Image.fromarray(out.astype(np.uint8)).save(a.out)
    print('  wrote %s' % a.out)


if __name__ == '__main__':
    main()
