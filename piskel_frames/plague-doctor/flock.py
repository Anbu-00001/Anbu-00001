#!/usr/bin/env python3
"""
Extract silhouettes from a plate and fly them along a path as a seamless cycle.

Generated once, animated in post. Regenerating birds every frame would boil them
and could never close the loop: for f15 to flow into f12 the configuration has to
repeat exactly, which means a CONVEYOR -- n birds evenly spaced along a path,
each advancing 1/frames of that spacing per frame, so after a full cycle every
bird sits where the one ahead of it was and the set is identical.

Sprites are lifted as an alpha matte from how much DARKER the plate is than the
master, so a silhouette carries no colour of its own and takes the sky it is
placed on.

  flock.py base.png out.png --plate f12_raw.png --master f11.png \
      --src 170 210 1418 1462 --path 1770 185 1330 265 --n 3 --phase 0
"""
import argparse
import cv2
import numpy as np
from PIL import Image


def lum(x):
    return 0.2126 * x[:, :, 0] + 0.7152 * x[:, :, 1] + 0.0722 * x[:, :, 2]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('base'); p.add_argument('out')
    p.add_argument('--plate', required=True); p.add_argument('--master', required=True)
    p.add_argument('--src', nargs=4, type=int, action='append', required=True,
                   metavar=('Y0', 'Y1', 'X0', 'X1'))
    p.add_argument('--path', nargs=4, type=float, required=True,
                   metavar=('X0', 'Y0', 'X1', 'Y1'))
    p.add_argument('--n', type=int, default=3)
    p.add_argument('--phase', type=float, default=0.0, help='0..1 through one spacing')
    p.add_argument('--cut', type=float, default=18.0)
    p.add_argument('--darkness', type=float, default=0.30,
                   help='silhouette luminance as a fraction of the sky behind it')
    p.add_argument('--scale-near', type=float, default=1.0)
    p.add_argument('--scale-far', type=float, default=0.55)
    a = p.parse_args()

    B = np.array(Image.open(a.base).convert('RGB')).astype(np.float32)
    P = np.array(Image.open(a.plate).convert('RGB')).astype(np.float32)
    M = np.array(Image.open(a.master).convert('RGB')).astype(np.float32)
    g = lum(M).mean() / max(lum(P).mean(), 1e-6)
    D = lum(M) - lum(P) * g                      # positive where the plate is darker

    sprites = []
    for (y0, y1, x0, x1) in a.src:
        al = np.clip(D[y0:y1, x0:x1] / a.cut, 0, 1)
        al = cv2.GaussianBlur(al, (0, 0), 0.7)
        if al.max() < 0.35:
            print('  WARNING: weak sprite at y%d x%d (max alpha %.2f)' % (y0, x0, al.max()))
        sprites.append(al.astype(np.float32))
        print('  sprite %dx%d, %d px above half alpha' % (al.shape[1], al.shape[0], int((al > .5).sum())))

    x0, y0, x1, y1 = a.path
    H, W = B.shape[:2]
    out = B.copy()
    for i in range(a.n):
        t = ((i + a.phase) / a.n) % 1.0          # even spacing, advanced by phase
        cx, cy = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        s = a.scale_near + (a.scale_far - a.scale_near) * t
        al = sprites[i % len(sprites)]
        sh, sw = al.shape
        nw, nh = max(3, int(sw * s)), max(3, int(sh * s))
        al2 = cv2.resize(al, (nw, nh), interpolation=cv2.INTER_AREA)
        px, py = int(cx - nw / 2), int(cy - nh / 2)
        if px < 0 or py < 0 or px + nw > W or py + nh > H:
            print('  skipped a bird off-canvas at (%d,%d)' % (px, py)); continue
        roi = out[py:py + nh, px:px + nw]
        A3 = al2[..., None]
        out[py:py + nh, px:px + nw] = roi * (1 - A3 * (1 - a.darkness))
        print('  bird %d at x%4d y%4d  scale %.2f' % (i + 1, int(cx), int(cy), s))

    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(a.out)
    print('  wrote %s' % a.out)


if __name__ == '__main__':
    main()
