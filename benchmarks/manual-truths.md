# Manual truth fixtures — full inventory (Phase 0, v0.8.2 re-measure batch)

Purpose: single index of every human hand-drawn reference layout used as
ground truth by the engine's form batteries and regression tests. This file
lists **paths + provenance pointers only** — no coordinate copies (per the
copy discipline in `benchmarks/manual/README.md`; consumers must read the
fixture files themselves).

## In-repo fixtures (7)

| # | Fixture (path) | Graph | Origin (pointer) |
|---|---|---|---|
| 1 | `benchmarks/manual/classic-cld-manual-layout.json` | classic-cld-growth-and-burden (8n) | jacky hand-drag on demo-2d, "Export layout" (2026-11-06) — provenance + structural regularities: `benchmarks/manual/README.md` § classic-cld; consumed by `tests/test_layout_modes.py::TestSpineWingManualEquivalence` |
| 2 | `benchmarks/manual/fan-d12-manual-layout.json` | fan-d12 (HUB+11) | jacky hand-drag, export (2026-11-15) — `benchmarks/manual/README.md` § fan-d12; consumed by `tests/test_radial_manual_calibration.py` |
| 3 | `benchmarks/manual/fan-d17-manual-layout.json` | fan-d17 (HUB+17) | jacky hand-drag, export (2026-11-15); carries the single-ring k>=17 design ruling — `benchmarks/manual/README.md` § fan-d17 |
| 4 | `benchmarks/manual/brand-flywheel-manual-layout.json` | brand-flywheel (6n ring) | jacky hand-drag, export (2026-11-16); good-ring anchor for `ringlayout` gates — `benchmarks/manual/README.md` § brand-flywheel |
| 5 | `benchmarks/manual/random-n10-i00-manual-layout.json` | random-n10-i00 | jacky hand-drag, export (2026-11-16); spine-wing reverse-form-gate fixture — `benchmarks/manual/README.md` § random-n10-i00 |
| 6 | `benchmarks/manual/random-n10-i05-manual-layout.json` | random-n10-i05 | jacky hand-drag, export (2026-11-16); ring upper-band fixture — `benchmarks/manual/README.md` § random-n10-i05 |
| 7 | `tests/data/epidemic-feedback-manual-layout.json` | tests/data/epidemic-feedback.cld (10n/14e/5 loops) | hand-drawn 0-crossing layout — provenance: `tests/test_manual_gate_na.py` header; also consumed by `tests/test_ring_reposition.py` |

## Non-fixture manual artifacts (same dir, for provenance completeness)

- `benchmarks/manual/README.md` — the per-fixture provenance record (origins,
  measured structural regularities, v0.7.1 freshness incident + recurrence
  guard). This is the source of truth the table above points at.
- `benchmarks/manual/report-section-5b.md` — hand-maintained WS3-Q routing
  rework record (2026-11-06), edited into REPORT §5b by collect.py.

## Consumers (who reads these fixtures programmatically)

- `tests/test_layout_modes.py` (spine-wing equivalence, fixture #1)
- `tests/test_radial_manual_calibration.py` (radial battery, fixtures #2/#3)
- `tests/test_manual_layout.py`, `tests/test_manual_anchors.py`,
  `tests/test_manual_fallback_gates.py`, `tests/test_manual_gate_na.py`
  (manual closed-loop / gates, fixtures #1/#7)
- `tests/test_ring_reposition.py` (ring, fixtures #4/#5/#6/#7 contexts)

Count at inventory time (v0.8.2 re-measure branch): **7 fixtures**. Any new
hand-drawn export lands in `benchmarks/manual/` with a provenance section in
its README, then gets a row here.
