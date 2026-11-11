# Grading Contract — single source of truth

This document is the **single source of truth** for stdraw's quality-grade
semantics. Hosts (CI pipelines, agent integrators) should link here instead
of copying grade tables into their own docs. The docs-consistency gate
(`scripts/check_docs_consistency.py`) verifies that the user-facing surfaces
(README.md / README_zh-CN.md / AGENTS.md / skills/stdraw/SKILL.md) stay in
sync with this contract.

Canonical facts are the CODE, never the prose:
- v2 grading: `certificate_auto()` in `stdraw/metrics.py` (caliber
  `v2-hardgates`, recipe `auto-v2`);
- v1 grading: `certificate()` in `stdraw/metrics.py` (caliber `v1-legacy`,
  recipe `ortho-v1`).

## 1. Grade tokens (what `certificate.json.grade` can contain)

| caliber | recipe | tokens emitted by the 2D pipeline |
|---|---|---|
| `v2-hardgates` | `auto-v2` | `best`, `uncertified` |
| `v1-legacy` | `ortho-v1` | `best`, `uncertified` (plus a retained legacy `second` branch, logically near-unreachable) |

`3d` is a **documentation-level tier** describing the 3D delivery path
(rotate freely; projection crossings solved by the camera): it does not
appear as a value of the 2D `certificate.json.grade` field.

`second` is **v1-legacy only**: the branch still exists in the v1 grading
code for byte-compatible regression, but it was removed from the v2
implementation in v0.7.15+ (logically unreachable). No document may present
`second` as a current tier of the auto-v2 recipe.

## 2. The two calibers are different rulers

Both calibers can emit `grade: "best"`, but the token means different
things under each. The certificate therefore self-describes (fields are
additive; consumers read `caliber` **before** interpreting `grade`):

| field | v1-legacy (ortho-v1) | v2-hardgates (auto-v2) |
|---|---|---|
| `recipe` | `ortho-v1` | `auto-v2` |
| `caliber` | `v1-legacy` | `v2-hardgates` |
| `placement` | `ortho-v1` | placement mode (ring-cycle / spine-wing / ...) |
| `grade_semantics` | grading formula, in the certificate | grading formula, in the certificate |
| `blocking_gates` | list of `false` gate keys | list of `false` gate keys |
| `deliverable` | always `false` (see §4) | reflects the delivery contract (CLI full deliverable: `true`) |
| `blocked_reason` / `blocked_by` | set (`D0`) | absent |
| gate count at `best` | 4 legacy gates | 11+ hard gates (placement-specific) |

Grading formulas:

- **v2-hardgates**: `best` = 0 line crossings AND all placement-specific
  hard gates AND `anchors_standard` AND `visual_crossings_zero` AND dual
  crossing accounting; everything else is `uncertified` (honest no-grade).
- **v1-legacy**: `best` = 0 crossings AND min card gap >= 16 AND spacing
  CV <= 0.35; `second` (legacy) = placement ok AND <= 2 crossings; else
  `uncertified`.

Host rule: **read `caliber` first, then `grade`.** A v1 `best` and a v2
`best` are not interchangeable claims; and a v1 output is never a
deliverable at all (§4).

## 3. Soft targets vs certificate gates (the caliber split)

"Crossings <= 2 acceptable" and "row alignment" describe the **layout
objective function** (report items / soft targets: when placement
regularity holds, <= 2 crossings may be tolerated — order and elegance
first). They are **not** certificate gates: the certificate-level `best`
requires 0 crossings under both calibers, and in v2
`visual_crossings_zero` is a hard gate. A figure laid out under the soft
target regime with 1-2 crossings is correctly `uncertified` — that is an
honest result, not a bug, and thresholds must never be tuned to change it.

## 4. D0 — vertical-orthogonal diagrams are banned as deliverables

Ruling D0 (jacky, 2026-11-11): **vertical-orthogonal (ortho-v1) output is
banned as a deliverable / publication / iframe embed / gallery screenshot.**
"Box-over-line everywhere, repeatedly unfixable."

Engineering basis (isolation, not repair):

- the visibility-representation layout declares `wires strictly vertical`
  and `occlusion allowed under cards` by design — unrelated wires passing
  underneath opaque cards are structural, not incidental;
- leader bars span nearly the full canvas width while edges degenerate to
  single-column `{a, b, x, y1, y2}` segments, so cause-and-effect tracing
  through the drawing is broken;
- the layout is byte-frozen for CI regression (production behavior pin),
  so any layout-level fix collides with the freeze — the defect is
  unfixable in place, hence the delivery-exit ban.

Consequently:

- `recipe=ortho-v1` / `caliber=v1-legacy` outputs carry
  `deliverable: false`, `blocked_reason`, `blocked_by: "D0"`, and the CLI
  prints a `[BANNED / D0]` notice;
- the frozen baseline itself stays in place for CI byte-regression
  (`tests/baselines/*.layout.json`, gate A) — the ban is on the **exit**,
  not on the recipe code or its regression data;
- enforcement: `scripts/check_no_ortho_delivery.py` (wired into
  `tests/ci_checks.py`) rejects any output directory that ships an `.html`
  page with vertical-orthogonal signals, using both certificate
  confessions (`caliber` / `recipe` / `deliverable`) and geometry
  fallbacks (`meta.method`, leader bars + single-x edges, "all lines
  strictly vertical") so stripped or hand-made products cannot bypass it.

## 5. Change rules

- Grading implementation, gate thresholds, and the token set change only
  via an explicitly authorized card (never to let a specific figure pass).
- This document is updated in the same change set as any doc that presents
  grading tiers; the docs-consistency gate fails on drift.
