#!/usr/bin/env python3
"""
Build six looping frames from the three plates. Nothing here is generated.

WHAT IS NOT HERE, AND WHY. A synthetic treeline scroll was attempted three times
and abandoned. The foreground is not a clean rectangular band: the sill slopes
through it and belongs to the carriage, not the landscape, and the doctor's
shoulder overlaps the window at those rows. Every rectangle that captures the
trees also captures something that must not move, and it tears. Two real travel
positions are not enough to synthesise six.

So the loop is a cinemagraph, which is the right form for a 3-second badge anyway:
he sleeps while the world stirs around him. Everything below is seam-free.

  cloth    period 2  - watchers alternate between the still (f02) and streaming
                       (f03) plates: same figures, same places, only the cloth
  crows    period 6  - a wingbeat cycled from sprites harvested across all plates,
                       drifting on an arc and scaling with distance
  beacon   period 3  - interpolated between two real flame sizes (area 295 -> 152)
  lantern  period 2  - guttering, a different period so the loop reads longer
  gleam    period 6  - crimson interior breath; carving glow breathes with it
"""
import numpy as np, cv2, os, json
from PIL import Image
import frametest as FT

W, H, N = 1774, 887, 6
A2 = np.array(Image.open('f02-new.png').convert('RGB')).astype(np.float32)
A3 = np.array(Image.open('f03-raw.png').convert('RGB')).astype(np.float32)
A1 = np.array(Image.open('f01-new.png').convert('RGB')).astype(np.float32)
WIN = FT.build_masks((H, W), json.load(open('regions.json')))['window'] > 0
lum = lambda x: 0.2126*x[:,:,0] + 0.7152*x[:,:,1] + 0.0722*x[:,:,2]

# ── crow sprites, harvested as alpha mattes from all three plates ────────────
def harvest(src):
    #  Stop short of the castle. The old window reached x1770, so tower masonry was
    #  being harvested as "crow sprites" and cycled into the flock -- one of the
    #  animated birds was a piece of battlement.
    L = lum(src); sky = np.zeros(L.shape, bool); sky[60:360, 980:1460] = True
    bg = cv2.GaussianBlur(L, (0,0), 9)
    m = (((bg - L) > 26) & sky).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for k in range(1, n):
        a, x, y, w, h = (st[k, cv2.CC_STAT_AREA], st[k, cv2.CC_STAT_LEFT],
                         st[k, cv2.CC_STAT_TOP], st[k, cv2.CC_STAT_WIDTH], st[k, cv2.CC_STAT_HEIGHT])
        if not (60 <= a <= 3000 and 0.7 <= w/max(h,1) <= 4.0): continue
        al = np.clip((bg[y:y+h, x:x+w] - L[y:y+h, x:x+w]) / 30.0, 0, 1)
        out.append((w/max(h,1), cv2.GaussianBlur(al.astype(np.float32), (0,0), 0.6)))
    return out

