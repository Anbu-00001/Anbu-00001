#!/usr/bin/env python3
"""
Graft one localised change from a generated plate onto the master, discarding
everything else it touched.

Generation reliably produces the change you asked for AND a global relight plus
incidental redraws elsewhere. Compositing only the changed region keeps the
former and throws away the latter.

  graft.py master.png plate.png out.png --box y0 y1 x0 x1
"""
import argparse
import numpy as np
import cv2
from PIL import Image, ImageFilter
from scipy.optimize import brentq


def lum(x):
    return 0.2126*x[:, :, 0] + 0.7152*x[:, :, 1] + 0.0722*x[:, :, 2]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('master'); p.add_argument('plate'); p.add_argument('out')
    p.add_argument('--box', nargs=4, type=int, required=True,
                   metavar=('Y0', 'Y1', 'X0', 'X1'))
    p.add_argument('--all-blobs', action='store_true',
                   help='keep every blob in the box, not just the largest. A procession '
                        'is a LINE of separate clusters -- largest-blob keeps one of them '
                        'and silently drops the rest.')
    p.add_argument('--min-area', type=int, default=25)
    p.add_argument('--opacity', type=float, default=1.0,
                   help='blend strength for the grafted region. An element that must '
                        'not pop into existence is brought up across frames instead.')
    p.add_argument('--thresh', type=float, default=12.0,
                   help='per-pixel diff above which a pixel counts as changed')
    p.add_argument('--feather', type=float, default=6.0)
    p.add_argument('--poly', help='regions.json key to use as the mask instead of '
                                  'blob-detecting the change')
    p.add_argument('--region-gamma', type=float, default=1.0,
                   help='gamma applied to the grafted region only')
    p.add_argument('--protect-cold', action='store_true',
                   help="restore cold-coloured pixels (the owl's eyes) at full "
                        "strength after any gamma/saturation work -- they sit "
                        "inside the window mask and must never be altered")
    p.add_argument('--region-sat', type=float, default=None,
                   help='target mean saturation for the grafted region; solves for '
                        'the scale toward luminance that hits it')
    a = p.parse_args()

    M = cv2.cvtColor(cv2.imread(a.master), cv2.COLOR_BGR2RGB).astype(np.float64)
    P = cv2.cvtColor(cv2.imread(a.plate), cv2.COLOR_BGR2RGB).astype(np.float64)
    y0, y1, x0, x1 = a.box

    # 1. Undo the plate's global relight before comparing, or the whole frame
    #    reads as "changed".
    f = lambda g: lum(255.0*np.power(np.clip(P, 0, 255)/255.0, g)).mean() - lum(M).mean()
    try:
        g = brentq(f, 0.3, 4.0)
        P = 255.0*np.power(np.clip(P, 0, 255)/255.0, g)
        print('  plate exposure matched to master, gamma %.4f' % g)
    except ValueError:
        print('  exposure match skipped')

    if a.poly:
        import json as _j
        from travel import window_mask
        poly = _j.load(open('regions.json'))[a.poly]
        m = window_mask(M.shape, poly, feather=a.feather).astype(np.float64)
        if a.region_gamma != 1.0:
            P = 255.0*np.power(np.clip(P, 0, 255)/255.0, a.region_gamma)
            print('  region gamma %.3f applied' % a.region_gamma)
        if a.region_sat is not None:
            sel = m[:, :, 0] > 0.5
            def sat(x):
                return (x.max(2) - x.min(2))[sel].mean()
            def pull(k):
                g_ = lum(P)[:, :, None]
                return np.clip(g_ + (P - g_) * k, 0, 255)
            f2 = lambda k: sat(pull(k)) - a.region_sat
            try:
                k = brentq(f2, 0.05, 2.0)
                P = pull(k)
                print('  saturation pulled to %.1f (k=%.3f)' % (sat(P), k))
            except ValueError:
                print('  saturation target unreachable, left as is')
        m = m * a.opacity
        out = M*(1-m) + P*m
        if a.protect_cold:
            src = cv2.cvtColor(cv2.imread(a.plate), cv2.COLOR_BGR2RGB).astype(np.int16)
            cold = ((src[:, :, 2] > src[:, :, 0] + 40) & (src[:, :, 2] > 120))
            cold = cv2.dilate(cold.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
            srcf = cv2.cvtColor(cv2.imread(a.plate), cv2.COLOR_BGR2RGB).astype(np.float64)
            out[cold] = srcf[cold]
            print('  %d cold px restored at full strength' % cold.sum())
        print('  graft covers %.3f%% of the canvas' % (m.mean()*100))
        Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(a.out)
        print('  wrote %s' % a.out); return

    # 2. Inside the box, find what actually moved.
    d = np.abs(M - P).mean(2)
    sel = np.zeros(d.shape, np.uint8)
    sel[y0:y1, x0:x1] = (d[y0:y1, x0:x1] > a.thresh).astype(np.uint8)

    # Keep only the largest blob -- the object -- and drop speckle.
    n, lab, stats, _ = cv2.connectedComponentsWithStats(sel, connectivity=8)
    if n > 1 and a.all_blobs:
        keep = np.zeros_like(sel)
        kept = 0
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] >= a.min_area:
                keep[lab == i] = 1
                kept += 1
        sel = keep
        print('  kept %d blob(s) of %d in the box, %d px' % (kept, n - 1, int(sel.sum())))
    elif n > 1:
        big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        sel = (lab == big).astype(np.uint8)
        bx, by, bw, bh, area = stats[big]
        print('  changed region: %dx%d at (%d,%d), %d px' % (bw, bh, bx, by, area))
    sel = cv2.morphologyEx(sel, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    sel = cv2.dilate(sel, np.ones((9, 9), np.uint8))

    m = np.asarray(Image.fromarray(sel*255).filter(
        ImageFilter.GaussianBlur(a.feather))).astype(np.float64)[:, :, None]/255.0
    m = m * a.opacity
    out = M*(1-m) + P*m
    print('  graft covers %.3f%% of the canvas' % (m.mean()*100))
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(a.out)
    print('  wrote %s' % a.out)


if __name__ == '__main__':
    main()
