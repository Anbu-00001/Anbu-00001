#!/usr/bin/env python3
"""
Cool the plate onto the Crimson Moon's colour axis, and relay the sky's wash.

Why this exists
---------------
Measured against the moon's final frame, the generated plates sat on a
different red entirely:

    bright reds     moon  h 16.8 deg (crimson/rose)   plates  h 30.1 (scarlet)
    the shadows     moon  visible rose body          plates  near-neutral black

The two share their DARK reds almost exactly -- moon #4E0F27 against plate
#431529 -- and diverge only as the reds get brighter, where the plate's blue
channel collapses (B/R 0.61 -> 0.20) and the hue climbs into orange. So the
correction has to scale with lightness: a flat hue rotation would drag the
shadows somewhere neither picture goes.

Everything here runs on the full 1774x887 plate, BEFORE export.py's downsample,
so the grade is decided at full detail and the resampler only ever sees finished
colour.

Both operations preserve L* exactly -- they move hue and chroma only -- so the
lighting, the silhouette and every carved edge come through untouched.
"""
import numpy as np
import cv2


# ---------------------------------------------------------------- colour space

def to_lch(rgb):
    """float RGB 0..255 -> (L* 0..100, C*, h degrees). Float LAB, not uint8 LAB:
    the 8-bit round trip quantises a and b to 1/255 and that alone banded the sky."""
    f = (np.clip(rgb, 0, 255) / 255.).astype(np.float32)
    lab = cv2.cvtColor(f, cv2.COLOR_RGB2LAB)
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    return L, np.hypot(a, b), (np.degrees(np.arctan2(b, a)) + 360) % 360


def from_lch(L, C, H):
    a = C * np.cos(np.radians(H))
    b = C * np.sin(np.radians(H))
    lab = np.stack([L, a, b], -1).astype(np.float32)
    return np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB) * 255., 0, 255)


def ss(x, e0, e1):
    """Smoothstep. Every mask in here is soft -- a hard threshold on hue or
    chroma leaves a visible contour exactly where the grade changes strength."""
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------- grading

def cool(rgb, rot=-26.0, shadow=0.5):
    """Rotate the bright reds off scarlet toward the moon's crimson, and give the
    darks a violet body.

    rot     degrees of hue rotation at full strength. -17.5 lands on the moon
            exactly (h 16.5 against its 16.8); -26 carries past it into rose,
            which is what reads as 'cooler' rather than merely 'corrected'.
    shadow  how much blue-violet enters the deep darks, 0..1.

    The rotation is gated three ways -- on hue (reds only), on chroma (leave the
    near-greys, which carry no hue to rotate) and on lightness (leave the
    shadows, which already match). Rotating everything turns the lamp green.
    """
    L, C, H = to_lch(rgb)
    Hs = np.where(H > 180, H - 360, H)                  # unwrap around 0 deg
    amt = (ss(-np.abs(Hs), -50., -30.)                  # red family
           * ss(C, 10., 22.)                            # has real chroma
           * ss(L, 15., 50.))                           # and is bright
    out = from_lch(L, C, (H + rot * amt) % 360)

    if shadow > 0:
        L2, C2, H2 = to_lch(out)
        s = (1.0 - ss(L2, 4., 30.)) * shadow            # 1 in the deepest darks
        # shortest-arc rotation onto the violet axis, plus a chroma floor so the
        # darks stop being flat black and start reading as coloured shadow
        Hv = (H2 + ((290. - H2 + 540) % 360 - 180) * s * 0.55) % 360
        Cv = C2 + (np.maximum(C2, 9.5) - C2) * s
        out = from_lch(L2, Cv, Hv)
    return out


def sky_mask(rgb, blur=None):
    """The valley sky beyond the window frame: bright, red, right of the mullion,
    above the hills. Built from the picture's own colour rather than a fixed
    rectangle, so it follows the skyline instead of cutting across it."""
    L, C, H = to_lch(rgb)
    h, w = L.shape
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    box = ss(xs, w * 0.495, w * 0.545) * (1 - ss(ys, h * 0.80, h * 0.90))
    Hs = np.where(H > 180, H - 360, H)
    m = box * ss(C, 14., 30.) * ss(L, 8., 22.) * ss(-np.abs(Hs), -60., -40.)
    return cv2.GaussianBlur(m, (0, 0), blur if blur else max(3.0, w / 85.))[..., None]


def regrade(rgb, strength=1.0):
    """Replace the sky's blotchy low frequency with one clean vertical ramp.

    The generator left a hot patch in the upper left that no real sky has and the
    moon's own disc certainly doesn't. Split the sky into low frequency (the
    wash) and high (the cloud striations), fit a weighted quadratic in y to the
    wash -- weighted BY THE MASK, so the fit is driven only by sky pixels and
    never by the carriage -- then put the clouds back on top untouched.
    """
    f = np.clip(rgb, 0, 255).astype(np.float32)
    h, w = f.shape[:2]
    m = sky_mask(f)
    sig = max(8.0, w / 30.)
    lo = cv2.GaussianBlur(f, (0, 0), sig)
    hi = f - lo                                          # cloud detail, preserved

    yy = (np.mgrid[0:h, 0:w][0].astype(np.float32) / h)
    A = np.stack([np.ones_like(yy), yy, yy * yy], -1).reshape(-1, 3)
    W = m[..., 0].reshape(-1)
    ramp = np.empty_like(lo)
    for c in range(3):
        AtW = A.T * W
        coef = np.linalg.lstsq(AtW @ A, AtW @ lo[..., c].reshape(-1), rcond=None)[0]
        ramp[..., c] = (A @ coef).reshape(h, w)

    return np.clip(lo * (1 - m * strength) + ramp * (m * strength) + hi, 0, 255)


def grade(rgb, rot=-26.0, shadow=0.5, sky=1.0):
    """The whole pass, in the order the corrections depend on each other: cool
    first, then relay the sky -- the ramp must be fitted to the colours that will
    actually ship, not to the ones the grade is about to replace."""
    out = cool(rgb, rot=rot, shadow=shadow)
    if sky > 0:
        out = regrade(out, strength=sky)
    return out


# ------------------------------------------------------------------ measurement

def report(name, rgb):
    L, C, H = to_lch(np.asarray(rgb, dtype=np.float32))
    Hs = np.where(H > 180, H - 360, H)
    red = (np.abs(Hs) < 45) & (C > 18) & (L > 35)
    mh = float(np.average(Hs[red], weights=C[red])) % 360 if red.any() else float('nan')
    dark = L < 22
    print('  %-28s bright-red h %6.2f   dark C* %5.2f   mean L* %5.2f'
          % (name, mh, float(C[dark].mean()) if dark.any() else 0, float(L.mean())))


if __name__ == '__main__':
    import argparse
    from PIL import Image
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('src')
    p.add_argument('dst')
    p.add_argument('--rot', type=float, default=-26.0)
    p.add_argument('--shadow', type=float, default=0.5)
    p.add_argument('--sky', type=float, default=1.0)
    a = p.parse_args()
    src = np.array(Image.open(a.src).convert('RGB')).astype(np.float32)
    out = grade(src, a.rot, a.shadow, a.sky)
    report('in  %s' % a.src, src)
    report('out %s' % a.dst, out)
    Image.fromarray(out.astype(np.uint8)).save(a.dst)
    print('  wrote %s' % a.dst)
