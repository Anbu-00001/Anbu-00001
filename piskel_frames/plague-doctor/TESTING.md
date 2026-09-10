# Testing a sequence of PNGs

Notes from building the frame-continuity harness, including the parts that
turned out to be wrong.

---

## The question

Given N PNGs that are supposed to form a coherent animation, how do you test them
automatically? Specifically: how do you tell **"the forest moved 15px"** apart
from **"a different forest was drawn"** — when both produce a large pixel
difference?

Two hand-rolled attempts failed before this one. The first measured edge overlap
(IoU) only inside the carriage, so it scored 1.000 while the window boiled
completely. The second measured luminance only, so it missed a 69% saturation
climb because red carries just 0.21 of luma. Both told me things were fine.

---

## What exists (the research)

**Appearance / difference metrics**

| metric | origin | notes |
|---|---|---|
| PSNR | classical | per-pixel, no perceptual model |
| SSIM / MS-SSIM | Wang et al. | structural similarity, widely used |
| **ꟻLIP** | NVIDIA | *built for alternating between two rendered images* — i.e. exactly frame playback. C++, NumPy, PyTorch, and a Rust crate (`nv-flip`) |
| Butteraugli / SSIMULACRA2 | Google / libjxl | psychovisual, tuned for compression artefacts |
| LPIPS | learned | needs a network |
| CIEDE2000 | CIE | proper perceptual colour distance, in CIELAB |

**Motion / registration**

| method | notes |
|---|---|
| **Phase correlation** | FFT-based, sub-pixel global translation. `cv2.phaseCorrelate` |
| **ORB + RANSAC** | feature match then robust fit; the inlier ratio tells you whether *any* rigid transform explains the change |
| Optical flow (Farnebäck, DIS, RAFT) | dense per-pixel motion |
| ECC | `cv2.findTransformECC`, intensity-based alignment |

**Temporal consistency (the video-research angle)**

- **Warping error (WE)** — warp frame A to B by optical flow, measure residual.
- **tOF** — compare flow fields rather than pixels.
- **RWE** — relational warping error, subtracts the ground-truth baseline.
- **Flicker penalty** — "detail that changes not due to actual motion."

That last phrase is the whole problem stated precisely. The literature also flags
a trap: **warping error is never zero even for ground-truth video**, because of
natural intensity variation and flow estimation error. An absolute threshold on
it is meaningless without a baseline.

---

## Which language

Asked about C++, C#, Rust and Python. The honest answer is that this is a
**C++ pipeline with Python driving it**, and the other two are worse fits:

- **Python** — orchestration only. Every metric below executes in compiled C++
  (OpenCV core, FLIP's backend). Nothing numerical runs in the interpreter.
- **C++** — the same libraries natively. Correct if you need throughput. At 15
  frames the whole suite runs in seconds, so it buys nothing.
- **Rust** — `nv-flip` wraps NVIDIA's FLIP, and `image`/`imageproc` cover basics.
  But there is no mature ORB/RANSAC/optical-flow stack; you would reimplement
  OpenCV to get back to where Python already is.
- **C#** — `Emgu.CV` is OpenCV bindings and `ImageSharp` handles I/O, so the
  ceiling is "Python but with more ceremony." Nothing recommends it here.

---

## The calibration that changed the design

Before trusting any metric, run it against cases whose answer is known:

- **IDENTITY** — a frame against itself. The perfect floor.
- **TRANSLATED** — a frame against itself shifted 15px. Ground-truth coherent motion.
- **REDRAWN** — two independent generations. The failure we must catch.

A metric is only useful if TRANSLATED lands near IDENTITY and far from REDRAWN.

```
case          FLIP     SSIM   dCIE2000  warpErr   ORBinl   phaseDx
IDENTITY    0.0000   1.0000      0.000    0.000    1.000    +0.00
TRANSLATED  0.1755   0.4359      6.522   13.349    0.979   -15.00
REDRAWN     0.1721   0.6126      6.176   11.040    0.562    +0.85
```

**Four of six metrics are useless, and two are actively inverted.** FLIP scores a
correct 15px pan (0.1755) as *worse* than a total redraw (0.1721). SSIM calls the
redraw 40% *more* similar than the correct motion. ΔE and warping error cannot
separate them either.

The reason is simple once seen: they are all **appearance** metrics with no
motion model, so they punish legitimate movement exactly as hard as incoherence.
Reporting FLIP on raw frame pairs would have shipped a suite that fails good
frames and passes bad ones.

Only the **registration** metrics worked: phase correlation recovered the shift
exactly, and the ORB inlier ratio separated cleanly (0.979 vs 0.562).

---

## The fix: register first, then compare

Align A onto B using the recovered transform, and only then run the appearance
metrics. What remains is *change not explained by motion* — the flicker itself.

```
TRANSLATED   inliers 0.979   recovered dx=-14.97 dy=-0.00 scale=1.0000
  raw                 FLIP 0.1755   SSIM 0.4359   dE 6.522
  AFTER registration  FLIP 0.0021   SSIM 0.9992   dE 0.041

REDRAWN      inliers 0.562   recovered dx=+0.75 dy=-0.26 scale=1.0004
  raw                 FLIP 0.1721   SSIM 0.6126   dE 6.176
  AFTER registration  FLIP 0.1719   SSIM 0.6253   dE 6.101
```

Same metrics, same images, ordering changed: **~80x separation** where there was
none. Registration is sub-pixel accurate (-14.97 recovered from a -15 shift).

---

## The harness

`frametest.py` implements the two stages.

**Stage 1 — registration.** ORB + RANSAC partial-affine (translation, rotation,
uniform scale), cross-checked by FFT phase correlation, which shares none of
ORB's failure modes. Reports `dx`, `dy`, `scale` and the inlier ratio. Scale > 1
is how forward travel is detected — objects grow as you approach them.

**Stage 2 — residual.** Warp A by the recovered transform, then FLIP, SSIM and
CIEDE2000 on the aligned pair.

```bash
./.venv/bin/python frametest.py A.png B.png --hold 0.9 [--expect-dx -15]
./.venv/bin/python frametest.py --sequence 'f*.png' --holds 0.9,0.5,0.12
./.venv/bin/python frametest.py A.png B.png --regions regions.json
```

`regions.json` splits the frame so parts with different expected behaviour are
judged separately. `"~name"` means the complement of another region:

```json
{"window": [[962,0],[1774,0],[1774,652],[1050,412]], "interior": "~window"}
```

### Thresholds and where they came from

| check | threshold | basis |
|---|---|---|
| inlier ratio | >= 0.80 | translation 0.979, redraw 0.562 |
| FLIP (aligned) | <= 0.05 | translation 0.0035, redraw 0.1704 |
| SSIM (aligned) | >= 0.95 | translation 0.9988, redraw 0.6313 |
| CIEDE2000 (aligned) | <= 1.50 | translation 0.075, redraw 6.079 |

Verified end to end: identity ACCEPTs, a synthetic 15px translation ACCEPTs with
`dx` recovered exactly, an independent regeneration REJECTs on all four.

---

## Limitations — read before trusting a number

1. **Thresholds are calibrated against synthetic controls, not against a good
   *generated* pair**, because we do not have one yet. A real hand-made frame will
   carry legitimate small differences. Expect to loosen these once there is a
   frame we agree is correct, and record why.

2. **Partial-affine cannot represent parallax.** It models one rigid motion for
   the whole region. If near and far content genuinely move at different rates —
   which is exactly what forward travel through a forest looks like — the inlier
   ratio drops *legitimately*. Mitigation: split depth bands into separate
   regions. Do not read a low inlier ratio as "redrawn" without checking whether
   the region spans several depths.

3. **ORB needs texture.** In very dark, low-contrast regions it finds few
   keypoints and registration gets noisy. Match count is printed for this reason;
   below ~200 matches, treat the transform as unreliable and lean on phase
   correlation instead.

4. **These metrics say nothing about whether the animation is any good.** They
   test continuity, not staging, timing or drama. A perfectly coherent sequence
   of boring frames passes everything.

---

## Environment

System Python is PEP 668 externally-managed, so the stack lives in a venv that
inherits the existing system packages rather than duplicating them:

```bash
python3 -m venv --system-site-packages .venv
./.venv/bin/pip install flip-evaluator scikit-image
```

| package | version | provides |
|---|---|---|
| opencv | 4.13.0 | ORB, RANSAC, phase correlation, optical flow, warping |
| numpy | 2.4.4 | arrays |
| scipy | 1.17.1 | numerics |
| scikit-image | 0.26.0 | SSIM, CIELAB, CIEDE2000 |
| flip-evaluator | 1.7 | NVIDIA ꟻLIP |
| Pillow | 12.2.0 | I/O |

## Sources

- [ꟻLIP: A Difference Evaluator for Alternating Images — NVIDIA Research](https://research.nvidia.com/publication/flip)
- [FLIP paper (ACM CGIT 3:2)](https://dl.acm.org/doi/10.1145/3406183)
- [nv-flip — Rust bindings](https://docs.rs/nv-flip/latest/nv_flip/)
- [OpenCV: Motion Analysis and Object Tracking](https://docs.opencv.org/4.x/d7/df3/group__imgproc__motion.html)
- [Phase correlation](https://en.wikipedia.org/wiki/Phase_correlation)
- [Toward Accurate and Temporally Consistent Video Restoration (warping error, tOF, RWE)](https://arxiv.org/html/2312.16247v1)
- [Blind Video Temporal Consistency via Deep Video Prior](https://arxiv.org/pdf/2010.11838)
- [SSIMULACRA2 on PyPI](https://pypi.org/project/ssimulacra2/)

---

# The gate — `calibrate.py`

`frametest.py` tells you **what** is wrong. `calibrate.py` decides **whether to
proceed**. One number out of 100, and the rule is simple:

> **Do not move to the next frame until the current one scores 95 or above.**

```bash
./.venv/bin/python calibrate.py --baseline f01.png     # first frame, absolute checks
./.venv/bin/python calibrate.py f01.png f02.png        # scored against predecessor
./.venv/bin/python calibrate.py --sequence 'f*.png'    # every consecutive pair
```

## How it is interdependent, not standalone

- It **imports** `frametest.py` — `register`, `residual`, `phase_shift`,
  `build_masks`, `read`. The registration-then-compare pipeline is not
  reimplemented, so the two tools can never drift apart in method.
- It **reads `sequence.json`**, which encodes SCRIPT.md's exposure sheet: the act
  structure, the per-frame hold times, the travel budget, and which acts are
  permitted to gain light. Change the plan, and the gate changes with it.
- It **reads `regions.json`**, so interior and window are scored separately and
  the worst region governs — the exact blind spot that let an earlier checker
  report 1.000 while the window boiled completely.

## Weights, and why these ones

Weights are proportional to what actually broke this sequence, counted:

| category | weight | what it catches | times it bit us |
|---|---|---|---|
| registration | 30 | content redrawn instead of moved | ~every frame |
| residual | 25 | change beyond the motion | ~every frame |
| travel | 15 | direction, magnitude, growth | direction reversed 4x |
| exposure | 15 | luminance continuity within act budget | overshot 3x |
| colour | 10 | saturation / channel drift | missed entirely by a luma-only check |
| invariants | 5 | canvas, clipping, owl clearance, cold pixels | owl nearly slid out of frame |

## Curve endpoints

Every curve is anchored to the measured calibration table — the bad case maps to
0.0, the ground-truth case to 1.0. Nothing is guessed.

| axis | 0.0 at | 1.0 at | measured |
|---|---|---|---|
| inlier ratio | 0.60 | 0.95 | redraw 0.543, translation 0.978 |
| FLIP | 0.120 | 0.010 | redraw 0.1704, translation 0.0035 |
| SSIM | 0.700 | 0.990 | redraw 0.6313, translation 0.9988 |
| CIEDE2000 | 4.00 | 0.30 | redraw 6.079, translation 0.075 |

Tolerance axes (exposure, saturation) use a **dead zone**: perfect within 35% of
tolerance, then ramping to zero at the limit. A linear-from-zero ramp cost a 0.6%
deviation eight points, which made 100 unreachable for a legitimately good frame.

## Validated end to end

| case | score | verdict |
|---|---|---|
| f01 baseline | **100.00** | PROCEED |
| synthetic ground-truth motion | **99.82** | PROCEED |
| real independent regeneration | **17.26** | DO NOT PROCEED |

A gate that only ever passes is worthless, so both ends are tested every time the
curves change.

## A bug worth recording

The first run scored f01 at exactly 95.00 with "cold pixels: 4 blobs, 483 px",
while a standalone check on the same file said 2 blobs, 257 px. Two of my own
tools disagreeing on one image is not a rounding difference — one was wrong.

Cause: `a[:, :, 0] + 40` on a **uint8** array wraps. R=230 becomes 14, so bright
lantern pixels satisfied "blue exceeds red by 40" and registered as cold. The
standalone check cast to `int` first; the gate did not.

The lesson is not "remember to cast." It is that **the disagreement was the
signal**. Neither number looked absurd on its own. Keep at least two independent
paths to any measurement that gates a decision.

## Still not measured

Staging, timing, drama, whether the frame is any good. A perfectly coherent
sequence of boring frames scores 100. This gates continuity only.

---

## The saturation metric was measuring light, not colour (2026-09-10)

The gate scored region saturation as raw chroma, `mean(max(RGB) - min(RGB))`, against
a +-10% tolerance. That metric is **luminance-confounded**: chroma scales linearly with
exposure, so brightening a region without touching its hue moves it hard.

Measured on f07's window band, a pure scalar gain and nothing else:

| gain | chroma (max-min) | HSV S |
|------|------------------|-------|
| 1.00 | 14.27  +0.0%     | 0.5281  +0.0% |
| 1.25 | 17.83 +24.9%     | 0.5688  +7.7% |
| 1.50 | 21.36 +49.6%     | 0.5688  +7.7% |
| 2.00 | 27.73 +94.3%     | 0.5677  +7.5% |

A 1.5x gain — **zero hue change** — reads as +49.6%, five times past tolerance.
HSV S moves +7.7% on the first step (dark pixels lifting off the `mx > 1` floor) and
is then flat, which is the correct behaviour.

The clinching evidence: the **locked reference** sits at chroma 61.04 against f07's
14.27. Enforced literally, the rule forbids the piece from ever reaching its own
approved ending. The rule was wrong, not the art.

**What it cost before it was caught.** Steering by it, f07's window was desaturated to
HSV S 0.498 while every other frame sat at 0.655-0.671 — a one-frame colour pothole,
exactly the flicker artefact the harness exists to prevent. The gate scored that frame
**100.00**. Repaired with `resat.py` to 0.662; the pair went 90.25 -> 99.00 under the
corrected metric.

**Fixes applied**
- Saturation is now HSV S `(max-min)/max` with a near-black floor; tolerance is
  act-aware (+-10%, +-25% where the act may brighten), matching exposure, because
  light and visible colour move together physically.
- Exposure and saturation now use the **traced polygons**, not column bands. The band
  `x >= 0.54w` swept in sill and wall, damping every window reading. Under the polygon,
  f06->f07's window read +49.2%, not the ~+20% the band had reported.
- Window exposure is scored against a **declared ramp** (`window_luma_plan`), not
  against the previous frame. A delta budget lets each frame redefine its own ceiling;
  that is precisely how f07 drifted +49% with nothing to catch it. The plan is the
  exposure sheet doing its job.

### The pattern, for the third time

Every metric failure so far has the same shape: **the metric has no model of the thing
that legitimately changed.** `residual()` had no model of a complement mask, so it
measured the wrong region. The window mask had no model of dark trunks, so it kept
them. Chroma has no model of exposure, so it charged the art for the light.

The tell each time was two measurements disagreeing. Here: the gate said f07's window
was *too saturated*, while the eye said it looked *washed out*. That contradiction was
the signal, and it sat unexamined for a frame.

## resat.py

Region metering: hits a target mean luminance (region gamma, solved) and then a target
HSV S (chroma scaled about luma, solved). Scaling chroma about luma is **exactly**
luma-preserving — the weights sum to 1 — so a saturation tool cannot smuggle in a
relight. Order matters: exposure first, because gamma and a chroma scale do not commute
and the saturation solve must run on the pixels that ship.

    resat.py in.png out.png --poly window --target-luma 16.5 --target-s 0.665

Solve against the *gate's* saturation formula, not OpenCV's. They differ by ~0.05 on
this material because OpenCV assigns S=1.0 to near-black pixels where max=1, min=0.
The first version of this tool overshot 0.665 to 0.719 for exactly that reason.

---

## The gate had no anchor to the art lock (2026-09-10)

The sill carving **SAME DISEASE, DIFFERENT KINGS** is absent from every frame in the
build. The generator dropped it when it made f01 from `reference.png`, and because each
later frame inherits f01's interior through the graft pipeline, the loss propagated
byte-identically. Detail energy in that band:

    reference.png   1.386   100%
    build/f01..f08  0.610    44%      <- identical in all eight

**The gate scored all eight 95-100.** It compares frame N+1 to frame N and never opens
`reference.png`. A feature lost at f01 is *perfectly consistent* with everything that
follows it, so continuity scoring is structurally blind to it. Eight frames of a
sequence built against an art lock that nothing ever checked against the art lock.

### Fix: anchor checks

`anchors` in `sequence.json` names boxes that must still carry the reference's incised
detail, scored as normalised cross-correlation of the **high-pass** of each against the
reference's. High-pass, not raw pixels, so a frame that is merely lit differently still
passes — the question is "is the carving still cut into this sill", not "does this look
like the reference".

    sill_carving   absent 0.380 | restored 0.589 | floor 0.50

An anchor failure is a **hard stop**, not a weighted deduction: the old carving-less
f07->f08 pair scores 99.58 and is refused anyway. A missing art-lock feature is not
worth five points, it is worth the frame.

## engrave.py

Restores a carved detail from the art lock without dragging the lock's lighting with it.
Pasting reference pixels would import the reference's rim-light; instead it transfers
the **high-pass detail layer only**, scaled by how lit the target's sill actually is
(`strength = target_luma / reference_luma`). Across f01-f08 that solved to 0.508-0.510 —
stable to three decimals, so the carving does not flicker — and it means the carving
deepens as the world brightens instead of popping in at full strength.

### A near-miss worth recording

While chasing this I built a tile-wise Laplacian-energy map of reference vs f01 and read
it as "134 of 217 interior tiles lost >40% of their detail". Checking two of those tiles
by eye killed the claim: f01 is a **relight** of the reference — less crimson rim-light,
warmer wall — and normalised Laplacian variance responds to local contrast, so it was
measuring the lighting change. Same confound as the chroma metric, found the same way,
one turn later. The carving is real because it was verified *by eye* as a discrete
missing feature; the broad claim was withdrawn.

**The rule this suggests:** a metric may flag, but only a look may convict.

---

## The residual was pricing exposure twice (2026-09-10)

`residual()` compared aligned frames with FLIP, grey SSIM and CIEDE2000, none of which
have any model of a lighting change. f09's entire job is a large **non-uniform** relight,
and it scored **43%** on a window that was geometrically perfect — while exposure, in its
own category, scored 15/15 for the same fact. The same change was being charged twice,
once in the category built for it and once in a category blind to it.

**Fix: divide out the low-frequency shading field before comparing.** A single gain is
not enough — the change is a gradient, not a level. Dividing by the blurred luminance
ratio removes shading that varies more slowly than `SHADING_SIGMA` and leaves everything
sharper than it, which is exactly what boil and redraws are.

| at sigma 60 | window FLIP | SSIM | dE |
|---|---|---|---|
| relit, geometry identical | 0.037 | 0.991 | 1.02 |
| genuine redraw | 0.085 | 0.954 | 3.50 |

That 2-3x margin holds from sigma 30 to 100, so it is not a tuned number. Validated both
ways on every change: the assembled f09 rose 84 -> 96, and the raw plate — a real interior
redraw — still fails at 75. A fix that only ever raises scores is not a fix.

### What it exposed

With the residual finally measuring structure, **f01->f02 dropped to 94.58 and failed.**
It had been passing on the strength of a lighting difference masking real boil. The cause
was honest: f02's window was 4.5% darker than f01's, which also crushed 2% more pixels to
pure black. The forest act declares no light change, so the plan now *says* so — f02-f06
are pinned flat at f01's measured 8.62 — and all eight pairs pass on structure.

A metric that gets stricter should be expected to fail something that used to pass. If it
doesn't, it probably wasn't stricter.

## relight.py

Moves light from a plate onto a master without moving geometry: the ratio of plate
luminance to master luminance, blurred until no edge survives, applied as a gain. Broad
falloff crosses over; strokes do not. **Colour-blind by construction**, so a plate that
came back too warm cannot drag its warmth along with the light.

It also turned out to be the better way to build the *window*. Grafting f09_raw's window
scored 84.32 (registration 0.932, residual 43%); relighting f08's own window from the
same plate scored 96.30 (registration 0.984, residual 85%). The landscape had not moved,
so there was never any reason to accept new pixels for it — the same "transform, don't
regenerate" principle that carried f02-f06, applied to light instead of position.

### A leak in resat.py, found the same way

`--target-luma` solved its gamma and applied it to the **whole array**, then blended only
inside the region — so the exposure change leaked into every pixel outside it. f08 shipped
with its interior quietly lifted +1.2%. Caught because f09's interior measured 19.15 going
in when f08's interior was 17.09, and those two numbers had no business differing.
Fixed by blending against a pre-gamma copy. **Two numbers that should have been equal
and weren't** — the same tell as every other bug in this file.

---

## The loop (2026-09-11)

f12-f15 were built **entirely in post**, with no generation. Regenerating a loop frame
cannot work: for f15 to flow into f12 the configuration must repeat *exactly*, and a
generator gives a new arrangement every time. So every moving element is a cycle
computed from the frame index.

    build/f14 -> build/f15   98.46
    build/f15 -> build/f12   98.47      <- the closure, interior exposure delta -0.0%

**Cycle lengths are deliberately different** — 4 for the birds, the light and the carving
glow, 2 for the lantern flame — because a loop whose elements all share one period reads
as its frame count. Riding them at different lengths makes the perceived period the LCM.

Anything constant through the loop must be *exactly* constant: the interior gleam is
applied at the same strength in all four frames, which is why the closure's interior
exposure delta is -0.0% rather than merely small.

### flock.py — the conveyor

Birds are generated once and animated in post. n birds sit evenly spaced along a path,
each advancing 1/frames of that spacing per frame, so after a full cycle every bird
occupies the position the one ahead of it held and the set is identical. Sprites are
lifted as an **alpha matte** from how much darker the plate is than the master, so a
silhouette carries no colour of its own and takes whatever sky it is placed on.

### stamp.py — the readouts

The labels are lifted from `reference.png` and composited as a proportional darkening
(they measure 0.479x their local background there), never generated. A generator
re-letters between frames, and text redrawn every frame **crawls** — fatal for words that
hold the same spot through a loop. The numbers are deliberately not baked: they change
daily and belong to the renderer.

### gleam.py — light without flattening

Strengthening the interior could not be a flat wash: a wash lifts the shadows and
flattens the figure, and his silhouette against a brighter window is what the piece rests
on. Instead it amplifies light that is *already there* — pixels already crimson-leaning
and already catching some light get more, flat black stays flat black — with falloff from
the window, because that is where the light comes from.

### What the anchor caught

f12_raw came back with the sill carving gone: **NCC 0.381, exactly the "absent" value**,
and the gate hard-stopped it at 55.62 regardless of everything else. That is the second
time the generator has silently dropped that carving, and the first time anything noticed
on the same day it happened.

---

## The export was the failure, not the animation (2026-09-11)

Two faults shipped in the first export, both in `assemble.py`, both measured after:

**Grading.** It quantised to 32 colours with Floyd-Steinberg dithering. The Crimson Moon
banner's own contract says *"single fixed palette across all frames"* with **no
dithering**, and the measurement agrees — dithering is strictly worse at every colour
count:

| 512x256 | no dither | Floyd-Steinberg |
|---|---|---|
| 32 colours | dE 2.778 | dE 3.210 |
| 128 colours | dE 1.733 | dE 1.936 |

Shipped: **dE 3.21**. Corrected: **dE 1.658** at 128 colours, no dither — half the error.
The moon lives happily on 10-16 colours because it is flat pixel art. This is a graded
render; grading needs an order of magnitude more.

**The labels.** They were baked into the frames and then dithered into nothing. They
should never have been there: GitHub proxies README images through Camo, which blocks
every external resource, which is exactly why the renderer already draws text as SVG
`<rect>` glyphs from `lib/pixelfont.js`. Stripped from the frames, moved to the renderer.

### Also measured and rejected

**WebP.** Lossy is worse than the quantisation it would replace — q95 adds dE 3.573,
above even the 32-colour PNG. Lossless saves 12% (943 KB vs 1073 KB) for a compatibility
gamble inside a Camo'd SVG. Palette PNG stays.

**384x192.** Payload 644 KB against 1012 KB, but the sill carving stops being legible —
"KINGS" mushes out. 512x256 is the floor for this art, which is what the reference
measurement said in the first place.

### Delta-cropped layers, and a bug in the obvious version

The renderer stacks frames with cumulative opacity, so a later layer only needs to carry
the rectangle that changed. That cut the payload ~30%.

But the obvious version is wrong for the loop. Reveal layers (f02-f12) fade in and STAY,
so a delta against the predecessor is correct. Loop overlays (f13-f15) fade in **and
out** over a permanently opaque f12 — and a delta against the predecessor would be wrong
the instant the layer before it switched off, because the pixels it does not carry fall
back to f12, not to the frame it was differenced against. Loop overlays are therefore
deltas against **f12**, which makes each one self-sufficient.

### Hard switches, not cross-fades

The moon dissolves because it is a reveal of one growing shape. This is an animation: the
world moves between frames, so a dissolve would double-expose the trees and the birds.
Hard switches are safe here for the same reason the moon's fade was — the stack below is
always fully opaque, so the page ground never shows through and there is no black flash.

---

## The six-frame rebuild (2026-09-11)

### The readout, settled by measurement

Three colour treatments were tried and rejected by eye before anyone measured the
thing. The research says the two obvious answers are both wrong on this ground —
*"white text on red… tends to get swallowed"* and *"red text has a low contrast
level"* — which is exactly bone and glow, the two options I had offered.

Then the numbers closed it. Under the actual text lines the ground ran from
rgb(65,26,54) to rgb(236,7,37):

| ink | vs the dark bands | vs the bright bands |
|---|---|---|
| reference rgb(26,12,27) | 1.38:1 | — |
| pure black | 1.30:1 | — |
| bone #D6C9BE | 9.75:1 | 2.78:1 |
| near-white | — | 3.86:1 |

**Nothing contrasts with both ends.** The ink was never the problem; the ground was.
So the zone is flattened — which is what the Crimson Moon banner already does with
its inscription zone, for exactly this reason.

**And the benchmark was wrong too.** `reference.png`'s own baked readout measures
**1.82:1** — glyph rgb(23,12,27) on ground rgb(126,17,45). Chasing WCAG 4.5:1 on a
crimson badge was never achievable and never the target. The flattened zone reaches
**2.6–2.7:1 on four of five lines, better than the master**, with the top line at
1.74:1, matching it.

So "still looks stupid" was never about colour. It was the 3x5 letterforms. The
research is explicit — *"when unsure, use 5x7 — you need 5x7 pixels to have gaps
where they should be"* — and `pixelfont7.js` is 5x7 with 1px uniform strokes and
O/0, I/1, S/5 deliberately disambiguated.

### The treeline scroll, abandoned honestly

Three attempts, three tears:

1. band from x950 — dragged the doctor's shoulder into the middle of the forest,
   because the window OPENING starts near x1096 at those rows, not x950
2. band y452-887 — scrolled the river and the viaduct, which are far and must not move
3. narrowed and filled from a second plate — still tore, because the **sill slopes
   through the foreground and belongs to the carriage, not the landscape**

There is no rectangle that captures the trees without capturing something that must
stay still. And the generator will not translate a texture band: asked twice, it
either re-invents it (f02, inliers 0.634) or holds it perfectly (f03, 0.959). It has
no third behaviour, and two real travel positions cannot synthesise six.

So the loop is a cinemagraph. That is the right form for a 3-second badge, and it is
seam-free, which a forced scroll would not have been.

### What moves, and on what period

    cloth    2   watchers alternate between the still and streaming plates
    crows    6   a wingbeat cycled from 21 sprites harvested across the three plates
                 (width/height 0.7 to 3.6 — folded through fully spread), drifting
                 on an arc and scaling with distance
    beacon   3   interpolated between two measured flame sizes, area 295 -> 152
    lantern  2   guttering
    gleam    6   crimson interior breath; carving glow breathes with it

Different periods on purpose: a loop whose elements share one period reads as its
frame count.

### Export

512x256, **256 colours**, no dither, fully opaque. Mean **dE 1.688**, p95 3.91 —
against the **3.21** the first export shipped. Delta-cropping saved nothing here
(every layer covers 100%) because the gleam and glow breathe across the whole frame;
that is a deliberate trade of ~200 KB for a picture that is alive rather than static.

---

## Quality pass (2026-09-11)

### The actual defect was a rectangle in the sky

`zonecalm.py` flattened the readout ground inside a **feathered rectangle**, and a
blurred rect still shows its edge: the lifted cloud bands meet unlifted ones along a
straight line and the eye finds it instantly. It read as a glass panel pasted into
the sky. Replaced with a **separable raised-cosine (Hann) falloff**, which has no
boundary at all — the correction simply goes to nothing at the edges.

### Formats, measured not assumed

GitHub does serve WebP, so dropping the palette entirely looked like the obvious
quality win. It is not:

| at 512x256 | payload | mean dE | p95 |
|---|---|---|---|
| shared 256c palette | 634 KB | **1.688** | 3.91 |
| WebP q98 | 391 KB | 3.628 | 11.36 |
| WebP q92 | 278 KB | 3.850 | 11.57 |

WebP lossy is **worse**, and badly: it subsamples chroma 4:2:0, and this picture is
almost entirely saturated crimson, which is the worst case for that. WebP lossless is
exact but 1195 KB at 512x256. Second time WebP lossy has lost on measurement here.

### libimagequant, a free win

pngquant's library refines the palette with K-means (Voronoi iteration) toward a
locally optimal set instead of stopping at the median-cut split:

    PIL median cut 256c    634 KB   dE 1.688
    libimagequant 256c     628 KB   dE 1.483     same size, 12% less error

### Resolution was the lever

Colour error is flat across resolutions (dE ~1.45 at 512, 768 and 1024) because it is
palette-limited, not resolution-limited. The visible difference is pure sharpness —
512x256 needs a 2x upscale to fill 1024 wide. Shipping **768x384**: 2.25x the pixels,
and the GIF actually got *smaller* (349 KB against 577 KB) because libimagequant
compresses better than median cut.

Delta-cropping was also recovered from 100% to 72% coverage: the cloth change had
been done by alternating **whole plates**, so every pixel differed between frames even
though only 12% actually changed. One base plate with the watcher band grafted fixed it.

### Readout placement, scanned rather than centred

Every vertical offset was scored against the darkest cloud band each line actually
sits on, across all six frames. Centring gave a worst line of 1.53:1; **y=31 gives
1.93:1**, which beats `reference.png`'s own baked readout at 1.82:1.
