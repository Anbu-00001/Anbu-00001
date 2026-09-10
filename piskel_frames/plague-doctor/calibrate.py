#!/usr/bin/env python3
"""
calibrate — the gate. Scores a frame out of 100 against its predecessor.

    DO NOT MOVE TO THE NEXT FRAME UNTIL THE CURRENT ONE SCORES >= 95.

Design honesty, up front
------------------------
A weighted sum of arbitrary checks is a number that FEELS rigorous. This one is
not arbitrary in two specific ways:

  1. Every scoring curve is anchored to MEASURED endpoints from the calibration
     in TESTING.md -- a synthetic ground-truth translation (the best a real frame
     can be) and an independent regeneration (the failure we must catch). A curve
     maps the good case to 1.0 and the bad case to 0.0. Nothing is guessed.

  2. Category weights reflect what ACTUALLY broke this sequence, counted:
     forest redrawn instead of moved (~every frame), travel direction reversed
     (4 times), exposure overshoot (3 times), interior redrawn (~every frame),
     colour drift (missed entirely by a luminance-only checker), owl drifting
     toward the frame edge (once, nearly fatal).

It reuses frametest.py's functions directly rather than reimplementing them, and
reads sequence.json so the act structure, hold times and travel budget come from
SCRIPT.md's plan instead of being hardcoded here.

What it does NOT measure
------------------------
Staging, timing, drama, whether the frame is any good. A perfectly coherent
sequence of boring frames scores 100. This gates CONTINUITY only.

Usage
    calibrate.py --baseline f01.png              # first frame: absolute checks
    calibrate.py f01.png f02.png                 # scored against predecessor
    calibrate.py --sequence 'f*.png'             # every consecutive pair
"""
import argparse, glob, json, os, re, sys
import numpy as np
import cv2
from PIL import Image

import frametest as FT     # register / phase_shift / residual / build_masks / read

BAR = 95.0

# ── scoring curves ───────────────────────────────────────────────────────────
# Endpoints measured in TESTING.md. lo -> 0.0, hi -> 1.0, clamped, so a frame as
# good as a ground-truth translation scores ~1.0 on every axis.
CURVES = {
    #                  bad    good      measured basis
    'inliers':        (0.60,  0.95),   # redraw 0.543 | translation 0.978
    'flip':           (0.120, 0.010),  # redraw 0.1704 | translation 0.0035
    'ssim':           (0.700, 0.990),  # redraw 0.6313 | translation 0.9988
    'de':             (4.000, 0.300),  # redraw 6.079 | translation 0.075
}

WEIGHTS = {
    'registration': 30,   # does a rigid transform explain the change at all
    'residual':     25,   # what changed BEYOND the motion
    'travel':       15,   # direction, magnitude, growth
    'exposure':     15,   # luminance continuity within the act's budget
    'colour':       10,   # saturation / channel drift
    'invariants':    5,   # canvas, clipping, owl clearance, cold-pixel sanity
}


def ramp(v, lo, hi):
    """Map v from lo->0 .. hi->1, clamped. Works in either direction."""
    if hi == lo:
        return 1.0
    return float(np.clip((v - lo) / (hi - lo), 0.0, 1.0))


def anchor_ncc(B, R, box, sigma=3.0):
    """High-pass NCC of one art-lock feature against the reference.

    High-pass, not raw pixels, so a frame that is merely lit differently from the
    reference still scores high -- what is being asked is "is the carving still
    incised here", not "does this look like the reference"."""
    y0, y1, x0, x1 = box
    def hp(x):
        g = cv2.cvtColor(x.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
        d = g - cv2.GaussianBlur(g, (0, 0), sigma)
        return d[y0:y1, x0:x1]
    a, b = hp(R), hp(B)
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / max(np.sqrt((a * a).sum() * (b * b).sum()), 1e-9))


