#!/usr/bin/env python3
"""
Export the frames for the SVG renderer, to the Crimson Moon contract.

Three rules taken from the existing banner, and one added by this piece:

  1. ONE fixed palette across every frame, and NO DITHERING. Dithering is
     strictly worse here -- measured mean dE 3.21 with Floyd-Steinberg against
     2.78 without, at the same colour count -- and its noise is what dissolved
     the readout labels entirely at 512x256.
  2. Fully opaque. No alpha channel anywhere.
  3. No text baked in. GitHub proxies README images through Camo, which blocks
     every external resource, so the renderer draws glyphs as SVG <rect>s.
  4. NEW: this art is a graded render, not flat pixel art. The moon lives on
     10-16 colours because it is flat; grading needs an order of magnitude more.

Layers are DELTA-CROPPED. The renderer stacks frames with cumulative opacity --
frame 0 stays opaque and each later frame fades in on top and stays -- so a later
layer only has to carry the rectangle that actually changed.
"""
import argparse, base64, io, json, os
import cv2
import imagequant
import numpy as np
from PIL import Image

import grade as G


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--w', type=int, default=512)
    p.add_argument('--h', type=int, default=256)
    p.add_argument('--colours', type=int, default=80)
    p.add_argument('--thresh', type=int, default=6, help='per-pixel delta that counts as changed')
    p.add_argument('--out', default='dist')
    p.add_argument('--grade', dest='grade', action='store_true', default=True,
                   help='cool onto the Crimson Moon axis and relay the sky (default)')
    p.add_argument('--no-grade', dest='grade', action='store_false')
    p.add_argument('--rot', type=float, default=-26.0)
    p.add_argument('--shadow', type=float, default=0.5)
    p.add_argument('--sky', type=float, default=1.0)
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)

    stems = ['f%d' % i for i in range(1, 7)]

    #  Grade at the plate's full 1774x887 and only then resample, so the colour
    #  decision is made on all the detail and the resampler sees finished pixels.
    #
    #  INTER_AREA, not LANCZOS. Measured on f1 at 512x256, against the same frame
    #  resampled but left unquantised: AREA holds detail NCC 0.971 where LANCZOS
    #  manages 0.957, at dE 5.29 against 6.41. Lanczos' ringing becomes its own
    #  palette entries once quantised, so the sharpening it buys is spent twice.
    #  Pre-sharpening was tried too and rejected -- it moved NCC 0.9682 -> 0.9685,
    #  inside the noise, while dE went 5.71 -> 6.69. It shifts colour, not detail.
    small = []
    for s in stems:
        plate = np.array(Image.open('build/%s.png' % s).convert('RGB')).astype(np.float32)
        if a.grade:
            plate = G.grade(plate, rot=a.rot, shadow=a.shadow, sky=a.sky)
        px = cv2.resize(np.clip(plate, 0, 255).astype(np.uint8), (a.w, a.h),
                        interpolation=cv2.INTER_AREA)
        small.append(Image.fromarray(px))

    strip = Image.new('RGB', (a.w, a.h * len(small)))
    for i, im in enumerate(small):
        strip.paste(im, (0, i * a.h))
    #  libimagequant, not PIL's median cut. It refines the palette with K-means
    #  (Voronoi iteration) toward a locally optimal set instead of stopping at the
    #  median-cut split, and it is measurably less posterised here: dE 1.483
    #  against 1.688 at the same colour count and the same file size.
    pal = imagequant.quantize_pil_image(strip, dithering_level=0.0,
                                        max_colors=a.colours,
                                        min_quality=0, max_quality=100)

    quant = [im.quantize(palette=pal, dither=Image.NONE) for im in small]
    arrs = [np.array(q.convert('RGB')).astype(np.int16) for q in quant]

    layers, total = [], 0
    for i, q in enumerate(quant):
        if i == 0:
            box = (0, 0, a.w, a.h)
        else:
            #  Every layer is a delta against its predecessor, because the whole
            #  15-frame sequence loops as ONE cumulative pass: within a cycle layers
            #  only ever switch ON, in order, and all of them reset together at the
            #  wrap. f01 stays permanently opaque underneath, so the reset never
            #  exposes the page ground -- no black flash.
            d = np.abs(arrs[i] - arrs[i - 1]).max(2)
            ys, xs = np.nonzero(d > a.thresh)
            if len(xs) == 0:
                layers.append(None); continue
            box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1 - int(xs.min()),
                   int(ys.max()) + 1 - int(ys.min()))
        crop = q.crop((box[0], box[1], box[0] + box[2], box[1] + box[3]))
        buf = io.BytesIO(); crop.save(buf, 'PNG', optimize=True)
        raw = buf.getvalue(); total += len(raw)
        layers.append({'x': box[0], 'y': box[1], 'w': box[2], 'h': box[3],
                       'data': base64.b64encode(raw).decode()})
        crop.save('%s/%s.png' % (a.out, stems[i]), optimize=True)

    js = ('// Auto-generated by piskel_frames/plague-doctor/export.py -- do not hand-edit.\n'
          '// 6-frame "The Indifferent World" streak banner, %dx%d native, %d-colour\n'
          '// shared palette, no dithering, fully opaque. Graded by grade.py onto the\n'
          '// Crimson Moon colour axis (%s) so the two banners read as one set.\n'
          '// Layers after the first are DELTA-CROPPED: each carries only the rectangle\n'
          '// that changed, and the renderer stacks them with cumulative opacity so\n'
          '// earlier layers show through.\n'
          'export const ART_W = %d;\nexport const ART_H = %d;\n'
          'export const LAYERS = %s;\n'
          % (a.w, a.h, a.colours,
             ('rot %+.1f, shadow %.2f, sky %.2f' % (a.rot, a.shadow, a.sky))
             if a.grade else 'ungraded',
             a.w, a.h, json.dumps(layers, separators=(',', ':'))))
    open('%s/frames.js' % a.out, 'w').write(js)

    cov = np.mean([l['w'] * l['h'] / (a.w * a.h) for l in layers[1:] if l])
    print('  %dx%d, %d colours, no dither' % (a.w, a.h, a.colours))
    print('  %d layers, mean layer covers %.0f%% of canvas' % (len([l for l in layers if l]), cov * 100))
    print('  payload %.0f KB raw -> %.0f KB base64 in the SVG' % (total / 1024, total * 4 / 3 / 1024))
    print('  wrote %s/frames.js (%.0f KB)' % (a.out, os.path.getsize('%s/frames.js' % a.out) / 1024))


if __name__ == '__main__':
    main()
