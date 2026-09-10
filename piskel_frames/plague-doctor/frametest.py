#!/usr/bin/env python3
"""
frametest — continuity testing for a sequence of PNG animation frames.

TWO STAGES, IN THIS ORDER. The order is the whole idea.

  STAGE 1  REGISTRATION   Recover the rigid transform taking A to B.
                          Answers "did this MOVE?" and by how much.
  STAGE 2  RESIDUAL       Align A onto B by that transform, THEN compare.
                          Answers "what changed BEYOND the motion?"

Why the order matters, measured on this project (see TESTING.md):
appearance metrics run on unaligned frames are useless here and two of them are
actively inverted -- FLIP scored a correct 15px pan (0.1755) as WORSE than a
complete redraw (0.1721), and SSIM called the redraw 40% more similar than the
correct motion. They have no motion model, so they punish legitimate movement.
Run after registration, the same metrics separate the cases by ~80x.

Usage
  frametest.py A.png B.png [--hold 0.9] [--regions regions.json] [--expect-dx N]
  frametest.py --sequence 'f*.png' [--holds 0.9,0.5,0.12]

regions.json (optional):
  {"window": [[962,0],[1774,0],[1774,652],[1050,412]], "interior": "~window"}
  A "~name" value means the complement of that polygon.
"""
import argparse, glob, json, sys
import numpy as np
import cv2
from skimage.metrics import structural_similarity as ssim
from skimage.color import rgb2lab, deltaE_ciede2000
import flip_evaluator as flip

# Thresholds calibrated against synthetic controls (identity / known translation
# / independent regeneration). See TESTING.md for the calibration table.
INLIER_PASS   = 0.80   # below this, no single transform explains the change
FLIP_PASS     = 0.05   # residual after registration
FLIP_WARN     = 0.10
SSIM_PASS     = 0.95
DE_PASS       = 1.50   # CIEDE2000, perceptual colour drift


def read(p):
    im = cv2.imread(p, cv2.IMREAD_COLOR)
    if im is None:
        sys.exit('cannot read %s' % p)
    return cv2.cvtColor(im, cv2.COLOR_BGR2RGB)


def poly_mask(shape, pts):
    m = np.zeros(shape[:2], np.uint8)
    cv2.fillPoly(m, [np.array(pts, np.int32)], 255)
    return m


def build_masks(shape, spec):
    if not spec:
        return {'whole frame': np.full(shape[:2], 255, np.uint8)}
    out, deferred = {}, {}
    for name, v in spec.items():
        if isinstance(v, str) and v.startswith('~'):
            deferred[name] = v[1:]
        else:
            out[name] = poly_mask(shape, v)
    for name, src in deferred.items():
        out[name] = 255 - out[src]
    return out