def hsv_sat(x):
    """HSV saturation (max-min)/max -- invariant to a pure exposure gain."""
    x = x.astype(np.float32)
    mx, mn = x.max(2), x.min(2)
    return np.where(mx > 1.0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)


def tol_score(d, tol, dead=0.35):
    """Deviation scoring with a flat top. Within dead*tol of zero it is perfect;
    beyond that it ramps to zero at tol. A linear-from-zero ramp punished a 0.6%
    deviation with an 8-point loss, which made 100 unreachable for good frames."""
    ad = abs(d)
    if ad <= dead * tol:
        return 1.0
    return float(np.clip((tol - ad) / max(tol * (1 - dead), 1e-9), 0.0, 1.0))


def lum(a):
    return 0.2126 * a[:, :, 0] + 0.7152 * a[:, :, 1] + 0.0722 * a[:, :, 2]


def cold_blobs(a):
    # a is uint8: promote BEFORE the addition or 230+40 wraps to 14 and bright
    # warm pixels register as cold. This bug scored the lantern flame as owl eyes.
    a = a.astype(np.int16)
    m = ((a[:, :, 2] > a[:, :, 0] + 40) & (a[:, :, 2] > 120)).astype(np.uint8)
    if m.sum() == 0:
        return 0, None, 0
    n, _ = cv2.connectedComponents(m)
    ys, xs = np.nonzero(m)
    return n - 1, (xs.mean(), ys.mean()), int(m.sum())


def act_of(stem, cfg):
    for name, a in cfg['acts'].items():
        if stem in a['frames']:
            return name, a
    return 'unknown', {'may_brighten': False}


def bar(frac, width=22):
    n = int(round(frac * width))
    return '#' * n + '.' * (width - n)


# ── plate (a targeted edit, not a motion frame) ──────────────────────────────
def score_plate(master, plate, box, cfg):
    """A PLATE is not a frame in the sequence -- it is the master with ONE thing
    deliberately changed. Registration, travel and growth are meaningless for it.
    The only question is: does it differ ONLY where it is allowed to?"""
    A, B = FT.read(master), FT.read(plate)
    rows, pts, tot = [], 0.0, 0.0

    def add(label, q, detail, weight):
        nonlocal pts, tot
        pts += weight * q; tot += weight
        rows.append((label, q, detail))

    if A.shape != B.shape:
        return 0.0, [('canvas', 0.0, 'shape mismatch')]

    d = np.abs(A.astype(float) - B.astype(float)).mean(2)
    y0, y1, x0, x1 = box
    allowed = np.zeros(d.shape, bool); allowed[y0:y1, x0:x1] = True

    # Outside the allowed box nothing may differ at all.
    out = d[~allowed]
    q = 1.0 if out.max() < 0.5 else float(np.clip(1 - out.mean() / 2.0, 0.0, 1.0))
    add('untouched area intact', q,
        'max diff %.3f, mean %.4f outside the box' % (out.max(), out.mean()), 45)

    # Inside it, something had better have actually changed.
    ins = d[allowed]
    q = float(np.clip(ins.max() / 20.0, 0.0, 1.0))
    add('edit actually happened', q, 'max diff %.1f inside the box' % ins.max(), 20)

    # Exposure must not have drifted anywhere.
    for nm, sl in {'whole': slice(None), 'interior': slice(0, int(A.shape[1]*.52))}.items():
        la, lb = lum(A[:, sl].astype(float)), lum(B[:, sl].astype(float))
        dv = (lb.mean() - la.mean()) / max(la.mean(), 1e-6)
        q = tol_score(dv, 0.03)
        add('exposure %s' % nm, q, '%+.2f%% (tol +-3%%)' % (dv * 100), 15)

    n, _, _ = cold_blobs(B)
    add('owl eyes intact', 1.0 if n == 2 else 0.0, '%d cold blob(s)' % n, 5)
    return pts / tot * 100.0, rows


