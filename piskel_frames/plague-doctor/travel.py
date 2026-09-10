#!/usr/bin/env python3
"""
Build a frame by TRANSFORMING the plate's window instead of regenerating it.

Rationale, measured: over a 0.9s hold the world moves ~12px on this canvas. At
that magnitude the difference between true per-depth parallax and a single
translate+scale is 2-3px -- invisible. The difference between transforming and
regenerating is the entire forest changing identity (window inlier ratio 0.21).

  travel.py plate.png out.png --dx -11.7 --dy 2 --scale 1.008
"""
import argparse, json
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def window_mask(shape, poly, feather=2.5):
    h, w = shape[:2]
    m = Image.new('L', (w, h), 0)
    ImageDraw.Draw(m).polygon([tuple(p) for p in poly], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(feather))
    return (np.asarray(m).astype(np.float32) / 255.0)[:, :, None]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('plate'); p.add_argument('out')
    p.add_argument('--dx', type=float, default=0.0)
    p.add_argument('--dy', type=float, default=0.0)
    p.add_argument('--scale', type=float, default=1.0)
    p.add_argument('--regions', default='regions.json')
    p.add_argument('--match-exposure', action='store_true',
                   help='rebalance the transformed window to the plate\'s level; '
                        'scaling about the far corner pulls darker content in')
    a = p.parse_args()

    im = Image.open(a.plate).convert('RGB')
    W, H = im.size
    P = np.asarray(im).astype(np.float64)

    # Scale about the vanishing point we travel toward -- the window's far
    # (upper-right) corner -- so growth radiates outward from it the way forward
    # motion actually looks.
    cx, cy, s = W * 0.98, H * 0.10, a.scale
    inv = (1/s, 0, cx - cx/s - a.dx/s,
           0, 1/s, cy - cy/s - a.dy/s)
    M = np.asarray(im.transform((W, H), Image.AFFINE, inv,
                                resample=Image.BICUBIC)).astype(np.float64)

    # Refill whatever the transform vacated at the edges from the plate itself.
    e = int(abs(a.dx) + abs(a.dy) + 4)
    M[:, -e:] = P[:, -e:]
    M[-e:, :] = P[-e:, :]

    poly = json.load(open(a.regions))['window']
    m = window_mask(P.shape, poly)

    if a.match_exposure:
        sel = m[:, :, 0] > 0.5
        def lum(x):
            return (0.2126*x[:,:,0] + 0.7152*x[:,:,1] + 0.0722*x[:,:,2])[sel].mean()
        tgt, cur = lum(P), lum(M)
        if cur > 1e-6:
            from scipy.optimize import brentq
            f = lambda g: lum(255.0*np.power(np.clip(M,0,255)/255.0, g)) - tgt
            try:
                g = brentq(f, 0.3, 4.0)
                M = 255.0*np.power(np.clip(M,0,255)/255.0, g)
                print('  window exposure matched, gamma %.4f' % g)
            except ValueError:
                pass
    out = P * (1 - m) + M * m
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(a.out)
    print('  %s  dx=%+.1f dy=%+.1f scale=%.4f' % (a.out, a.dx, a.dy, a.scale))


if __name__ == '__main__':
    main()
