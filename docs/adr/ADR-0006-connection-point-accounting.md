# ADR-0006: Connection-point accounting: fan spread, azimuth-monotone slot order, midband preference

- **Status**: Accepted 2026-11-06 (rule 3) / 2026-11-09 (slot-order rework); midband directive; second-review rejection

## Context

The original annotations carried the rule text plus the attribution; the
quote above is preserved verbatim. The fan-X legacy figures were fixed under
this caliber (entry-side slot ordering, occupied-slot give-way, bowtie
monotone slots).

## Decision (rule in force)

Rule 3: multiple outgoing lines on the same node must not pile up at the
same border midpoint - spread uniformly with a fixed step, clamped inside
the border. Rework: slot ORDER is azimuth-monotone (on t/b borders by the
other box center's horizontal offset, on r/l borders by its vertical
offset) so anchor order along the border always matches the targets'
positions. Midband directive: "the points where lines attach to boxes
should also prefer each border's midpoint; avoid the corners possible." A
first rework of the midband channel was REJECTED in the owner's second
review; the delivered design is the three-stage version (tier 0 baseline
accounting, tier 1 enhanced ladder, tier 2 joint detour).

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/routing.py:2124`

```
                2026-11-06 connection-point accounting hard rule 3 (jacky): multiple outgoing lines on the same node must not pile up at the
                same border midpoint -- spread uniformly with step FAN_STEP, clamped inside the border at +/-(half-3).
```

Source: `stdraw/routing.py:2126`

```
                2026-11-09 ref-scrubbed (jacky): slot ORDER is azimuth-monotone -- on t/b borders by the other box center's horizontal
                offset, on r/l borders by its vertical offset -- so anchor order along the border always matches the targets'
                left/right (top/bottom) positions (the former incidence-angle key could invert neighbours and produce a
                visible X crossing, classic-cld adopters box). After spreading, every
```

Source: `stdraw/routing.py:2871`

```
                jacky: "the points where lines attach to boxes should also prefer each border's midpoint; avoid the corners
                possible." The routing decision layer keeps the legacy exit geometry (candidate coverage unchanged); before delivery, this channel
                clamps out-of-band anchors along their own border tangent into the +/- 1/4 band -- corners are excluded wholesale (in-band anchors
                can never hug a corner). Per-edge hard-gate recheck (press/clearance/anchor angle/no crossing increase/mutual separation >= 4px).
```

Source: `stdraw/routing.py:2876`

```
                ref-scrubbed rework (rejected in jacky's second review): three stages --
                Tier 0 "baseline accounting": the original v0.7.2 semantics (endpoint clamping, ctrl untouched, the original hard-gate set)
                runs first and delivers on success (the guarantee that the other 18 graphs stay byte-for-byte identical to v0.7.2);
```

## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0006` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