# ── baseline (no predecessor) ────────────────────────────────────────────────
def score_baseline(path, cfg):
    A = FT.read(path)
    t = cfg['baseline_targets']
    h, w = A.shape[:2]
    L = lum(A.astype(float))
    rows, pts, tot = [], 0.0, 0.0

    def add(label, ok, detail, weight):
        nonlocal pts, tot
        pts += weight * (1.0 if ok else 0.0); tot += weight
        rows.append((label, 1.0 if ok else 0.0, detail))

    add('canvas', [w, h] == cfg['canvas'], '%dx%d' % (w, h), 20)
    add('aspect 2:1', abs(w / h - 2) < 0.002, '%.5f' % (w / h), 10)

    masks = FT.build_masks(A.shape, json.load(open(cfg['regions'])))
    g = cv2.cvtColor(A, cv2.COLOR_RGB2GRAY)
    for nm, mk in masks.items():
        k = len(cv2.ORB_create(6000).detect(g, mk))
        add('ORB %s' % nm, k >= t['min_orb_per_region'], '%d keypoints' % k, 15)

    blk = (L < 1).mean() * 100
    add('black not crushed', blk <= t['max_pure_black_pct'], '%.2f%% pure black' % blk, 15)
    wht = (L > 250).mean() * 100
    add('no blowout', wht <= t['max_blown_white_pct'], '%.4f%% blown' % wht, 10)

    li = lum(A[:, :int(w * .52)].astype(float)).mean()
    lw = lum(A[:, int(w * .54):].astype(float)).mean()
    add('light balance', (li > lw) == t['interior_brighter_than_window'],
        'interior %.2f vs window %.2f' % (li, lw), 10)

    n, c, npx = cold_blobs(A)
    add('cold pixels', n == t['cold_blobs_expected'],
        '%d blob(s), %d px' % (n, npx), 5)
    return pts / tot * 100.0, rows