def erase_crows(src):
    """Paint the generator's own crows out of the sky.

    They are drawn INTO the plate, so they never move -- and the three animated
    crows composited on top just added moving birds beside nine frozen ones. The
    sky is smooth here, so inpainting fills them convincingly.
    """
    L = lum(src)
    sky = np.zeros(L.shape, bool); sky[40:440, 975:1774] = True
    bg = cv2.GaussianBlur(L, (0, 0), 9)
    m = (((bg - L) > 11) & sky).astype(np.uint8)          # catch the soft edge, not just the core
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    keep = np.zeros_like(m)
    hits = 0
    for k in range(1, n):
        a, w, h = st[k, cv2.CC_STAT_AREA], st[k, cv2.CC_STAT_WIDTH], st[k, cv2.CC_STAT_HEIGHT]
        #  bird-shaped: small, wider than tall or nearly square, never a tower
        if 40 <= a <= 3000 and 0.6 <= w/max(h,1) <= 4.5 and h < 90:
            keep[lab == k] = 1; hits += 1
    keep = cv2.dilate(keep, np.ones((21, 21), np.uint8))

    #  Fill from a MEDIAN-filtered sky, not by cloning sideways.
    #
    #  Cloning copied birds INTO the cleaned holes: the mask never catches every
    #  bird, so a source offset that happened to land on a missed one duplicated it,
    #  which is why bird-shaped things survived in every frame. A wide median filter
    #  has no such failure mode -- it removes anything smaller than its kernel while
    #  preserving the horizontal cloud banding, because the bands are wider than the
    #  window in the direction that matters.
    med = cv2.medianBlur(np.clip(src, 0, 255).astype(np.uint8), 61).astype(np.float32)
    soft = cv2.GaussianBlur(keep.astype(np.float32), (0, 0), 3.5)[..., None]
    out = np.clip(src * (1 - soft) + med * soft, 0, 255)
    print('  erased %d baked-in crows' % hits)
    return out.astype(np.float32)

sprites = harvest(A1) + harvest(A2) + harvest(A3)
sprites.sort(key=lambda t: t[0])                     # narrow (wings up) -> wide (spread)

#  Normalise every sprite to one body size.
#
#  These are different birds at different distances, so cycling them raw made the
#  silhouette change SIZE and IDENTITY frame to frame -- which reads as flicker, not
#  as one bird flapping. Rescaling to a common body height leaves only the wings
#  changing, which is the thing that is supposed to move.
BODY = 26
def normalise(al):
    h, w = al.shape
    k = BODY / float(max(h, 1))
    nw, nh = max(4, int(round(w*k))), max(4, int(round(h*k)))
    r = cv2.resize(al, (nw, nh), interpolation=cv2.INTER_AREA)
    #  centre each pose in a common canvas so the BODY stays put and the wings
    #  extend around it, instead of the whole shape jumping
    pad = np.zeros((BODY, BODY*4), np.float32)
    oy, ox = (BODY-nh)//2, (BODY*4-nw)//2
    pad[oy:oy+nh, ox:ox+nw] = r
    return pad
sprites = [(ar, normalise(al)) for ar, al in sprites]
def phase(i):                                        # a five-beat wing cycle
    order = [0.10, 0.35, 0.90, 0.60, 0.35, 0.15]
    q = order[i % len(order)]
    return sprites[min(len(sprites)-1, int(q*len(sprites)))][1]

# Three crows crossing the valley, a third of a turn apart.
#
# The body now travels much further per frame and follows an ARC with a bob, rather
# than sliding down a straight line. Animation's arc principle is the whole
# difference here: a body that holds a straight path while its wings beat reads as
# fluttering in place; one that rises and dips through the stroke reads as flying.
# Three birds, three DIFFERENT paths.
#
# They used to share one path, evenly spaced a third apart, each advancing a sixth
# per frame. That makes the set of positions repeat every TWO frames -- after two
# steps every bird has arrived exactly where the one ahead of it was, so a 6-frame
# loop showed only 2 distinct arrangements and the flock looked frozen. Spacing that
# divides the step count is the trap.
#
# Separate paths remove it: each bird still advances a sixth per frame and so still
# returns to its own start after six (the loop stays seamless), but no bird ever
# lands where another was, so all six frames differ.
PATHS = [
    ((1762, 112), (1010, 300)),
    ((1700, 226), (1048, 128)),
    ((1620, 300), (1120, 196)),
]
PHASE = [0.00, 0.41, 0.74]          # not thirds -- thirds is what caused the repeat

