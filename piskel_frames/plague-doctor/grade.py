#!/usr/bin/env python3
"""
Shift the plate onto the Crimson Moon's TEMPERATURE ARC, and calm the sky's wash.

Why this exists
---------------
Measured against the moon's final frame, the generated plates sat on a
different red entirely:

    bright reds     moon  h 16.8 deg (crimson/rose)   plates  h 30.1 (scarlet)
    the shadows     moon  visible rose body          plates  near-neutral black

The lesson that cost a whole revision
-------------------------------------
The first version of this file corrected the AVERAGE hue and shipped. It hit the
target dead on -- 8.7 deg against the moon's 16.8 -- and the result was lifeless,
because an average is not a palette.

What a picture is actually made of is its arc: how hue travels as lightness
rises. Shadows sit cool, highlights sit warm, and the span between them is where
the life is. Both references have a long one; the first correction crushed it:

                     shadow   midtone   highlight    arc     warm chroma
    moon               327        9         17      +32        39.6%
    plates, as made    308       17         32      +70        61.0%
    v1, flat rotation  325        4          9      +44         0.7%   <-- dead

The flat rotation scaled with lightness, so it bit HARDEST at the brightest
pixels. That is hue shifting run backwards: it cooled the lamp flame, the beak
highlight and the fire on the keep -- every warm accent in the frame -- and left
one uniform pink. 62.3% of the picture's warm chroma went to 0.7%.

So the correction is a HUMP over the midtones, not a ramp. The ambient mass that
actually read as too warm gets the full shift; the two ends are left alone, and
the light sources are held back explicitly (see `ember`). Resonating with the
moon means sharing its arc, not landing on its mean -- and since the moon's
highlights only reach 17 deg, matching it exactly at the top would drain a scene
that contains real fire.

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

def temp_arc(L, shadow=-6.0, mid=-26.0, high=4.0):
    """Hue offset as a function of lightness -- a HUMP over the midtones, not a ramp.

    This is the whole correction, and the first version of this file got it
    backwards. It scaled the rotation by smoothstep(L, 15, 50), i.e. hardest at
    the brightest pixels, which is hue shifting run in reverse. Measured cost:
    the warm share of the picture's chroma went from 62.3% to 0.7%. The lamp
    flame, the beak highlight and the fire on the castle all live in hue 20-40,
    and every one of them was rotated out of existence.

    Both reference pictures obey the standard rule -- shadows cool, highlights
    warm -- and their hue climbs monotonically with lightness:

        L* band       moon    plague as generated
        deep shadow   327     308
        midtone         9      16
        highlight      17      31 .. 42
        total arc     +50     +94 degrees

    That arc IS the life in the picture. So the bulk of the sky, which is what
    actually read as too warm, gets the full correction, while the two ends are
    left to do their jobs: the shadows stay cool and the fire stays fire.

    Note the moon's own highlights only reach 17 deg, so matching it exactly at
    the top would drain a scene that contains real flame. Resonance is a shared
    arc, not a shared average.
    """
    w_lo = 1.0 - ss(L, 6., 20.)                         # deep shadow
    w_mid = ss(L, 10., 26.) * (1.0 - ss(L, 34., 52.))   # the ambient mass
    w_hi = ss(L, 46., 66.)                              # flame, embers, highlight
    tot = w_lo + w_mid + w_hi + 1e-6
    return (shadow * w_lo + mid * w_mid + high * w_hi) / tot


def cool(rgb, rot=-26.0, shadow=0.5, ember=1.0):
    """Shift the picture onto the moon's temperature arc and give the darks a
    violet body.

    rot     the midtone correction in degrees -- the depth of the hump. The two
            ends scale with it, so this stays the single temperature knob.
    shadow  how much blue-violet enters the deep darks, 0..1.
    ember   how firmly the hottest, most saturated pixels are held back from the
            correction, 0..1. These are the light SOURCES -- lamp flame, the fire
            on the keep -- and a light source keeps its own colour no matter what
            the ambient does. Without this the lamp cools with the sky and the
            picture loses the one warm thing in it.

    Gated on hue (reds only) and chroma (near-greys have no hue to rotate), but
    NOT on lightness any more -- the arc is the lightness term now.
    """
    L, C, H = to_lch(rgb)
    Hs = np.where(H > 180, H - 360, H)                  # unwrap around 0 deg
    gate = ss(-np.abs(Hs), -50., -30.) * ss(C, 10., 22.)

    scale = rot / -26.0                                 # one knob drives the arc
    off = temp_arc(L, shadow=-6.0 * scale, mid=rot, high=4.0 * scale)

    #  Protect the light sources: bright AND saturated together means emitter,
    #  not lit surface. Either alone is ordinary -- the sky is saturated, the
    #  beak highlight is bright -- so this has to be the product, not a sum.
    if ember > 0:
        keep = ss(L, 44., 62.) * ss(C, 55., 80.) * ember
        gate = gate * (1.0 - keep)

    out = from_lch(L, C, (H + off * gate) % 360)

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


def regrade(rgb, strength=0.5):
    """Blend the sky's blotchy low frequency toward one clean vertical ramp.

    At strength 1.0 this replaced the wash outright, and that went too far: the
    bright patch over the valley is not just blotchiness, it is the fire's glow,
    and flattening it removed a thing the picture was saying. Half strength
    keeps the glow while still pulling the worst of the mottling out.

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


def grade(rgb, rot=-26.0, shadow=0.5, sky=0.5):
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
    p.add_argument('--sky', type=float, default=0.5)
    a = p.parse_args()
    src = np.array(Image.open(a.src).convert('RGB')).astype(np.float32)
    out = grade(src, a.rot, a.shadow, a.sky)
    report('in  %s' % a.src, src)
    report('out %s' % a.dst, out)
    Image.fromarray(out.astype(np.uint8)).save(a.dst)
    print('  wrote %s' % a.dst)
