# The Indifferent World — six frames, looping

Companion to the Crimson Moon view counter. Shows GitHub streak and total commits.
**`reference.png` is the master.** Everything here serves that image; nothing
re-opens it.

## What the piece is

A plague doctor asleep in a carriage above a burning valley. He does not wake. He
never wakes. The world outside is staging an apocalypse — a castle alight, a
ruined viaduct, a river running red, figures standing along the road watching him
pass — and he sleeps through all of it, holding the book and the count.

The carving on the sill is the thesis: **SAME DISEASE, DIFFERENT KINGS.** Nothing
changes but who is in charge. The tally marks on the wall are the streak; the book
is the record; he keeps both and looks at neither.

The loop is the argument, not the delivery format. This sits on a README and is
seen every day, forever. It does not resolve because it does not resolve.

## Six frames

Only **f1 is generated.** f2–f6 are built in post, because a generator cannot close
a loop: the configuration has to repeat exactly and it gives a new arrangement
every time.

| what | behaviour | why |
|---|---|---|
| far landscape | **static** | distant things do not parallax; holding them is honest |
| near treeline | scrolls left, one tree-spacing over 6 frames | close things move — this is what says *travelling* |
| watchers | conveyor along the ridge, identical and motionless | loops cleanly, and means there are many of them |
| birds | wing cycle + drift | so they fly rather than slide |
| beacon, lantern | gutter on a 2-frame cycle | a different period, so the loop reads longer than 6 |
| crimson gleam | pulses; carving glow breathes | keeps the interior alive without moving anything |

Holds 0.5s each — a 3.0s cycle.

## Rules that do not get re-litigated

- **He never wakes.** No eyes, no lenses, no goggles, no glints, ever. Four attempts
  at revealing the mask all failed; the art works *because* the head is hidden.
- **No orange, no yellow.** The window measures 0.0–0.2% of lit pixels in that hue
  band across every frame and the reference. It is crimson going to plum and rose.
- **Text is never baked in.** GitHub proxies README images through Camo, which
  blocks every external resource — so the renderer draws glyphs as SVG `<rect>`s
  from `lib/pixelfont7.js`. Numbers change daily and belong to the renderer.
- **The readout zone stays calm and bright.** x 278–379, y 27–96 in 512×256 coords.
  Dark ink needs a lit ground; that is why the reference's own ink reads there.
- **One fixed palette, no dithering.** Measured: dithering is strictly worse at
  every colour count.

## Export

512×256, **256-colour** shared palette, no dither, fully opaque, delta-cropped
layers. Six frames costs less than fifteen did at half the colours, so the
saving goes into fidelity.
