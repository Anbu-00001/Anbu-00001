#!/usr/bin/env python3
"""
Restore a carved/incised detail from the art lock onto a frame.

The sill carving SAME DISEASE, DIFFERENT KINGS was dropped by the generator when
it produced f01 from reference.png, and every later frame inherited the loss
through the graft pipeline. The gate never saw it: it scores frame N+1 against
frame N and never looks at the reference, so a feature lost at f01 is perfectly
consistent forever after.

Pasting reference pixels would drag the reference's lighting in with them. So
transfer the ENGRAVING ONLY, as a high-pass detail layer, and scale it by how
lit the target's sill actually is -- which means the carving emerges as the
world brightens, instead of sitting at a fixed strength through a lighting ramp.

  engrave.py f08.png out.png --ref reference.png --box 700 812 1040 1774
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
    p.add_argument('--box', nargs=4, type=int, required=True,
                   metavar=('Y0', 'Y1', 'X0', 'X1'))
    p.add_argument('--sigma', type=float, default=3.0,
                   help='high-pass cutoff; the carving strokes are a few px wide')
    p.add_argument('--feather', type=float, default=10.0)
    p.add_argument('--dx', type=float, default=1.32)   # reference -> f01, measured
    p.add_argument('--dy', type=float, default=-0.32)
    p.add_argument('--strength', type=float, default=1.0,
                   help='detail transfer strength; pass 0 to add ONLY glow to a carving '
                        'that is already present, without doubling it')
    p.add_argument('--glow', type=float, default=0.0,
                   help='crimson light in the incised strokes themselves')
    p.add_argument('--glow-sigma', type=float, default=7.0,
                   help='halo radius bleeding out of the letters into the stone')
    p.add_argument('--glow-halo', type=float, default=0.55)
    a = p.parse_args()

    F = np.array(Image.open(a.src).convert('RGB')).astype(np.float32)
    R = np.array(Image.open(a.ref).convert('RGB')).astype(np.float32)
    M = np.float32([[1, 0, a.dx], [0, 1, a.dy]])
    R = cv2.warpAffine(R, M, (R.shape[1], R.shape[0]), flags=cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_REPLICATE)

    y0, y1, x0, x1 = a.box
    detail = R - cv2.GaussianBlur(R, (0, 0), a.sigma)       # the incision, no lighting

    #  Scale to the target's own light.  The reference is the fully-lit end state;
    #  a frame at half that brightness should carry a proportionally shallower
    #  carving, so it surfaces as the light arrives rather than popping in.
    rl = lum(R[y0:y1, x0:x1]).mean()
    fl = lum(F[y0:y1, x0:x1]).mean()
    k = a.strength * (fl / max(rl, 1e-6))

    mask = np.zeros(F.shape[:2], np.float32)
    mask[y0:y1, x0:x1] = 1.0
    mask = cv2.GaussianBlur(mask, (0, 0), a.feather)[..., None]

    out = F + detail * k * mask

    if a.glow > 0:
        #  Light the strokes from within rather than lighting the whole sill: take
        #  the LIT side of the incision, tint it to the piece's crimson, and bleed a
        #  halo into the stone around it. Ramped across frames so the words surface
        #  as the world brightens instead of switching on.
        lit = np.clip(lum(detail), 0, None)
        halo = cv2.GaussianBlur(lit, (0, 0), a.glow_sigma) * a.glow_halo
        crimson = np.array([1.00, 0.13, 0.20], np.float32)      # hue ~-9deg, in palette
        glow = (lit + halo)[..., None] * crimson[None, None, :]
        out = out + glow * a.glow * mask
    out = np.clip(out, 0, 255)
    Image.fromarray(out.astype(np.uint8)).save(a.out)

    def energy(img):
        g = cv2.cvtColor(img[y0:y1, x0:x1].astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
        g = (g - g.mean()) / max(g.std(), 1e-6)
        return cv2.Laplacian(g, cv2.CV_32F).var()
    print('  %s: sill luma %.2f vs reference %.2f -> strength %.3f' % (a.src, fl, rl, k))
    print('  detail energy %.3f -> %.3f  (reference %.3f)'
          % (energy(F), energy(out), energy(R)))
    print('  wrote %s' % a.out)


if __name__ == '__main__':
    main()
