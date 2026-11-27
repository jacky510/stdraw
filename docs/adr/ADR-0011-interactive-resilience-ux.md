# ADR-0011: Interactive layer: fail-visible isolation, decluttered dots, endpoint hit-test and arc-freeze root fixes

- **Status**: Outage fixes v0.7.9 / v0.7.11; endpoint UX root fix 2026-11-12

## Context

All five items are interactive-layer behavior rulings from incident
reports and review feedback; the drag layer remains opt-in
(`--interactive`) since the 2026-11-25 reduction card, and `--from-layout`
replay stays a core deliverable.

## Decision (rule in force)

(a) One edge whose reroute/updateEdge throws must not kill the remaining
edges of a re-anchor pass - they would stay on stale anchors (the Edge
mixed floating-arrow outage). Degrade that edge visibly + console WARN,
keep going, self-heal on the next successful pass (v0.7.11).
(b) Browser-inflated DOM text overflows planned rects while edges stay
anchored -> floating arrows (the same outage family); the ACTUAL rendered
text is measured per card post-render and the rect grows (never shrinks) to
fit (v0.7.9).
(c) Dots in the rendered graph are visual noise: the visible endpoint
handle dot and the anchor dots are hidden by default; hover / drag /
toolbar toggle reveal them.
(d) Endpoint handles hard to grab: two compounding root causes (DOM-order
overlap arbitration + hit-band priority) fixed as a root fix.
(e) "Line jumps while dragging an endpoint": stale freeze base; fixed with
freezeArcBase re-sync at every gesture finalize.

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/_interactive_js.py:245`

```
// growth: coincident anchors, infeasible route) must not kill the remaining
// edges of a re-anchor pass — they would stay on stale anchors (jacky's Edge
// mixed floating-arrow outage, ref-scrubbed). Degrade that edge visibly (red
// dashed stroke) + console WARN, keep going, and self-heal the marker on the
```

Source: `stdraw/_interactive_js.py:793`

```
  // hit priority is structural (DOM order), pinned by the probe.
  // ref-scrubbed: the VISIBLE handle dot is hidden by default (jacky: dots in
  // the rendered graph are visual noise); it fades in only while its edge is
```

Source: `stdraw/_interactive_js.py:963`

```
// scale), the rendered label overflows the planned rect while the edges stay
// anchored to the planned border -> floating arrows (jacky's Edge outage,
// ref-scrubbed). Here the ACTUAL rendered text is measured per card
```

Source: `stdraw/_interactive_js.py:1030`

```
    // re-anchor round (stale anchors on all subsequent edges = the mixed
    // floating-arrow state jacky saw in Edge). Fail-visible per edge instead.
```

Source: `stdraw/_interactive_js.py:1351`

```
svg.appendChild(anchorLayer);
```

Source: `stdraw/_interactive_js.py:1436`

```
}
// ── 2026-11-12 endpoint hit-test root fix (jacky: endpoint handles hard to
```

Source: `stdraw/_interactive_js.py:1487`

```
  // accumulated divergence at once — the user-visible "line jumps while
  // dragging an endpoint" bug (jacky 2026-11-12 report, root cause: stale
```


## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0011` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
