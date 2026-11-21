# Edge-mirror feature: vertical-axis (left-right) symmetry of edges

Research card deliverable (definition only — no scorer/engine code changed).
Measurement script and raw results live in the local evidence tree
(`kanban/evidence/`, untracked by convention); the script path is referenced
at the bottom.

## Motivation

Operator aesthetic rules (2026-11-21):

1. The symmetric main shape is LEFT-RIGHT symmetric (vertical-axis mirror).
2. Beyond node symmetry, EDGES should mirror too — anchor choices, edge
   style, and routed paths — adding a sense of order.

This document defines the "edge mirror" feature strictly, so it can be
measured identically on human anchors and engine outputs.

## 1. Candidate node mirrors

A vertical mirror of a drawing is a permutation `sigma` of the node set with:

- **Involution**: `sigma(sigma(v)) = sigma(v) = v` for paired nodes and
  `sigma(v) = v` for fixed nodes (a mirror never 3-cycles nodes).
- **Graph automorphism** of the UNDIRECTED graph (direction/polarity is out
  of scope: an edge mirror pair is "edges whose endpoints mutually mirror";
  arrowheads are a separate semantic dimension). For every undirected edge
  `{u,v}`, `{sigma(u),sigma(v)}` is also an edge, and sigma is a bijection.
- **Geometry validity** (what makes it a *vertical* mirror and not just any
  symmetry):
  - y-preservation: every paired `(u, sigma(u))` has
    `|y_u - y_sigma(u)| <= tol`;
  - fitted axis: there EXISTS an axis `x = c` — fitted as the mean of all
    pair midpoints `(x_u + x_sigma(u))/2` and fixed-point abscissas — such
    that all of them lie within `tol` of `c`. The axis is NOT forced to the
    canvas mid-axis (real drawings are often not canvas-centered; e.g. a
    wide canvas with the drawing on the left).
- **Tolerance is adaptive, not canvas-relative**:
  `tol = SCALE_FRAC x s`, where `s` = median nearest-neighbour node
  distance of the drawing (the layout's own granularity; `SCALE_FRAC = 0.5`
  in the reference implementation). A large canvas with a small drawing
  must not loosen the tolerance — measured failure mode: with a
  canvas-diagonal tolerance, two stacked near-axis nodes 1 pitch apart were
  accepted as a "mirror pair".

Enumeration: backtracking over involutions with degree and y-preservation
pruning, exact automorphism verification of every complete candidate,
post-filter by fitted-axis spread `<= tol`. Complete over geometry-valid
candidates up to a documented state cap (`SEARCH_CAP = 500_000` expansions);
overflow flags `search_truncated = true` (never silent). Candidates with
zero mirror edge pairs are excluded (the identity is trivially "valid" but
carries no signal).

**Primary mirror** = the valid candidate whose fitted axis `c` is closest to
the canvas mid-axis `cx` (rule 1: symmetry is about the canvas); tie-break:
tighter axis spread, then more mirror pairs, then enumeration order. All
candidates are retained in the measurement output; consistency is reported
both for the primary and as the max over candidates (fan/star graphs have
many equally valid mirrors and tie-breaks must not fake a verdict).

## 2. Mirror edge pairs

For an edge `e = {u,v}` and the primary mirror `sigma`:

- `sigma(e) = {sigma(u), sigma(v)}`;
- if `sigma(e) = e` (both endpoints on the axis, or endpoints swapped) the
  edge is **self-mirrored** — it lies on the axis, is excluded from pairs,
  and is logged;
- otherwise `{e, sigma(e)}` is a **mirror edge pair**; pairs are disjoint
  (sigma is an involution).

`pair_coverage = |pairs| / |edges - self-mirrored|`.

## 3. Pair consistency

A mirror pair is evaluated on three dimensions. Each dimension can only
FAIL when it is evaluable; missing data is "non-evaluable", never a silent
pass of a violated check.

### 3.1 Anchor mirror (two sub-calibers)

Anchors are normalized through the engine's own anchor geometry
(`stdraw.anchors.standard_anchors`, 16 points: 4 edge midpoints, 4 corners,
2 golden points per side). String anchor ids compare at id level; coordinate
anchors (engine outputs `{a:[x,y], b:[x,y]}`) normalize to one of 8 x 45deg
compass sectors from the node centre (SVG y-down, n = up) and compare at
sector level.

Jacky's manual data exercises two readings of group anchors (g1/g2), so
both sub-calibers are reported:

- **golden** (geometric slot mirror, y-preserving): the mirror of an anchor
  id is the standard anchor at the x-mirrored canonical offset —
  `e<->w, n<->n, s<->s, ne<->nw, se<->sw, n-g1<->n-g2, s-g1<->s-g2,
  e-g1<->w-g2, e-g2<->w-g1`;
- **slot** (ordinal attachment slot): mirrored side, same slot index —
  `e-gk<->w-gk`, `n-gk<->n-gk`, `s-gk<->s-gk` (n/s map to themselves).

Per anchor endpoint (src, dst — after aligning the stored edge direction to
the mirrored direction `sigma(a) -> sigma(b)`, since mirror edges are often
stored reversed): both sides present -> equal/mismatch; one side missing ->
unknown (non-evaluable); both missing -> non-evaluable. The anchor
dimension FAILS the pair iff at least one endpoint mismatches.

### 3.2 Style mirror

Manual exports: style class equality (`None -> auto`;
`auto/straight/arc/free`). Engine outputs: route-kind equality
(`line/poly/polyline/vg/arc`). Mirror pairs never cross documents, so no
manual-to-engine style mapping is needed.

### 3.3 Path mirror (evaluable only when both edges carry points)

Mirror one polyline about the fitted axis `c` (`x -> 2c - x`), resample both
polylines to K points by arc length (K = 24), and require the mean L2
distance (minimum over both traversal directions) `<= tol_path`
(`TOL_PATH_FRAC = 0.05` x canvas diagonal). Evaluable only when BOTH edges
carry route/waypoint points; manual "Export layout" JSONs carry no path for
untouched edges, so this dimension is mostly engine-side.

### Pair verdict

`consistent(caliber)` = no evaluable dimension fails under that anchor
sub-caliber.

## 4. Graph-level feature keys (candidate names for a future scorer)

| key | meaning |
|---|---|
| `edge_mirror_presence` | 1 if >= 1 geometry-valid candidate with >= 1 pair |
| `edge_mirror_pair_coverage` | pairs / non-self-mirrored edges (primary mirror) |
| `edge_mirror_consistency` | mean pair consistency, golden anchor caliber |
| `edge_mirror_consistency_slot` | same, slot anchor caliber |
| `edge_mirror_best_consistency` | max consistency over all candidates |
| `edge_mirror_axis_offset` | fitted axis `c` minus canvas `cx`, px |

## 5. Parameters

| param | value | role |
|---|---|---|
| `SCALE_FRAC` | 0.5 | geometry tol = 0.5 x median nn node distance |
| `TOL_PATH_FRAC` | 0.05 | path mirror mean-distance tol (x canvas diagonal) |
| `SEARCH_CAP` | 500000 | automorphism enumeration state cap |
| `RESAMPLE_K` | 24 | polyline resampling for path mirror |

Reference implementation: `kanban/evidence/<research-card>/measure_edge_mirror.py`
(untracked evidence tree, card id withheld per the leak gate); raw per-graph
output: `edge-mirror-measurement.json` next to it. Sensitivity of mirror
presence to `SCALE_FRAC` in {0.35, 0.5, 0.75} is logged in the same JSON.
