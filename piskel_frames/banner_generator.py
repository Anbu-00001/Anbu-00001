"""
Crimson Moon Reveal - 256x128 banner sprite, 10 frame centre-parting sequence.

One cloud mass splits horizontally across the middle: the top bank draws upward,
the bottom bank downward, uncovering the disc from its midline outward. Every
frame is built from ONE set of puffs, so cloud shapes never jitter between
frames - only the displacement, the moon radius and the crimson light change.

Frame 10 is the resting frame and is held indefinitely, so the inscription zone
is stamped flat as the very last operation before quantisation: nothing in the
render pipeline can dirty it.
"""
import numpy as np, random, math, json, base64, io
from PIL import Image
from scipy import ndimage

W, H = 256, 128
MOON_CX, MOON_CY = 128.0, 64.0
SEAM_Y = 64.0

# ---- inscription zone: flat rectangle, both caption and number live here ----
BAND_W, BAND_H = 90, 28
BX0, BX1 = int(MOON_CX - BAND_W // 2), int(MOON_CX + BAND_W // 2)
BY0, BY1 = int(MOON_CY - BAND_H // 2), int(MOON_CY + BAND_H // 2)

# ---------------------------------------------------------------- palette ---
PALETTE_HEX = [
    "0C1024", "131933", "161428", "17203C", "222F53", "262B47", "29355B",
    "364776", "384368", "241A33", "3A2440", "55305B", "7A4570",
    "4E0F27", "7A1533", "A81A3F", "D42350",
    "2E0A1A",
]
PALETTE = [tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) for h in PALETTE_HEX]
HEX = {n: tuple(int(n[i:i + 2], 16) for i in (0, 2, 4)) for n in PALETTE_HEX}

SKY_TOP, SKY_MID, SKY_LOW = HEX["0C1024"], HEX["131933"], HEX["17203C"]
CLOUD = [HEX["161428"], HEX["17203C"], HEX["222F53"], HEX["29355B"], HEX["364776"]]
CLOUD_BACK = [HEX["0C1024"], HEX["131933"], HEX["161428"], HEX["17203C"], HEX["262B47"]]
SEAM, SEAM_WARM = HEX["0C1024"], HEX["2E0A1A"]

MOON_CORE = HEX["D42350"]
MOON_MID = HEX["A81A3F"]
MOON_DEEP = HEX["7A1533"]
MOON_EDGE = HEX["4E0F27"]
GLOW = HEX["A81A3F"]
BLEED = HEX["D42350"]        # brightest tone left in the palette
BAND_RGB = HEX["D42350"]     # constant across frames: no flicker under the text

STAR_TONES = [HEX["262B47"], HEX["29355B"], HEX["384368"]]

BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6],
                  [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0

YY, XX = np.mgrid[0:H, 0:W]
DIAG = {}


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


# ------------------------------------------------------------- geometry -----
def puff_list(x0, x1, baseline_fn, rmin, rmax, step, jitter, seed):
    r = random.Random(seed)
    puffs, x = [], x0
    while x < x1:
        rad = r.uniform(rmin, rmax)
        puffs.append((x, baseline_fn(x) + r.uniform(-jitter, jitter), rad))
        x += r.uniform(step * 0.6, step * 1.25)
    return puffs


def top_edge(x):
    return (SEAM_Y - 6.0 + 6.0 * math.sin(x / 37.0 + 0.4)
            + 3.5 * math.sin(x / 12.0)
            - 4.5 * math.exp(-((x - MOON_CX) ** 2) / (2 * 54.0 ** 2)))


def bot_edge(x):
    return (SEAM_Y + 7.0 - 5.5 * math.sin(x / 30.0 + 2.1)
            - 3.0 * math.sin(x / 10.0 + 1.0)
            + 4.0 * math.exp(-((x - MOON_CX) ** 2) / (2 * 54.0 ** 2)))


BACK_TOP = puff_list(-18, W + 22, lambda x: 34 + 8 * math.sin(x / 42.0) + 5 * math.sin(x / 14.0), 8, 17, 11, 4.0, 101)
BACK_BOT = puff_list(-18, W + 22, lambda x: 94 - 6 * math.sin(x / 34.0 + 1.2) - 5 * math.sin(x / 13.0), 8, 17, 11, 4.0, 202)
FRONT_TOP = puff_list(-22, W + 26, top_edge, 9, 20, 13, 3.2, 303)
FRONT_BOT = puff_list(-22, W + 26, bot_edge, 9, 20, 13, 3.2, 404)

# star field: fixed, drawn into the sky so it never re-rolls between frames
_sr = np.random.RandomState(1234)
STARS = []
for _ in range(150):
    sx = int(_sr.randint(0, W))
    sy = int(_sr.randint(0, H))
    bias = abs(sy - MOON_CY) / (H / 2)          # denser away from the seam
    if _sr.rand() < 0.25 + 0.75 * bias:
        STARS.append((sx, sy, STAR_TONES[_sr.randint(0, len(STAR_TONES))]))

# fixed nibble pattern for wispy lips - a column that frays keeps fraying
FRAY = np.random.RandomState(777).rand(2, W, 3)


def displace(puffs, amp, sigma, direction, x_push):
    out = []
    for (cx, cy, rad) in puffs:
        g = math.exp(-((cx - MOON_CX) ** 2) / (2 * sigma ** 2))
        dy = direction * amp * g
        dx = math.copysign(1.0, cx - MOON_CX) * x_push * g if x_push else 0.0
        out.append((cx + dx, cy + dy, rad))
    return out


def bank_mask(puffs, fill_dir):
    mask = np.zeros((H, W), dtype=bool)
    for (cx, cy, rad) in puffs:
        d = ((XX - cx) ** 2) / (rad * 1.15) ** 2 + ((YY - cy) ** 2) / (rad * 0.85) ** 2
        mask |= d <= 1.0
    for x in range(W):
        col = np.where(mask[:, x])[0]
        if len(col):
            if fill_dir < 0:
                mask[0:col.max() + 1, x] = True
            else:
                mask[col.min():H, x] = True
    return mask


def shade_bank(img, puffs, fill_dir, ramp, seed, mask=None):
    if mask is None:
        mask = bank_mask(puffs, fill_dir)

    depth = np.zeros((H, W), dtype=np.int32)
    run = np.zeros(W, dtype=np.int32)
    for y in range(H):
        run = np.where(mask[y], run + 1, 0)
        depth[y] = run
    shade = np.zeros((H, W))
    shade[mask] = np.clip(1.0 - depth[mask] / 42.0, 0, 1)

    body = np.zeros((H, W))
    rim = np.zeros((H, W))
    for i in sorted(range(len(puffs)), key=lambda i: puffs[i][1]):
        cx, cy, rad = puffs[i]
        nx, ny = (XX - cx) / (rad * 1.15), (YY - cy) / (rad * 0.85)
        d = np.sqrt(nx ** 2 + ny ** 2)
        inside = d <= 1.0
        lightv = np.clip(-ny * 0.85 - nx * 0.25, -1, 1)
        local = 0.5 + 0.5 * lightv
        body[inside] = local[inside]
        band = inside & (d > 0.72) & (lightv > 0.15)
        rim[band] = 1.0
        rim[inside & ~band] = 0.0

    val = np.zeros((H, W))
    val[mask] = 0.10 + 0.62 * body[mask] + 0.26 * shade[mask]
    val[rim > 0.5] += 0.34
    val = np.clip(val, 0, 1)

    noise = np.zeros((H, W))
    for (sx, amp, sc) in [(0, 0.085, 8), (5, 0.05, 4), (9, 0.03, 2)]:
        nr = np.random.RandomState(seed + sx)
        small = nr.rand(H // sc + 2, W // sc + 2)
        noise += (np.kron(small, np.ones((sc, sc)))[:H, :W] - 0.5) * 2 * amp
    val = np.clip(val + noise, 0, 1)

    levels = len(ramp) - 1
    bay = np.tile(BAYER, (H // 4 + 1, W // 4 + 1))[:H, :W]
    idx = np.clip(np.floor(val * levels + (bay - 0.5) * 0.62).astype(int), 0, levels)
    for l in range(levels + 1):
        sel = mask & (idx == l)
        img[sel] = ramp[l]
    return mask


def contact_line(top_m):
    out = np.full(W, -1, dtype=int)
    for x in range(W):
        col = np.where(top_m[:, x])[0]
        if len(col):
            out[x] = col.max()
    return out


def carve_crack(top_m, bot_m, crack_h, sigma_c, seed=5):
    if crack_h <= 0:
        return
    contact = contact_line(top_m)
    r = random.Random(seed)
    prev = None
    for x in range(W):
        c = contact[x]
        if c < 0:
            continue
        h = crack_h * math.exp(-((x - MOON_CX) ** 2) / (2 * sigma_c ** 2))
        if h < 0.35:
            continue
        if h < 0.75 and r.random() > (h - 0.35) / 0.40:
            continue
        n = max(1, int(round(h)))
        y0 = c - (n - 1) // 2
        rows = list(range(y0, y0 + n))
        if prev is not None and abs(y0 - prev) > 1:
            lo, hi = sorted((prev, y0))
            rows += list(range(lo, hi + 1))
        prev = y0
        for y in rows:
            if 0 <= y < H:
                top_m[y, x] = False
                bot_m[y, x] = False


def fray_lip(top_m, bot_m, amount, sigma):
    if amount <= 0:
        return
    for x in range(W):
        g = math.exp(-((x - MOON_CX) ** 2) / (2 * sigma ** 2))
        k = amount * g
        for b, (m, up) in enumerate(((top_m, True), (bot_m, False))):
            col = np.where(m[:, x])[0]
            if not len(col):
                continue
            lip = col.max() if up else col.min()
            for i in range(3):
                if FRAY[b, x, i] >= k * (0.68 ** i):
                    break
                y = lip - i if up else lip + i
                if 0 <= y < H:
                    m[y, x] = False


def single_opening(top_m, bot_m):
    gap = ~(top_m | bot_m)
    if not gap.any():
        return gap
    lab, n = ndimage.label(gap, structure=np.ones((3, 3)))
    if n > 1:
        d = (XX - MOON_CX) ** 2 + (YY - MOON_CY) ** 2
        keep = lab[np.unravel_index(np.where(gap, d, 1e9).argmin(), d.shape)]
        contact = contact_line(top_m | bot_m)
        for idx in range(1, n + 1):
            if idx == keep:
                continue
            ys, xs = np.where(lab == idx)
            for y, x in zip(ys, xs):
                if contact[x] >= 0 and y <= contact[x]:
                    top_m[y, x] = True
                else:
                    bot_m[y, x] = True
        gap = ~(top_m | bot_m)
    return gap


# ---------------------------------------------------------- calibration -----
def _banks(amp, sigma, x_push):
    return (bank_mask(displace(FRONT_TOP, amp, sigma, -1, x_push), -1),
            bank_mask(displace(FRONT_BOT, amp, sigma, +1, x_push), +1))


def visible_frac(amp, sigma, x_push, r):
    tm, bm = _banks(amp, sigma, x_push)
    disc = ((XX - MOON_CX) ** 2 + (YY - MOON_CY) ** 2) <= r * r
    return float((disc & ~(tm | bm)).sum()) / max(int(disc.sum()), 1)


def calibrate_visible(target, sigma, x_push, r):
    lo, hi = 0.0, 90.0
    for _ in range(26):
        mid = (lo + hi) / 2
        if visible_frac(mid, sigma, x_push, r) < target:
            lo = mid
        else:
            hi = mid
    return hi


def calibrate_clear(margin, sigma, x_push, r):
    """No cloud within `margin` px of the disc anywhere - the control that keeps
    working after `visible` has pinned at 100%."""
    return calibrate_visible(1.0, sigma, x_push, r + margin)


def measure_gap(amp, sigma, x_push):
    t, b = _banks(amp, sigma, x_push)
    return int((~(t[:, int(MOON_CX)] | b[:, int(MOON_CX)])).sum())


def calibrate_gap(gap_px, sigma, x_push):
    if gap_px <= 0:
        return 0.0
    lo, hi = 0.0, 60.0
    for _ in range(24):
        mid = (lo + hi) / 2
        if measure_gap(mid, sigma, x_push) < gap_px:
            lo = mid
        else:
            hi = mid
    return hi


# ------------------------------------------------------------ frame spec ----
FRAMES = {
    1:  dict(moon_r=0.0,  sigma=20, x_push=0.0,  gap_px=0, glow=0.00, halo=0.00,
             halo_stretch=1.0, bloom=0.0, crack_h=0.0, crack_s=1, fray=0.0),
    2:  dict(moon_r=30.0, sigma=22, x_push=0.0,  gap_px=0, glow=0.20, halo=0.30,
             halo_stretch=2.6, bloom=0.85, crack_h=1.0, crack_s=26, fray=0.0),
    3:  dict(moon_r=34.0, sigma=30, x_push=0.6,  gap_px=4, glow=0.32, halo=0.44,
             halo_stretch=2.0, bloom=0.55, crack_h=2.0, crack_s=42, fray=0.15, fray_s=40),
    4:  dict(moon_r=38.0, visible=0.17, sigma=40, x_push=2.0, glow=0.46, halo=0.52,
             halo_stretch=1.6, bloom=0.28, crack_h=0.0, crack_s=1, fray=0.35, fray_s=48,
             rim_s=44.0, bloom_off_disc=True),
    5:  dict(moon_r=42.0, visible=0.33, sigma=50, x_push=4.0, glow=0.58, halo=0.62,
             halo_stretch=1.35, bloom=0.16, crack_h=0.0, crack_s=1, fray=0.50, fray_s=58,
             rim_s=54.0, bloom_off_disc=True),
    6:  dict(moon_r=46.0, visible=0.51, sigma=60, x_push=6.5, glow=0.70, halo=0.72,
             halo_stretch=1.18, bloom=0.10, crack_h=0.0, crack_s=1, fray=0.65, fray_s=68,
             rim_s=66.0, bloom_off_disc=True),
    7:  dict(moon_r=49.0, visible=0.75, sigma=70, x_push=9.0, glow=0.80, halo=0.82,
             halo_stretch=1.08, bloom=0.06, crack_h=0.0, crack_s=1, fray=0.78, fray_s=78,
             rim_s=78.0, bloom_off_disc=True),
    8:  dict(moon_r=51.0, visible=0.97, sigma=80, x_push=12.0, glow=0.88, halo=0.90,
             halo_stretch=1.02, bloom=0.03, crack_h=0.0, crack_s=1, fray=0.88, fray_s=88,
             rim_s=90.0, bloom_off_disc=True),
    9:  dict(moon_r=53.0, clear=1.0, sigma=92, x_push=15.0, glow=0.95, halo=0.96,
             halo_stretch=1.0, bloom=0.0, crack_h=0.0, crack_s=1, fray=0.94, fray_s=98,
             rim_s=104.0, bloom_off_disc=True),
    10: dict(moon_r=55.0, clear=7.0, sigma=108, x_push=19.0, glow=1.00, halo=1.00,
             halo_stretch=1.0, bloom=0.0, crack_h=0.0, crack_s=1, fray=1.00, fray_s=110,
             rim_s=120.0, bloom_off_disc=True),
}


def amp_for(spec):
    if 'clear' in spec:
        return calibrate_clear(spec['clear'], spec['sigma'], spec['x_push'], spec['moon_r'])
    if 'visible' in spec:
        return calibrate_visible(spec['visible'], spec['sigma'], spec['x_push'], spec['moon_r'])
    return calibrate_gap(spec['gap_px'], spec['sigma'], spec['x_push'])


# --------------------------------------------------------------- render -----
def render(frame):
    spec = FRAMES[frame]
    amp = amp_for(spec)
    img = np.zeros((H, W, 3), dtype=np.uint8)

    # sky
    for y in range(H):
        t = y / (H - 1)
        img[y, :] = lerp(SKY_TOP, SKY_MID, t / .5) if t < .5 else lerp(SKY_MID, SKY_LOW, (t - .5) / .5)

    # stars, drawn into the sky so cloud simply covers them
    for (sx, sy, tone) in STARS:
        img[sy, sx] = tone

    shade_bank(img, BACK_TOP, -1, CLOUD_BACK, 11)
    shade_bank(img, BACK_BOT, +1, CLOUD_BACK, 22)

    # ---- moon ----
    moon_disc = np.zeros((H, W), dtype=bool)
    r = spec['moon_r']
    if r > 0:
        st = spec['halo_stretch']
        dist = np.sqrt((XX - MOON_CX) ** 2 + (YY - MOON_CY) ** 2)
        hdist = np.sqrt(((XX - MOON_CX) / st) ** 2 + ((YY - MOON_CY) * (1.0 + 0.35 * (st - 1))) ** 2)
        halo = np.clip(1.0 - (hdist - r) / (r * 2.0), 0, 1) ** 2 * spec['halo']
        halo[dist <= r] = 0
        for y in range(H):
            for x in range(W):
                if halo[y, x] > 0.02:
                    img[y, x] = lerp(tuple(int(v) for v in img[y, x]), GLOW, float(halo[y, x]) * 0.70)

        inside = dist <= r
        moon_disc = inside
        limb = np.clip(dist / max(r, 0.001), 0, 1)
        tone = 1.0 - 0.55 * limb ** 2
        band = (np.sin((YY - MOON_CY) * 0.55 + 0.6) > 0.80) | (np.sin((YY - MOON_CY) * 0.33 - 1.4) > 0.90)
        tone = np.where(band, tone - 0.13, tone)
        bay = np.tile(BAYER, (H // 4 + 1, W // 4 + 1))[:H, :W]
        tone = tone + (bay - 0.5) * 0.10
        for y in range(H):
            for x in range(W):
                if inside[y, x]:
                    t = float(np.clip(tone[y, x], 0, 1))
                    if t > 0.66:
                        img[y, x] = lerp(MOON_MID, MOON_CORE, (t - 0.66) / 0.34)
                    elif t > 0.33:
                        img[y, x] = lerp(MOON_DEEP, MOON_MID, (t - 0.33) / 0.33)
                    else:
                        img[y, x] = lerp(MOON_EDGE, MOON_DEEP, t / 0.33)

    # ---- front banks ----
    top_p = displace(FRONT_TOP, amp, spec['sigma'], -1, spec['x_push'])
    bot_p = displace(FRONT_BOT, amp, spec['sigma'], +1, spec['x_push'])
    top_mask = bank_mask(top_p, -1)
    bot_mask = bank_mask(bot_p, +1)
    carve_crack(top_mask, bot_mask, spec['crack_h'], spec['crack_s'])
    fray_lip(top_mask, bot_mask, spec.get('fray', 0.0), spec.get('fray_s', 40.0))
    gap = single_opening(top_mask, bot_mask)
    shade_bank(img, bot_p, +1, CLOUD, 44, mask=bot_mask)
    shade_bank(img, top_p, -1, CLOUD, 33, mask=top_mask)
    cloud_mask = top_mask | bot_mask

    # ---- seam shadow where the banks still press together ----
    for x in range(W):
        col = np.where(top_mask[:, x])[0]
        if not len(col):
            continue
        edge = col.max()
        if gap[min(edge + 1, H - 1), x]:
            continue
        warm = math.exp(-((x - MOON_CX) ** 2) / (2 * 34.0 ** 2))
        for k, strength in enumerate((0.92, 0.66, 0.38, 0.18)):
            y = edge + 1 + k
            if 0 <= y < H:
                tgt = lerp(SEAM, SEAM_WARM, warm * 0.6)
                s = strength * (0.78 if (x + y * 3) % 5 == 0 else 1.0)
                img[y, x] = lerp(tuple(int(v) for v in img[y, x]), tgt, s)

    # ---- crimson light spilling from the opening onto cloud edges ----
    if spec['glow'] > 0 and gap.any():
        moon_lit = gap & (np.sqrt((XX - MOON_CX) ** 2 + (YY - MOON_CY) ** 2) <= r + r * 1.6)
        src = moon_lit if moon_lit.any() else gap
        d = ndimage.distance_transform_edt(~src)
        falloff = 3.6 + 11.0 * spec['glow']
        light = np.exp(-d / falloff) * spec['glow']
        light[src] = 0
        light = light * cloud_mask
        for y in range(H):
            for x in range(W):
                l = float(light[y, x])
                if l > 0.03:
                    img[y, x] = lerp(tuple(int(v) for v in img[y, x]), GLOW, min(l * 1.05, 0.82))

        edge_ring = cloud_mask & ndimage.binary_dilation(src, iterations=1)
        rim_s = spec.get('rim_s')
        base_rim = 0.55 + 0.35 * spec['glow']
        for y in range(H):
            for x in range(W):
                if edge_ring[y, x]:
                    w = 1.0 if rim_s is None else \
                        0.30 + 0.70 * math.exp(-((x - MOON_CX) ** 2) / (2 * rim_s ** 2))
                    img[y, x] = lerp(tuple(int(v) for v in img[y, x]), MOON_CORE, base_rim * w)

        if spec['bloom'] > 0:
            thin = src & (ndimage.distance_transform_edt(src) <= 1.6)
            if spec.get('bloom_off_disc'):
                thin &= ~moon_disc
            for y in range(H):
                for x in range(W):
                    if thin[y, x]:
                        img[y, x] = lerp(tuple(int(v) for v in img[y, x]), BLEED, spec['bloom'])

    # ---- vignette ----
    v = np.clip((np.sqrt(((XX - MOON_CX) / 154.0) ** 2 + ((YY - MOON_CY) / 86.0) ** 2) - 0.60) / 0.75, 0, 1) * 0.40
    for y in range(H):
        for x in range(W):
            if v[y, x] > 0.02:
                img[y, x] = lerp(tuple(int(t) for t in img[y, x]), SKY_TOP, float(v[y, x]))

    # ---- inscription zone, stamped LAST so nothing above can dirty it ----
    band = np.zeros((H, W), dtype=bool)
    band[BY0:BY1, BX0:BX1] = True
    band_lit = band & moon_disc & ~cloud_mask
    img[band_lit] = BAND_RGB

    DIAG['disc_px'] = int(moon_disc.sum())
    DIAG['visible'] = (int((moon_disc & ~cloud_mask).sum()) / DIAG['disc_px']) if DIAG['disc_px'] else 0.0
    DIAG['band_clear'] = float(band_lit.sum()) / (BAND_W * BAND_H)
    DIAG['band_cloud'] = int((band & cloud_mask).sum())
    DIAG['cover'] = float(cloud_mask.mean())
    DIAG['amp'] = amp

    return quantize(Image.fromarray(img, 'RGB'))


# ------------------------------------------------------------- quantize -----
_pal_img = Image.new('P', (1, 1))
_flat = [c for rgb in PALETTE for c in rgb]
_flat += [0, 0, 0] * (256 - len(PALETTE))
_pal_img.putpalette(_flat)


def quantize(im):
    return im.quantize(palette=_pal_img, dither=Image.Dither.NONE).convert('RGB')


if __name__ == '__main__':
    import sys
    for f in ([int(a) for a in sys.argv[1:]] or list(range(1, 11))):
        im = render(f)
        im.save(f'/home/claude/work/b{f:02d}.png')
        print('frame %02d  amp %5.1f  visible %5.1f%%  band clear %5.1f%%  cover %5.1f%%'
              % (f, DIAG['amp'], 100 * DIAG['visible'], 100 * DIAG['band_clear'], 100 * DIAG['cover']))
