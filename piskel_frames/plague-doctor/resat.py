#!/usr/bin/env python3
"""
Restore saturation inside one region without touching its exposure.

Written after the gate's saturation metric was found to be luminance-confounded:
it measured raw chroma (max-min), which scales linearly with brightness, so a
frame that had merely been brightened read as "too saturated".  Steering by it
desaturated f07's window to HSV S 0.498 while every other frame in the sequence
sat at 0.655-0.671 -- a one-frame colour pothole.

Scales HSV S about the region's mean to hit a target, holds H, then restores the
region's original mean luminance so this cannot smuggle in an exposure change.

  resat.py in.png out.png --poly window --target-s 0.665
"""
import argparse
import json
import cv2
import numpy as np
from PIL import Image
from scipy.optimize import brentq


def lum(x):
    return 0.2126 * x[:, :, 0] + 0.7152 * x[:, :, 1] + 0.0722 * x[:, :, 2]


def poly_mask(shape, spec, key):
    m = np.zeros(shape[:2], np.uint8)
    pts = spec[key]
    if isinstance(pts, str):                      # "~window" -> complement
        return 255 - poly_mask(shape, spec, pts.lstrip('~'))
    cv2.fillPoly(m, [np.array(pts, np.int32)], 255)
    return m


def main():
    p = argparse.ArgumentParser()
    p.add_argument('src'); p.add_argument('out')
    p.add_argument('--poly', required=True)
    p.add_argument('--regions', default='regions.json')
    p.add_argument('--target-s', type=float, required=True)
    p.add_argument('--target-luma', type=float, default=None,
                   help='solve a region gamma for this mean luminance FIRST, '
                        'so the saturation solve runs on the final exposure')
    p.add_argument('--feather', type=float, default=4.0)
    a = p.parse_args()

    img = np.array(Image.open(a.src).convert('RGB')).astype(np.float32)
    spec = json.load(open(a.regions))
    hard = poly_mask(img.shape, spec, a.poly)
    sel = hard > 127
    soft = cv2.GaussianBlur(hard.astype(np.float32) / 255.0, (0, 0), a.feather)[..., None]

    orig = img.copy()          #  the pixels outside the region must survive untouched;
                               #  the exposure solve below rewrites `img` in place
    def gate_sat(x):
        """The gate's own measure -- (max-min)/max with a near-black floor.
        Solve against THIS, not OpenCV's, or the two disagree by ~0.05."""
        mx, mn = x.max(2), x.min(2)
        return np.where(mx > 1.0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)

    def scaled(k):
        """Scale chroma about luma: exactly luma-preserving, since the weights
        sum to 1, so a saturation tool can never smuggle in a relight."""
        L = lum(img)[..., None]
        return np.clip(L + (img - L) * k, 0, 255)

    if a.target_luma is not None:
        #  Exposure first: the saturation solve must run on the pixels that ship,
        #  and gamma is not commutative with a chroma scale.
        base = lum(img)[sel].mean()
        gf = lambda g: lum(255.0 * np.power(np.clip(img, 0, 255) / 255.0, g))[sel].mean() - a.target_luma
        if gf(0.2) * gf(6.0) > 0:
            raise SystemExit(f'target luma {a.target_luma} unreachable from {base:.2f}')
        gam = brentq(gf, 0.2, 6.0, xtol=1e-5)
        img = 255.0 * np.power(np.clip(img, 0, 255) / 255.0, gam)
        print(f'  region luma {base:.2f} -> {lum(img)[sel].mean():.2f} (gamma {gam:.4f})')

    cur = gate_sat(img)[sel].mean()
    lo, hi = 0.05, 8.0
    f = lambda k: gate_sat(scaled(k))[sel].mean() - a.target_s
    if f(lo) * f(hi) > 0:
        raise SystemExit(f'target S {a.target_s} unreachable from {cur:.4f}')
    k = brentq(f, lo, hi, xtol=1e-4)
    out = scaled(k)
    print(f'  region {a.poly}: mean S {cur:.4f} -> target {a.target_s:.4f}  (chroma x{k:.4f})')
    print(f'  luma {lum(img)[sel].mean():.3f} -> {lum(out)[sel].mean():.3f}  (held by construction)')

    #  Blend against ORIG, not img: --target-luma gammas the whole array, and
    #  blending against that leaked the region's exposure change into every pixel
    #  outside it. f08 shipped with its interior quietly lifted +1.2% that way.
    blend = np.clip(orig * (1 - soft) + out * soft, 0, 255).astype(np.uint8)
    Image.fromarray(blend).save(a.out)
    b = blend.astype(np.float32)
    print(f'  wrote {a.out}: S {gate_sat(b)[sel].mean():.4f}  luma {lum(b)[sel].mean():.3f}')


if __name__ == '__main__':
    main()