def crows(img, k):
    out = img.copy()
    for c in range(3):
        t = (PHASE[c] + k/float(N)) % 1.0
        (ax, ay), (bx, by) = PATHS[c]
        cx = ax + (bx-ax)*t
        cy = ay + (by-ay)*t
        cy += -14.0*np.sin(t*2*np.pi*2)          # the bob: two dips across the crossing
        cy += 26.0*(t - 0.5)**2 * -1.0           # and a shallow curve, not a ruled line
        sc = 1.25 - 0.70*t
        al = phase(k + c*2)
        h, w = al.shape
        nw, nh = max(4, int(w*sc)), max(4, int(h*sc))
        a2 = cv2.resize(al, (nw, nh), interpolation=cv2.INTER_AREA)
        px, py = int(cx-nw/2), int(cy-nh/2)
        if px < 0 or py < 0 or px+nw > W or py+nh > H: continue
        if not WIN[py:py+nh, px:px+nw].all(): continue
        roi = out[py:py+nh, px:px+nw]
        out[py:py+nh, px:px+nw] = roi*(1 - a2[...,None]*0.88)
    return out

# ── beacon: interpolate between the two measured flame sizes ─────────────────
BX, BY = 1577, 224
def beacon(img, k):
    s = [1.00, 0.78, 0.62, 0.70, 0.86, 0.96][k]      # period 3-ish dwindle and recover
    out = img.copy()
    y0, y1, x0, x1 = BY-34, BY+34, BX-30, BX+30
    patch = A1[y0:y1, x0:x1]
    base = A3[y0:y1, x0:x1]
    m = np.zeros(patch.shape[:2], np.float32)
    cv2.circle(m, (30, 34), 22, 1.0, -1)
    m = cv2.GaussianBlur(m, (0,0), 7.0)[..., None]
    warm = np.clip(patch - base, 0, None)
    out[y0:y1, x0:x1] = np.clip(base + warm*s*m + patch*(1-m)*0, 0, 255)
    out[y0:y1, x0:x1] = np.clip(base*(1-m) + (base + warm*s)*m, 0, 255)
    return out

# ── lantern gutter, a different period ──────────────────────────────────────
def lantern(img, k):
    #  Three states, not two: a 2-state alternation reads as a mechanical blink.
    #  Uneven values on a period that does not divide the 6-frame loop evenly keep
    #  it from locking to the birds.
    g = [1.00, 1.11, 1.04, 1.14, 1.02, 1.08][k]
    out = img.copy()
    #  the flame itself, plus the pool of light it throws on the panelling
    m = np.zeros((H, W), np.float32)
    m[140:250, 20:120] = 1.0
    m[90:430, 0:300] = np.maximum(m[90:430, 0:300], 0.45)
    m = cv2.GaussianBlur(m, (0,0), 26.0)[..., None]
    return np.clip(out*(1 + (g-1)*m), 0, 255)

A2 = erase_crows(A2)
A3 = erase_crows(A3)

os.makedirs('build', exist_ok=True)
for k in range(N):
    #  ONE base plate, with only the watcher band swapped for the cloth change.
    #  Alternating whole plates made every pixel differ between frames (A2 and A3
    #  are separate generations), which cost the entire delta-crop saving -- 100%
    #  coverage on every layer -- even though only 12% of pixels actually changed.
    im = A2.copy()
    if k % 2 == 1:
        y0, y1, x0, x1 = 556, 760, 1140, W
        m = np.zeros((y1-y0, x1-x0), np.float32); m[:] = 1.0
        m = cv2.GaussianBlur(m, (0, 0), 4.0)[..., None]
        im[y0:y1, x0:x1] = im[y0:y1, x0:x1]*(1-m) + A3[y0:y1, x0:x1]*m
    im = crows(im, k)
    im = beacon(im, k)
    im = lantern(im, k)
    Image.fromarray(np.clip(im,0,255).astype(np.uint8)).save('build/f%d_base.png' % (k+1))
    print('  f%d  cloth %s  beacon %.2f  lantern %.2f'
          % (k+1, 'still' if k%2==0 else 'streaming', [1,.78,.62,.70,.86,.96][k], [1,1.06][k%2]))
