#!/usr/bin/env python3
"""
Lift the reserved sky zone to the brightness the reference readout was drawn for.

The art lock sets near-black inscriptional capitals in that zone, and they read
there because the sky behind them is rgb(113,18,46). Our sky is dimmer at the same
point, so the reference's own ink goes muddy. Rather than change the ink -- which
would depart from the approved art -- change the GROUND to the condition the ink
was designed against.

Ramped in with the sky opening (nothing before f07), so it never appears as a
bright patch pasted onto the forest.

  zonelift.py in.png out.png --amount 1.0
"""
import argparse
import cv2
import numpy as np
from PIL import Image

ZONE = (93, 332, 963, 1313)      # y0 y1 x0 x1, full-res
GAIN = np.array([1.30, 1.06, 1.13], np.float32)   # crimson, not a neutral lift


def main():
    p = argparse.ArgumentParser()
    p.add_argument('src'); p.add_argument('out')
    p.add_argument('--amount', type=float, default=1.0)
    p.add_argument('--feather', type=float, default=34.0)
    a = p.parse_args()

    F = np.array(Image.open(a.src).convert('RGB')).astype(np.float32)
    y0, y1, x0, x1 = ZONE
    m = np.zeros(F.shape[:2], np.float32)
    m[y0 - 20:y1 + 20, x0 - 26:x1 + 26] = 1.0
    m = cv2.GaussianBlur(m, (0, 0), a.feather)[..., None] * a.amount

    out = np.clip(F * (1.0 + (GAIN - 1.0)[None, None, :] * m), 0, 255)
    lum = lambda x: 0.2126*x[:,:,0] + 0.7152*x[:,:,1] + 0.0722*x[:,:,2]
    sel = np.zeros(F.shape[:2], bool); sel[y0:y1, x0:x1] = True
    print('  zone luma %.2f -> %.2f  (reference 37.2)' % (lum(F)[sel].mean(), lum(out)[sel].mean()))
    Image.fromarray(out.astype(np.uint8)).save(a.out)


if __name__ == '__main__':
    main()