# ── pair scoring ─────────────────────────────────────────────────────────────
def score_pair(pa, pb, cfg):
    A, B = FT.read(pa), FT.read(pb)
    if A.shape != B.shape:
        return 0.0, [('canvas', 0.0, 'shape %s vs %s' % (A.shape, B.shape))], {}

    stem = os.path.splitext(os.path.basename(pa))[0]
    stem = re.match(r'(f\d+)', stem).group(1) if re.match(r'(f\d+)', stem) else stem
    hold = cfg['holds'].get(stem, 0.5)
    # The act is that of the DESTINATION frame: f06 -> f07 crosses from the jolt
    # into the emergence, and it is f07 that is allowed to gain light.
    dst = os.path.splitext(os.path.basename(pb))[0]
    dst = re.match(r'(f\d+)', dst).group(1) if re.match(r'(f\d+)', dst) else dst
    act_name, act = act_of(dst, cfg)

    masks = FT.build_masks(A.shape, json.load(open(cfg['regions'])))
    h, w = A.shape[:2]
    is_cut = bool(cfg.get('cuts', {}).get(stem, False))
    stem_b = os.path.splitext(os.path.basename(pb))[0]
    mb = re.match(r'(f\d+)', stem_b)
    stem_b = mb.group(1) if mb else stem_b
    cat, rows, info = {}, [], {'act': act_name, 'hold': hold}

    # ── registration + residual, per region, worst region governs ────────────
    reg_q, res_q = [], []
    for nm, mk in masks.items():
        # Across a cut the window content legitimately differs; only the interior
        # must still register.
        if is_cut and nm == 'window':
            rows.append(('registration window', 1.0, 'EXEMPT — deliberate cut'))
            reg_q.append(1.0); res_q.append(1.0)
            continue
        M, inl, nmatch = FT.register(A, B, mk)
        if M is None:
            reg_q.append(0.0); res_q.append(0.0)
            rows.append(('registration %s' % nm, 0.0, 'failed (%d matches)' % nmatch))
            continue
        q = ramp(inl, *CURVES['inliers'])
        reg_q.append(q)
        rows.append(('registration %s' % nm, q,
                     'inliers %.3f of %d matches' % (inl, nmatch)))
        if nm == 'window':
            info['M'] = M

        Aw = cv2.warpAffine(A, M, (w, h), flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_REPLICATE)
        r = FT.residual(Aw, B, mk)
        if r is None:
            continue
        f, s, de = r
        qs = [ramp(f, *CURVES['flip']), ramp(s, *CURVES['ssim']), ramp(de, *CURVES['de'])]
        res_q.append(float(np.mean(qs)))
        rows.append(('residual %s' % nm, float(np.mean(qs)),
                     'FLIP %.4f  SSIM %.4f  dE %.3f' % (f, s, de)))
    cat['registration'] = min(reg_q) if reg_q else 0.0
    cat['residual'] = min(res_q) if res_q else 0.0

    # ── travel: direction, budget, growth (owl eyes are the tracker) ─────────
    # Across a deliberate cut the world may have moved arbitrarily far; only the
    # DIRECTION still has to make sense.
    is_cut = bool(cfg.get('cuts', {}).get(stem, False))
    tq = []
    ca, cb = cold_blobs(A)[1], cold_blobs(B)[1]
    tv = cfg['travel']
    budget = tv['near_pct_per_0p9s'] * tv['window_width_px'] * (hold / 0.9) * tv['owl_fraction_of_near']
    if ca and cb:
        dx, dy = cb[0] - ca[0], cb[1] - ca[1]
        info['owl_dx'], info['owl_dy'] = dx, dy
        q = 1.0 if dx <= 1.0 else 0.0
        tq.append(q); rows.append(('travel direction', q, 'owl dx %+.1f px (must be <= 0)' % dx))
        if is_cut:
            rows.append(('travel magnitude', 1.0,
                         'dx %.1f px — EXEMPT, f06->f07 is a deliberate cut' % abs(dx)))
            tq.append(1.0)
        else:
            q = ramp(-abs(abs(dx) - budget) + budget, 0.0, budget) if budget > 0 else 1.0
            tq.append(q); rows.append(('travel magnitude', q,
                                       'dx %.1f px vs %.1f budget (%.2fs hold)' % (abs(dx), budget, hold)))
        if is_cut:
            tq.append(1.0); rows.append(('travel down-component', 1.0,
                                         'owl dy %+.1f px — EXEMPT across a cut' % dy))
        else:
            q = 1.0 if dy >= -1.5 else 0.0
            tq.append(q); rows.append(('travel down-component', q, 'owl dy %+.1f px' % dy))
        room = cb[0] - cfg['window_post_x']
        q = ramp(room, 60, 160)
        tq.append(q); rows.append(('owl clearance', q, '%.0f px before the window post' % room))
    else:
        owl_gone = stem >= cfg.get('owl_present_through', 'f99')
        if owl_gone and 'M' in info:
            dx = float(info['M'][0, 2])
            q = 1.0 if dx <= 1.0 else 0.0
            tq.append(q)
            rows.append(('travel direction', q,
                         'dx %+.1f px from registration (owl gone, tracker fallback)' % dx))
        elif owl_gone:
            tq.append(1.0)
            rows.append(('travel', 1.0, 'owl gone with the forest — tracker retired'))
        else:
            tq.append(0.0)
            rows.append(('travel', 0.0, 'owl eyes not found but should still be present'))
    if 'M' in info:
        sc = float(np.hypot(info['M'][0, 0], info['M'][1, 0]))
        q = 1.0 if sc >= 0.999 else ramp(sc, 0.985, 0.999)
        tq.append(q); rows.append(('growth (scale >= 1)', q, 'scale %.4f' % sc))
    cat['travel'] = float(np.mean(tq))

    # ── exposure ─────────────────────────────────────────────────────────────
    tol = 0.25 if act['may_brighten'] else 0.08
    eq = []
    whole = np.ones(A.shape[:2], bool)
    bands = {'whole': whole,
             'interior': masks['interior'].astype(bool),
             'window': masks['window'].astype(bool)}
    for nm, mk in bands.items():
        la, lb = lum(A.astype(float))[mk], lum(B.astype(float))[mk]
        d = (lb.mean() - la.mean()) / max(la.mean(), 1e-6)
        plan = cfg.get('window_luma_plan', {}).get(stem_b)
        if nm == 'window' and plan is not None:
            #  Measure against the declared ramp, not against the previous frame.
            #  A delta budget lets every frame redefine its own ceiling; that is
            #  how f07 drifted +49% and nothing caught it.
            ptol = cfg.get('window_luma_tol', 0.15)
            e = (lb.mean() - plan) / plan
            q = tol_score(e, ptol)
            eq.append(q)
            rows.append(('exposure window', q, 'luma %.2f vs planned %.2f (%+.1f%%, tol +-%.0f%%)'
                         % (lb.mean(), plan, e * 100, ptol * 100)))
            continue
        q = tol_score(d, tol)
        if act['may_brighten'] and d > 0:
            q = 1.0 if d <= tol else tol_score(d - tol, tol)
        eq.append(q)
        rows.append(('exposure %s' % nm, q, '%+.1f%% (tol +-%.0f%%)' % (d * 100, tol * 100)))
    cat['exposure'] = float(np.mean(eq))

    # ── colour ───────────────────────────────────────────────────────────────
    #  HSV saturation (max-min)/max, NOT raw chroma (max-min).  Raw chroma scales
    #  linearly with exposure: a pure 1.5x gain on f07's window -- which changes
    #  no hue whatsoever -- moves it +49.6%, five times past a +-10% tolerance,
    #  while HSV S moves +7.7% and then stays flat.  The locked reference sits at
    #  chroma 61.0 against f07's 14.3, so the raw-chroma rule forbids the piece
    #  from ever reaching its own approved ending.  It was measuring light.
    sat_tol = 0.25 if act['may_brighten'] else 0.10
    cq = []
    for nm in ('interior', 'window'):
        mk = masks[nm].astype(bool)
        sa, sb = hsv_sat(A)[mk].mean(), hsv_sat(B)[mk].mean()
        d = (sb - sa) / max(sa, 1e-6)
        q = tol_score(d, sat_tol)
        cq.append(q)
        rows.append(('saturation %s' % nm, q,
                     'S %.3f -> %.3f (%+.1f%%, tol +-%.0f%%)'
                     % (sa, sb, d * 100, sat_tol * 100)))
    cat['colour'] = float(np.mean(cq))

    # ── invariants ───────────────────────────────────────────────────────────
    iq = []
    n, _, _ = cold_blobs(B)
    if stem >= cfg.get('owl_present_through', 'f99'):
        iq.append(1.0)
        rows.append(('owl eyes', 1.0, '%d cold blob(s) — owl left behind, not required' % n))
    else:
        q = 1.0 if n == cfg['baseline_targets']['cold_blobs_expected'] else 0.0
        iq.append(q); rows.append(('owl eyes intact', q, '%d cold blob(s)' % n))
    # Absolute black level is the art's business (f01 is legitimately 14%).
    # What matters between frames is whether it gets WORSE.
    ba = (lum(A.astype(float)) < 1).mean() * 100
    bb = (lum(B.astype(float)) < 1).mean() * 100
    q = 1.0 if bb <= ba + 1.0 else float(np.clip(1 - (bb - ba - 1.0) / 5.0, 0.0, 1.0))
    iq.append(q); rows.append(('black not worse', q, '%.2f%% -> %.2f%% pure black' % (ba, bb)))
    cat['invariants'] = float(np.mean(iq))

    #  Fidelity to the art lock.  Continuity scoring cannot see this: a feature
    #  dropped at f01 is consistent with every frame that follows it.
    failed = []
    anchors = {k: v for k, v in cfg.get('anchors', {}).items() if not k.startswith('_')}
    if anchors:
        R = FT.read(cfg.get('reference', 'reference.png'))
        for nm, spec in anchors.items():
            v = anchor_ncc(B, R, spec['box'])
            ok = v >= spec['min_ncc']
            if not ok:
                failed.append(nm)
            rows.append(('anchor %s' % nm, 1.0 if ok else 0.0,
                         'NCC %.3f vs reference (floor %.2f)%s'
                         % (v, spec['min_ncc'], '' if ok else '  -- ART LOCK FEATURE MISSING')))

    total = sum(WEIGHTS[k] * cat[k] for k in WEIGHTS)
    return total, rows, {**info, 'cat': cat, 'anchor_failed': failed}


