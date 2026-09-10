#!/usr/bin/env python3
"""
Take only the NEW LIGHT SOURCES out of a plate and add them to a master.

The beacon chain is additive point light on a landscape that must not otherwise
change. Grafting the window imports the re-inked landscape with it; relighting
smears point sources away, because a blurred ratio field cannot represent a
spark. Neither tool fits, so: find where the plate got brighter, keep the
compact sources and their haloes, and ADD that difference to the master.

The landscape is then the master's, pixel for pixel, with fires on it.

  addlight.py f09.png f10_raw.png out.png --poly window
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
    p.add_argument('--seed', type=float, default=25.0,
                   help='luma gain that marks a pixel as a light SOURCE')
    p.add_argument('--min-area', type=int, default=20)
    p.add_argument('--max-area', type=int, default=4000,
                   help='reject blobs bigger than a light source -- those are relights')
    p.add_argument('--halo', type=int, default=21,
                   help='dilation around each seed, to carry the glow as well as the core')
    p.add_argument('--feather', type=float, default=5.0)
    p.add_argument('--gain', type=float, default=1.0)
    p.add_argument('--order', choices=['right-to-left', 'left-to-right', 'area'],
                   default=None,
                   help='sort the sources before --take. A signal relay propagates '
                        'AWAY from its origin, so lighting them all in one frame is a '
                        'pop; ordering lets the chain ignite across several frames.')
    p.add_argument('--take', type=int, default=None,
                   help='keep only the first N sources after --order')
    p.add_argument('--skip', type=int, default=0,
                   help='drop the first N after --order (the ones already alight)')
    a = p.parse_args()

    M = np.array(Image.open(a.master).convert('RGB')).astype(np.float32)
    P = np.array(Image.open(a.plate).convert('RGB')).astype(np.float32)
    spec = json.load(open(a.regions))
    region = poly_mask(M.shape, spec, a.poly) > 127

    d = P - M
    seeds = ((lum(P) - lum(M)) > a.seed) & region

    n, lab, st, cen = cv2.connectedComponentsWithStats(seeds.astype(np.uint8), 8)
    keep = np.zeros_like(seeds, np.uint8)
    kept = []
    for i in range(1, n):
        area = st[i, cv2.CC_STAT_AREA]
        if a.min_area <= area <= a.max_area:
            keep[lab == i] = 1
            kept.append((int(area), int(cen[i][0]), int(cen[i][1])))
    if a.order:
        if a.order == 'right-to-left':
            kept.sort(key=lambda t: -t[1])
        elif a.order == 'left-to-right':
            kept.sort(key=lambda t: t[1])
        else:
            kept.sort(key=lambda t: -t[0])
        chosen = kept[a.skip:] if a.take is None else kept[a.skip:a.skip + a.take]
        drop = [t for t in kept if t not in chosen]
        for area, x, y in drop:
            keep[(lab == [i for i in range(1, n)
                          if int(cen[i][0]) == x and int(cen[i][1]) == y][0])] = 0
        kept = chosen
    print('  %d light source(s) kept of %d blobs' % (len(kept), n - 1))
    for area, x, y in sorted(kept, reverse=True)[:10]:
        print('     area %5d at x%5d y%4d' % (area, x, y))

    #  Grow past the seed so the glow comes with the core, not just the hot centre.
    grown = cv2.dilate(keep, np.ones((a.halo, a.halo), np.uint8))
    soft = cv2.GaussianBlur(grown.astype(np.float32), (0, 0), a.feather)[..., None]
    soft *= region[..., None]

    out = np.clip(M + np.clip(d, 0, None) * soft * a.gain, 0, 255)
    Image.fromarray(out.astype(np.uint8)).save(a.out)
    print('  added light over %.3f%% of the canvas; landscape untouched'
          % (soft.mean() * 100))
    print('  %s luma %.2f -> %.2f' % (a.poly, lum(M)[region].mean(), lum(out)[region].mean()))
    print('  wrote %s' % a.out)


if __name__ == '__main__':
    main()
