# API Stability & Deprecation Policy

Status: adopted 2026-11-18 closure batch (DeepSeek external-review follow-up:
define the semver boundary before promising anything; docs only, no code
change in this batch).

## Stable surface (semver-protected)

Breaking any of these requires a version bump that signals it (see cadence
below) and a CHANGELOG entry:

1. **DSL syntax** — the `.cld` grammar documented in
   `docs/dsl-spec-v0.1.md` (+ zh-CN edition). Additive grammar extensions are
   minor; anything that changes the meaning of existing input is breaking.
2. **CLI surface** — subcommands (`layout`, `layout-diff`), positional
   argument semantics, and every documented flag of
   `python -m stdraw`. New flags are minor; removing/renaming a flag or
   changing a documented default is breaking.
3. **Certificate schema** — the certificate JSON structure and gate/grade
   semantics documented in `docs/grading-contract.md`. Gate additions are
   minor when purely additive (new gate slots); changing a gate's meaning,
   thresholds-caliber, or removing slots is breaking.
4. **Manual-layout JSON contract** — the `--from-layout` input format
   (node id -> x,y + viewBox, optional `edges[].waypoints`), as produced by
   demo-2d.html "Export layout".
5. **Output file set** — the artifacts `--outdir` produces (layout.json,
   certificate, demo HTML). Adding a file is minor; removing or renaming one
   is breaking.

## Internal surface (may change in any release)

Everything not listed above: layout mode internals (mode decision chain,
per-mode placement math), CP-SAT placement internals, routing/polish
internals, rendering internals, and every field of `layout.json` `meta` not
covered by the certificate schema. Layout **byte-level** output is protected
separately by the frozen-baseline + byte-regression gate mechanism (the
retired ortho-v1 gate-A precedent; today byte stability is a
*per-frozen-artifact* contract, not a general semver promise — downstream
consumers needing byte stability pin concrete outputs and register drift per
`docs/consumer-repro.md`, the STDRAW_PIN protocol).

## Deprecation policy

1. Deprecations are announced in a **minor** release: CHANGELOG entry +
   doc note at the use site (CLI help / doc section).
2. Removal of a deprecated stable-surface item happens **no earlier than the
   next minor release** after the deannouncement during the 0.x series, and
   only in a **major** release after 1.0.
3. Frozen baselines (layout mode family posture per
   `docs/breadth-freeze-policy.md`) are never removed while the posture is
   in force — they stop evolving, they are not deleted. (The ortho-v1
   recipe baseline was an exception, removed by explicit owner ruling on
   2026-11-24 together with the recipe's external entry.)

## Cadence note (0.x reality)

The project is in 0.x. Until 1.0: a **minor** bump may carry stable-surface
breaks, but each such break must be called out as `BREAKING:` at the top of
the CHANGELOG entry; **patch** bumps never change the stable surface.
After 1.0 the standard semver reading applies (breaks = major only).