def register(a, b, mask=None):
    """ORB + RANSAC partial-affine (translation, rotation, uniform scale).

    Returns (M, inlier_ratio, n_matches). A low inlier ratio is the signal that
    the change is NOT a rigid movement -- i.e. the content was redrawn.
    """
    ga = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY)
    gb = cv2.cvtColor(b, cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(6000)
    ka, da = orb.detectAndCompute(ga, mask)
    kb, db = orb.detectAndCompute(gb, mask)
    if da is None or db is None or len(da) < 12 or len(db) < 12:
        return None, 0.0, 0
    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(da, db)
    if len(matches) < 12:
        return None, 0.0, len(matches)
    pa = np.float32([ka[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    pb = np.float32([kb[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    M, inl = cv2.estimateAffinePartial2D(pa, pb, method=cv2.RANSAC,
                                         ransacReprojThreshold=3.0, maxIters=5000)
    if M is None:
        return None, 0.0, len(matches)
    return M, float(inl.mean()) if inl is not None else 0.0, len(matches)


def phase_shift(a, b, mask=None):
    """FFT phase correlation. Independent, sub-pixel translation estimate --
    a second opinion on registration that shares none of ORB's failure modes."""
    ga = np.float32(cv2.cvtColor(a, cv2.COLOR_RGB2GRAY))
    gb = np.float32(cv2.cvtColor(b, cv2.COLOR_RGB2GRAY))
    if mask is not None:
        ga, gb = ga * (mask > 0), gb * (mask > 0)
    win = cv2.createHanningWindow(ga.shape[::-1], cv2.CV_32F)
    (dx, dy), resp = cv2.phaseCorrelate(ga, gb, win)
    return dx, dy, resp


SHADING_SIGMA = 60.0    # slower-varying than any stroke that must not be normalised away


def residual(a_aligned, b, mask=None, match_level=True):
    """Appearance metrics on the ALIGNED pair: what motion does not explain.

    Averaged over the MASKED PIXELS, not the mask's bounding box. A complement
    region (e.g. interior = ~window) wraps around its counterpart, so its
    bounding box is the whole canvas -- cropping to it silently measured the
    window while claiming to measure the interior.
    """
    sel = None
    if mask is not None:
        sel = mask > 0
        if sel.sum() < 100:
            return None

    #  Divide out the low-frequency shading field before comparing.
    #
    #  FLIP, grey SSIM and CIEDE2000 all respond hard to a brightness change, and
    #  this residual is supposed to measure "what motion does not explain" --
    #  structure -- not exposure. Exposure is already scored separately, against a
    #  declared ramp. Charging it here as well prices the same fact twice, and it
    #  failed f09 for doing its only job: a frame whose whole purpose is a large
    #  NON-uniform relight scored 43% on a window that was geometrically perfect.
    #
    #  A single gain is not enough, because the change is a gradient, not a level.
    #  Dividing by the blurred luminance ratio removes any shading that varies
    #  slower than SIGMA and leaves everything sharper than it -- which is exactly
    #  what line boil and redraws are. Measured separation at sigma 60:
    #      relit, geometry identical   FLIP 0.037  SSIM 0.991  dE 1.02
    #      genuine redraw              FLIP 0.085  SSIM 0.954  dE 3.50
    #  and that 2-3x margin holds from sigma 30 to 100, so it is not tuned.
    if match_level:
        def _l(x):
            return 0.2126*x[:, :, 0] + 0.7152*x[:, :, 1] + 0.0722*x[:, :, 2]
        sig = SHADING_SIGMA
        la = cv2.GaussianBlur(_l(a_aligned.astype(np.float32)), (0, 0), sig)
        lb = cv2.GaussianBlur(_l(b.astype(np.float32)), (0, 0), sig)
        r = np.clip(la / np.maximum(lb, 1.0), 0.25, 4.0)[..., None]
        b = np.clip(b.astype(np.float32) * r, 0, 255).astype(np.uint8)

    # FLIP returns a per-pixel error map; average it over the selection.
    emap, fmean, _ = flip.evaluate(a_aligned.astype(np.float32)/255.,
                                   b.astype(np.float32)/255., "LDR")
    emap = np.asarray(emap)
    if emap.ndim == 3:
        emap = emap.mean(axis=2)
    f = float(emap[sel].mean()) if sel is not None else float(fmean)

    # SSIM likewise exposes its full similarity map.
    _, smap = ssim(cv2.cvtColor(a_aligned, cv2.COLOR_RGB2GRAY),
                   cv2.cvtColor(b, cv2.COLOR_RGB2GRAY), full=True)
    s = float(smap[sel].mean()) if sel is not None else float(smap.mean())

    dmap = deltaE_ciede2000(rgb2lab(a_aligned/255.), rgb2lab(b/255.))
    de = float(dmap[sel].mean()) if sel is not None else float(dmap.mean())
    return f, s, de


def mark(ok, warn=False):
    return 'WARN' if warn else ('PASS' if ok else 'FAIL')


def compare(pa, pb, hold, masks_spec, expect_dx=None):
    A, B = read(pa), read(pb)
    print('\n%s  ->  %s   (hold %.2fs)' % (pa, pb, hold))
    if A.shape != B.shape:
        print('  [FAIL] shape %s vs %s' % (A.shape, B.shape))
        return 1, 0
    masks = build_masks(A.shape, masks_spec)
    fails = warns = 0

    for name, mask in masks.items():
        print('\n  %s' % name.upper())
        M, inl, nm = register(A, B, mask)
        dxp, dyp, resp = phase_shift(A, B, mask)

        if M is None:
            print('    [FAIL] registration failed (%d matches)' % nm); fails += 1
            continue
        dx, dy = float(M[0, 2]), float(M[1, 2])
        scale = float(np.hypot(M[0, 0], M[1, 0]))
        print('    stage 1  transform  dx=%+.2f dy=%+.2f scale=%.4f' % (dx, dy, scale))
        print('             phase corr dx=%+.2f dy=%+.2f (independent check, resp %.3f)'
              % (dxp, dyp, resp))
        ok = inl >= INLIER_PASS
        print('    [%s] inlier ratio %.3f of %d matches  (floor %.2f)'
              % (mark(ok), inl, nm, INLIER_PASS))
        if not ok:
            print('           -> no single rigid transform explains this region.')
            print('              The content was REDRAWN, not moved.')
            fails += 1

        if expect_dx is not None:
            good = abs(dx - expect_dx) <= max(3.0, abs(expect_dx) * 0.35)
            print('    [%s] dx %+.2f vs expected %+.2f' % (mark(good), dx, expect_dx))
            fails += not good

        Aw = cv2.warpAffine(A, M, (A.shape[1], A.shape[0]),
                            flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        r = residual(Aw, B, mask)
        if r is None:
            continue
        f, s, de = r
        fs = mark(f <= FLIP_PASS, FLIP_WARN >= f > FLIP_PASS)
        print('    stage 2  residual after registration')
        print('    [%s] FLIP %.4f   (pass <= %.2f)' % (fs, f, FLIP_PASS))
        fails += fs == 'FAIL'; warns += fs == 'WARN'
        ok = s >= SSIM_PASS
        print('    [%s] SSIM %.4f   (pass >= %.2f)' % (mark(ok), s, SSIM_PASS))
        fails += not ok
        ok = de <= DE_PASS
        print('    [%s] dCIEDE2000 %.3f   (pass <= %.2f)' % (mark(ok), de, DE_PASS))
        fails += not ok
    return fails, warns


def main():
    p = argparse.ArgumentParser()
    p.add_argument('frames', nargs='*')
    p.add_argument('--sequence')
    p.add_argument('--hold', type=float, default=0.5)
    p.add_argument('--holds')
    p.add_argument('--regions')
    p.add_argument('--expect-dx', type=float)
    a = p.parse_args()

    spec = json.load(open(a.regions)) if a.regions else None

    if a.sequence:
        fs = sorted(glob.glob(a.sequence))
        if len(fs) < 2:
            sys.exit('need at least 2 frames')
        holds = [float(x) for x in a.holds.split(',')] if a.holds else [a.hold]*(len(fs)-1)
        tf = tw = 0
        for i in range(len(fs)-1):
            f, w = compare(fs[i], fs[i+1], holds[min(i, len(holds)-1)], spec)
            tf += f; tw += w
        print('\n%s   %d fail, %d warn across %d pairs\n'
              % ('REJECT' if tf else ('HOLD' if tw else 'ACCEPT'), tf, tw, len(fs)-1))
        return 1 if tf else 0

    if len(a.frames) != 2:
        sys.exit('give two frames, or --sequence')
    f, w = compare(a.frames[0], a.frames[1], a.hold, spec, a.expect_dx)
    print('\n%s   %d fail, %d warn\n' % ('REJECT' if f else ('HOLD' if w else 'ACCEPT'), f, w))
    return 1 if f else 0


if __name__ == '__main__':
    sys.exit(main())
