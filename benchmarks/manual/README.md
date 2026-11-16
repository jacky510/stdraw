# benchmarks/manual — jacky's hand-drawn samples, kept on file

This directory stores **manual layouts exported by jacky via hand-dragging**
(the ground truth) used as the acceptance baseline for the "structurally
equivalent" side of layout shape. Coordinates are not required to match
pixel-for-pixel, but the engine's automatic layout must reproduce the same
role grouping (endpoint columns / mid-row band / wing column / loner
placement) and relative geometric regularities as the samples.

## classic-cld-manual-layout.json

- **Origin**: exported via "Export layout" after jacky hand-dragged the nodes
  on the stdraw demo-2d interactive page (Kanban card ref-scrubbed attachment,
  2026-11-06).
- **Graph**: `classic-cld-growth-and-burden` (Limits to Growth × Shifting the
  Burden, 8 nodes).
- **viewBox**: 856×760.
- **Structural regularities** (the regression test
  `tests/test_layout_modes.py::TestSpineWingManualEquivalence` derives the
  role grouping automatically from this file):
  - Endpoint columns: adopters(413,214) / rate(412,535) — same x column
    within 1px;
  - Mid-row band: word(308,368) / potential(112,368) / crowding(547,369) —
    same row within ±1px;
  - Right-wing column: quickfix(741,289) / sideeffect(747,453) — same x
    column within 6px;
  - Loner mid-lower: fundamental(594,533) (in the same row band as rate).
- **Copy discipline**: this file is the in-repo ground truth; the regression
  tests tied to engine behavior read only this file and derive expectations
  from it — no coordinate copies are written inside the tests.

## fan-d12-manual-layout.json

- **Origin**: exported via "Export layout" after jacky hand-dragged the
  nodes on the stdraw demo-2d interactive page (2026-11-15).
- **Graph**: `fan-d12` (HUB + 11 spokes; dense-mode family, max_deg=11).
- **viewBox**: 1520×520.
- **Structural regularities** (measured; the regression test
  `tests/test_radial_manual_calibration.py` derives the battery
  expectations from the fixture itself, no coordinate copies):
  - HUB at the ring-card centroid (deviation 6/19px on the axes);
  - single ring, radius modulated in a 179–272px band (radius CV 0.122),
    azimuth gaps uneven (CV 0.486 — the human reading of "roughly
    evenly spread", with an open sector at the lower right);
  - minimum card rect-gap 12px (tight packing: shortest total spoke
    length under the symmetry/uniformity constraints);
  - no long edges: every edge is a hub spoke, longest/median < 2.
- **Caliber role**: upper band source for the radial form battery
  (azimuth CV <= 0.50, radius CV <= 0.15, centroid deviation <= 24px).

## fan-d17-manual-layout.json

- **Origin**: exported via "Export layout" after jacky hand-dragged the
  nodes on the stdraw demo-2d interactive page (2026-11-15). This is
  the k>=17 design truth: the operator delivered SEVENTEEN cards on a
  SINGLE ring (radius modulated 239–310px, wider horizontally than
  vertically — a hand approximation of an arc-length-even ellipse),
  NOT a double ring.
- **Graph**: `fan-d17` (HUB + 17 spokes; dense-mode family, max_deg=17).
- **viewBox**: 2120×824.
- **Structural regularities** (measured):
  - HUB at the ring-card centroid (deviation 2/14px);
  - single ring, radius CV 0.081, azimuth CV 0.235 (gap oscillation
    inversely tracks the local radius — arc-length-even spacing);
  - minimum card rect-gap 6px (the pack floor of the whole fixture set);
  - no long edges (all spokes), total spoke length 4800px.
- **Design ruling it carries**: the former "k>=17 double ring is
  geometrically infeasible" prototype conclusion is REFUTED by this
  fixture — the binding constraint was the chord-based radius caliber,
  not the geometry. The engine now computes the box-aware minimal
  uniform radius (fan-d17: 303px vs the old chord caliber 414px) and
  keeps one ring across the whole n<=20 fan family.

## brand-flywheel-manual-layout.json

- **Origin**: exported via "Export layout" after jacky hand-dragged the
  nodes on the stdraw demo-2d interactive page (2026-11-16).
- **Graph**: `brand-flywheel` (Brand Asset Flywheel; 6-node ring-cycle
  certified family).
- **viewBox**: 488×480.
- **Structural regularities** (measured with the certificate formulas):
  - single ring covering all 6 nodes, chord spacing CV 0.0802,
    regular-polygon deviation 0.1197 — a hand-drawn GOOD ring;
  - the former uncalibrated 0.05 gates REJECTED this fixture itself
    (the same incident class as the fan azimuth caliber).
- **Caliber role**: good-ring anchor for the ring form battery
  (`ringlayout.RING_SPACING_CV_MAX / RING_TEMPLATE_FIT_MAX`,
  recalibrated 2026-11-16).

## random-n10-i05-manual-layout.json

- **Origin**: exported via "Export layout" after jacky hand-dragged the
  nodes on the stdraw demo-2d interactive page (2026-11-16). The graph
  is ring-detected (k=9 covering 9/10 nodes) whose engine trial fails
  (crossings leg) and falls back to layered — jacky dragged his own
  ring reading of it.
- **Graph**: `random-n10-i05` (random corpus, E/N=1.60).
- **viewBox**: 528×512.
- **Structural regularities** (measured): single 9-node ring, chord
  spacing CV 0.4626, regular-polygon deviation 0.6922 — the upper band
  of a freehand ring reading.
- **Caliber role**: migration/upper-band fixture for the ring form
  battery (together with brand-flywheel below the recalibrated gates).

## random-n10-i00-manual-layout.json

- **Origin**: exported via "Export layout" after jacky hand-dragged the
  nodes on the stdraw demo-2d interactive page (2026-11-16). The graph
  is spine-wing-detected (hub pair N06/N07) whose engine trial fails
  (hard-gate proxy) and falls back to layered.
- **Graph**: `random-n10-i00` (random corpus).
- **viewBox**: 568×528.
- **Structural regularities** (measured): the freehand reading shows NO
  constructed spine-wing geometry (spine axis deviation 115px, wing
  midline deviation 172px) — a human "shape is right" layout, not a
  constructed one.
- **Caliber role**: spine-wing migration evidence: the 2px constructed
  battery band stays engine-side (verified against classic-cld's own
  6px sample, unchanged); the fixture anchors the spine-wing
  reverse-form-gate face (detected -> trial failed -> form_fallback
  meta instead of a silent layered fallback).

## Historical incident (recurrence guard)

v0.7.1 (ref-scrubbed): the engine-side spine-wing layout had landed and was
structurally correct, but `demos/classic-cld-2d.html` and
`docs/gallery/*.png` had not been re-rendered with the engine, so jacky's
visual inspection saw the old ring-construct rendering and misjudged it as
"structurally inconsistent" (rework card ref-scrubbed, v0.7.2). Recurrence
guard: `tests/ci_checks.py` deliverable freshness check — demo-2d.html is
byte-compared against a fresh render by the current engine.