def report(title, total, rows, info=None):
    print('\n' + '=' * 66)
    print(title)
    if info and 'act' in info:
        print('  act %s   hold %.2fs' % (info['act'], info['hold']))
    print('=' * 66)
    for label, q, detail in rows:
        flag = ' ' if q >= 0.95 else ('~' if q >= 0.60 else '!')
        print(' %s %-24s %s %5.1f%%  %s' % (flag, label, bar(q), q * 100, detail))
    if info and 'cat' in info:
        print('\n  category            weight   score')
        for k, wt in WEIGHTS.items():
            print('    %-16s %5d   %6.2f' % (k, wt, wt * info['cat'][k]))
    blocked = (info or {}).get('anchor_failed') or []
    verdict = 'PROCEED' if (total >= BAR and not blocked) else 'DO NOT PROCEED'
    if blocked:
        print('\n  HARD STOP: art-lock feature(s) missing -- %s' % ', '.join(blocked))
    print('\n  SCORE %.2f / 100        bar %.0f        %s' % (total, BAR, verdict))
    if total < BAR:
        worst = sorted(rows, key=lambda r: r[1])[:3]
        print('  fix first: ' + '; '.join('%s (%.0f%%)' % (l, q * 100) for l, q, _ in worst))
    return total >= BAR and not blocked


