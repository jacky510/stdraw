# ADR-0008: Manual-layout certificate caliber: structural gates N/A + waypoint endpoint rule

- **Status**: Accepted 2026-11-13 (P1-2); T2 plan A approved with the manual loop-closure card

## Context

Manual layouts are graded honestly on the remaining gates; the
`--from-layout` manual calibration loop is a live asset (reconfirmed
2026-11-26), not legacy.

## Decision (rule in force)

Manual coordinates (`--from-layout`) are exempt from the two
automatic-pipeline structural checks (check.py 6a/9 caliber): layered-mode
gate slots read "N/A", are excluded from the pass count and never block;
the measured values stay in metrics. This is a caliber alignment, not a
threshold change. Additionally (T2, plan A): a waypoint edge endpoint = the
standard anchor nearest to the border point aimed at the first/last
waypoint; sibling-anchor conflicts resolve through anchor_snap's give-way
machinery.

## Original code annotations (verbatim, pre-migration)

Source: `stdraw/metrics.py:1048`

```
    lens = scene.get("lens") or {}
    # P1-2 (jacky 2026-11-13 ruling): manual coordinates (--from-layout) are
    # exempt from the two automatic-pipeline structural checks — same caliber
    # as check.py 6a/9 ("manual: N/A"). Layered-mode gate slots read "N/A";
```

Source: `stdraw/layout_auto.py:2507`

```
        A, B = nodes_px[a], nodes_px[b]
        # T2 caliber (plan A, jacky-approved): endpoint = the standard anchor
```


## Migration note

The personal-ruling annotations above were migrated here (verbatim) and replaced in code by the rule text plus a `docs/adr/ADR-0008` pointer, per the code-hygiene card (engine outputs unchanged; the only output string touched is the ADR-0016 certificate note).
