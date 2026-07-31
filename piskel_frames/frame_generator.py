"""
Crimson Moon Reveal - 160x80 pixel art, 8 frame cloud-parting sequence.

Every frame is built from ONE set of cloud puffs. Only the displacement of the
two front banks, the moon radius and the crimson light field change per frame,
so cloud shapes never jitter between frames.
"""
import numpy as np, random, math, json, base64, io
from PIL import Image
from scipy import ndimage

W, H = 160, 80
MOON_CX, MOON_CY = 80.0, 43.0

# ---------------------------------------------------------------- palette ---
# 16 blues (identical to frame 1's locked palette) + crimson ramp + the
# mauve transition tones that lit cloud edges need to land on.
PALETTE_HEX = [
    "080C1B", "0C1024", "161428", "131933", "17203C", "1C2646", "262B47",
    "222F53", "29355B", "2C3A62", "2F3E69", "384368", "364776", "445783",
    "4A5D8C", "4F6396",
    "2E0A1A", "4E0F27", "7A1533", "A81A3F", "D42350", "F03A66", "FF6B8A",
    "241A33", "3A2440", "55305B", "7A4570",
]
PALETTE = [tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) for h in PALETTE_HEX]

SKY_TOP, SKY_MID, SKY_LOW = (8, 11, 26), (12, 17, 38), (17, 24, 50)
CLOUD = [(16, 22, 45), (27, 36, 68), (41, 55, 96), (60, 79, 130), (88, 110, 165)]
CLOUD_BACK = [(13, 18, 37), (18, 25, 48), (24, 32, 60), (31, 41, 73), (38, 50, 86)]
SEAM, SEAM_WARM = (10, 13, 30), (26, 15, 34)

MOON_CORE = (232, 46, 88)
MOON_DEEP = (150, 24, 56)
MOON_EDGE = (108, 18, 44)
BLEED = (255, 120, 150)      # light forcing through a hairline crack
GLOW = (196, 32, 70)

BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6],
                  [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0

YY, XX = np.mgrid[0:H, 0:W]


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


SEAM_Y = 41.0

def top_edge(x):
    return (SEAM_Y - 4.0 + 4.0 * math.sin(x / 23.0 + 0.4)
            + 2.2 * math.sin(x / 7.5)
            - 3.0 * math.exp(-((x - 80) ** 2) / (2 * 34.0 ** 2)))

def bot_edge(x):
    return (SEAM_Y + 5.0 - 3.6 * math.sin(x / 19.0 + 2.1)
            - 2.0 * math.sin(x / 6.5 + 1.0)
            + 2.6 * math.exp(-((x - 80) ** 2) / (2 * 34.0 ** 2)))


BACK_TOP = puff_list(-12, W + 14, lambda x: 26 + 5 * math.sin(x / 26.0) + 3 * math.sin(x / 9.0), 5, 11, 7, 2.5, 101)
BACK_BOT = puff_list(-12, W + 14, lambda x: 58 - 4 * math.sin(x / 21.0 + 1.2) - 3 * math.sin(x / 8.0), 5, 11, 7, 2.5, 202)
FRONT_TOP = puff_list(-14, W + 16, top_edge, 6, 13, 8, 2.0, 303)
FRONT_BOT = puff_list(-14, W + 16, bot_edge, 6, 13, 8, 2.0, 404)


def displace(puffs, amp, sigma, direction, x_push):
    """Push a bank away from the seam. Vertical opening + horizontal retreat."""
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
    shade[mask] = np.clip(1.0 - depth[mask] / 26.0, 0, 1)

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
    for (sx, amp, sc) in [(0, 0.085, 6), (5, 0.05, 3), (9, 0.03, 2)]:
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
    """Split the banks along their true contact line - an organic hairline,
    not a rectangular cut."""
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
            continue                      # ragged taper at the crack's ends
        n = max(1, int(round(h)))
        y0 = c - (n - 1) // 2
        rows = list(range(y0, y0 + n))
        if prev is not None and abs(y0 - prev) > 1:      # bridge a stepped lip
            lo, hi = sorted((prev, y0))
            rows += list(range(lo, hi + 1))
        prev = y0
        for y in rows:
            if 0 <= y < H:
                top_m[y, x] = False
                bot_m[y, x] = False


def single_opening(top_m, bot_m):
    """Light may only come through THE crack. Pinholes elsewhere in the banks
    get sealed so nothing leaks where it shouldn't."""
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


# ------------------------------------------------------------ frame spec ----
# amp is calibrated per frame so the measured centre gap hits `gap_px`.
FRAMES = {
    1: dict(halo_stretch=1.0, gap_px=0,  sigma=12, x_push=0.0, moon_r=0.0,  glow=0.00, bloom=0.0, halo=0.00, crack_h=0.0, crack_s=1),
    2: dict(halo_stretch=2.4, gap_px=0,  sigma=13, x_push=0.0, moon_r=7.5,  glow=0.24, bloom=1.0, halo=0.66, crack_h=1.0, crack_s=16),
    3: dict(halo_stretch=1.8, gap_px=5,  sigma=19, x_push=0.6, moon_r=9.5,  glow=0.34, bloom=0.55, halo=0.56, crack_h=1.6, crack_s=26),
    4: dict(halo_stretch=1.45, crack_h=0.0, crack_s=1, gap_px=10, sigma=25, x_push=2.0, moon_r=11.5, glow=0.60, halo=0.60, bloom=0.30),
    5: dict(halo_stretch=1.2, crack_h=0.0, crack_s=1, gap_px=16, sigma=31, x_push=4.0, moon_r=13.5, glow=0.74, halo=0.74, bloom=0.18),
    6: dict(halo_stretch=1.05, crack_h=0.0, crack_s=1, gap_px=23, sigma=38, x_push=7.0, moon_r=16.0, glow=0.86, halo=0.86, bloom=0.10),
    7: dict(halo_stretch=1.0, crack_h=0.0, crack_s=1, gap_px=32, sigma=46, x_push=11.0, moon_r=19.0, glow=0.94, halo=0.94, bloom=0.05),
    8: dict(halo_stretch=1.0, crack_h=0.0, crack_s=1, gap_px=44, sigma=58, x_push=16.0, moon_r=22.0, glow=1.00, halo=1.00, bloom=0.00),
}


def measure_gap(amp, sigma, x_push):
    t = bank_mask(displace(FRONT_TOP, amp, sigma, -1, x_push), -1)
    b = bank_mask(displace(FRONT_BOT, amp, sigma, +1, x_push), +1)
    col = ~(t[:, 80] | b[:, 80])
    return int(col.sum())


def calibrate(gap_px, sigma, x_push):
    if gap_px <= 0:
        return 0.0
    lo, hi = 0.0, 40.0
    for _ in range(22):
        mid = (lo + hi) / 2
        if measure_gap(mid, sigma, x_push) < gap_px:
            lo = mid
        else:
            hi = mid
    return hi


# --------------------------------------------------------------- render -----
def render(frame):
    spec = FRAMES[frame]
    amp = calibrate(spec['gap_px'], spec['sigma'], spec['x_push'])
    img = np.zeros((H, W, 3), dtype=np.uint8)

    # sky
    for y in range(H):
        t = y / (H - 1)
        img[y, :] = lerp(SKY_TOP, SKY_MID, t / .5) if t < .5 else lerp(SKY_MID, SKY_LOW, (t - .5) / .5)

    # distant bank
    shade_bank(img, BACK_TOP, -1, CLOUD_BACK, 11)
    shade_bank(img, BACK_BOT, +1, CLOUD_BACK, 22)

    # ---- moon (behind the front banks, in front of the distant bank) ----
    r = spec['moon_r']
    if r > 0:
        st = spec['halo_stretch']
        dist = np.sqrt((XX - MOON_CX) ** 2 + ((YY - MOON_CY) * 1.0) ** 2)
        hdist = np.sqrt(((XX - MOON_CX) / st) ** 2 + ((YY - MOON_CY) * (1.0 + 0.35 * (st - 1))) ** 2)
        # halo bleeding into the surrounding sky/cloud
        halo = np.clip(1.0 - (hdist - r) / (r * 2.4), 0, 1) ** 2 * spec['halo']
        halo[dist <= r] = 0
        for y in range(H):
            for x in range(W):
                if halo[y, x] > 0.02:
                    img[y, x] = lerp(tuple(int(v) for v in img[y, x]), GLOW, float(halo[y, x]) * 0.75)
        # disc: darker toward the limb, a couple of banded "seas" for texture
        inside = dist <= r
        limb = np.clip(dist / max(r, 0.001), 0, 1)
        tone = 1.0 - 0.55 * limb ** 2
        band = (np.sin((YY - MOON_CY) * 0.9 + 0.6) > 0.72) | (np.sin((YY - MOON_CY) * 0.55 - 1.4) > 0.86)
        tone = np.where(band, tone - 0.16, tone)
        bay = np.tile(BAYER, (H // 4 + 1, W // 4 + 1))[:H, :W]
        tone = tone + (bay - 0.5) * 0.10
        for y in range(H):
            for x in range(W):
                if inside[y, x]:
                    t = float(np.clip(tone[y, x], 0, 1))
                    img[y, x] = lerp(MOON_EDGE, MOON_CORE, t) if t > 0.5 else lerp(MOON_EDGE, MOON_DEEP, t * 2)

    # ---- front banks ----
    top_p = displace(FRONT_TOP, amp, spec['sigma'], -1, spec['x_push'])
    bot_p = displace(FRONT_BOT, amp, spec['sigma'], +1, spec['x_push'])
    top_mask = bank_mask(top_p, -1)
    bot_mask = bank_mask(bot_p, +1)
    carve_crack(top_mask, bot_mask, spec['crack_h'], spec['crack_s'])
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
            continue          # this column has opened; no contact shadow
        warm = math.exp(-((x - 80) ** 2) / (2 * 22.0 ** 2))
        for k, strength in enumerate((0.92, 0.66, 0.38, 0.18)):
            y = edge + 1 + k
            if 0 <= y < H:
                tgt = lerp(SEAM, SEAM_WARM, warm * 0.6)
                s = strength * (0.78 if (x + y * 3) % 5 == 0 else 1.0)
                img[y, x] = lerp(tuple(int(v) for v in img[y, x]), tgt, s)
        if (x * 7 + int(top_edge(x))) % 3 != 0:
            img[edge, x] = lerp(tuple(int(v) for v in img[edge, x]), (34, 44, 78), 0.55)

    # ---- crimson light spilling from the gap onto the cloud edges ----
    if spec['glow'] > 0 and gap.any():
        moon_lit = gap & (np.sqrt((XX - MOON_CX) ** 2 + (YY - MOON_CY) ** 2) <= r + r * 1.6)
        src = moon_lit if moon_lit.any() else gap
        d = ndimage.distance_transform_edt(~src)
        falloff = 2.4 + 7.5 * spec['glow']
        light = np.exp(-d / falloff) * spec['glow']
        light[src] = 0
        light = light * cloud_mask
        for y in range(H):
            for x in range(W):
                l = float(light[y, x])
                if l > 0.03:
                    img[y, x] = lerp(tuple(int(v) for v in img[y, x]), GLOW, min(l * 1.05, 0.82))

        # hard rim: cloud pixels directly touching the opening catch the light
        edge_ring = cloud_mask & ndimage.binary_dilation(src, iterations=1)
        for y in range(H):
            for x in range(W):
                if edge_ring[y, x]:
                    img[y, x] = lerp(tuple(int(v) for v in img[y, x]), MOON_CORE, 0.55 + 0.35 * spec['glow'])

        # bloom: a thin crack blows out brighter than the disc itself
        if spec['bloom'] > 0:
            thin = src & (ndimage.distance_transform_edt(src) <= 1.6)
            for y in range(H):
                for x in range(W):
                    if thin[y, x]:
                        img[y, x] = lerp(tuple(int(v) for v in img[y, x]), BLEED, spec['bloom'])

    # ---- vignette ----
    v = np.clip((np.sqrt(((XX - 80) / 96.0) ** 2 + ((YY - 40) / 54.0) ** 2) - 0.55) / 0.75, 0, 1) * 0.42
    for y in range(H):
        for x in range(W):
            if v[y, x] > 0.02:
                img[y, x] = lerp(tuple(int(t) for t in img[y, x]), (6, 8, 20), float(v[y, x]))

    img = (img.astype(float) * 0.90 + np.array((5, 7, 18)) * 0.10).astype(np.uint8)
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
    frames = [int(a) for a in sys.argv[1:]] or [1, 2, 3]
    for f in frames:
        im = render(f)
        im.save(f'/home/claude/f{f}.png')
        im.resize((W * 5, H * 5), Image.NEAREST).save(f'/home/claude/f{f}_prev.png')
        print('frame', f, 'gap',
              measure_gap(calibrate(FRAMES[f]['gap_px'], FRAMES[f]['sigma'], FRAMES[f]['x_push']),
                          FRAMES[f]['sigma'], FRAMES[f]['x_push']))
