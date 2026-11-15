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

## Historical incident (recurrence guard)

v0.7.1 (ref-scrubbed): the engine-side spine-wing layout had landed and was
structurally correct, but `demos/classic-cld-2d.html` and
`docs/gallery/*.png` had not been re-rendered with the engine, so jacky's
visual inspection saw the old ring-construct rendering and misjudged it as
"structurally inconsistent" (rework card ref-scrubbed, v0.7.2). Recurrence
guard: `tests/ci_checks.py` deliverable freshness check — demo-2d.html is
byte-compared against a fresh render by the current engine.