def main():
    p = argparse.ArgumentParser()
    p.add_argument('frames', nargs='*')
    p.add_argument('--baseline')
    p.add_argument('--sequence')
    p.add_argument('--plate', nargs=2, metavar=('MASTER', 'PLATE'))
    p.add_argument('--box', nargs=4, type=int, metavar=('Y0', 'Y1', 'X0', 'X1'))
    p.add_argument('--config', default='sequence.json')
    a = p.parse_args()
    cfg = json.load(open(a.config))

    if a.plate:
        if not a.box:
            sys.exit('--plate needs --box Y0 Y1 X0 X1 (the region allowed to change)')
        t, rows = score_plate(a.plate[0], a.plate[1], a.box, cfg)
        return 0 if report('PLATE  %s  ->  %s  (targeted edit)' % tuple(a.plate),
                           t, rows) else 1
    if a.baseline:
        t, rows = score_baseline(a.baseline, cfg)
        return 0 if report('BASELINE  %s  (no predecessor — absolute checks only)'
                           % a.baseline, t, rows) else 1
    if a.sequence:
        fs = sorted(glob.glob(a.sequence))
        ok = True
        for i in range(len(fs) - 1):
            t, rows, info = score_pair(fs[i], fs[i + 1], cfg)
            ok &= report('%s  ->  %s' % (fs[i], fs[i + 1]), t, rows, info)
        print('\n%s\n' % ('ALL PAIRS PASS' if ok else 'SEQUENCE BLOCKED'))
        return 0 if ok else 1
    if len(a.frames) != 2:
        sys.exit('give two frames, --baseline FRAME, or --sequence GLOB')
    t, rows, info = score_pair(a.frames[0], a.frames[1], cfg)
    return 0 if report('%s  ->  %s' % tuple(a.frames), t, rows, info) else 1


if __name__ == '__main__':
    sys.exit(main())
