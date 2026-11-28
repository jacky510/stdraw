# ADR-0020: Repair-hint `edge` tag — read the metrics detail rows (dead-code fix)

- **Status**: Accepted 2026-11-28

## Context

T13 promised a structured certificate repair hint of the shape
`{gate, edge?, hint, retry}`, where `edge` names a measured crossing so an
agent can act on the specific line pair instead of the whole drawing. In the
0.10.0 release the field was **never emitted**, for two independent reasons:

1. **Wrong host.** `repair.certificate_repair_hints(gates, scene)` read
   `scene["visual_crossing_details"]`, but the scans host that key inside the
   **metrics dict** (`metrics["visual_crossing_details"]`,
   `metrics["line_line_coincident_details"]`); the certificate scene only
   nests the whole dict as `scene["metrics"]`. The scene top level has never
   carried the key, so the detail lookup was always empty.
2. **Wrong detail shape.** Even with the host fixed, the extractor read
   `details[0]["a"] / ["b"]`. The scans emit
   `{"edges": ["u->v", "x->y"], "at": [x, y], "fan_pair": bool}` for
   crossings and `{"pair": ["u->v", "x->y"], "span_px": ..}` for
   coincidences — there is no `a` / `b` in either shape. The second bug was
   invisible while the first one made the branch unreachable.

`docs/agent-interface.md` documented `{gate, hint, retry}` (correct for what
the code produced); one release note promised `{gate, edge, hint, retry}`.

## Decision

- **ADR-0020-a — host**: the caller passes the metrics dict
  (`metrics.certificate_auto` → `certificate_repair_hints(g, metrics)`), and
  the builder reads the detail rows from that dict. Chosen over patching
  `scene` with a top-level copy of the key: the key is owned by the scan
  layer, the scene schema stays unchanged, and one copy cannot drift from
  the metrics row it was copied from. The change surface is one call site
  plus the builder body; no certificate field was added or removed.
- **ADR-0020-b — shape and vocabulary**: the tag is the first measured
  line of the first detail row, rendered `u<->v` with the direction dropped
  (the vocabulary the mutual-pair rows already use). Crossing rows contribute
  their `edges[0]`, coincidence rows their `pair[0]`. The full crossing list
  stays available in `metrics.visual_crossing_details` — the tag is a
  pointer-sized summary, not a second copy of the list.
- **ADR-0020-c — caliber: `edge` is mandatory for the two geometric gates,
  absent everywhere else.** The tag is attached to the hints of
  `visual_crossings_zero` and `lines_no_coincidence` only. Both gates fail
  **iff** their measured count is > 0, and the detail list is that count
  capped at 10, so a FAIL implies a non-empty list: no real certificate can
  produce a hint for these two gates without the tag. Other gates measure no
  line pair, so their hints never carry `edge` (a generic tag would be a
  fabricated fact). Gate thresholds and grade semantics untouched
  (ADR-0014).
- **ADR-0020-d — byte discipline unchanged**: only FAIL gates produce
  hints. An all-pass certificate keeps its bytes byte-for-byte; the golden
  archetype baseline is unmodified by this change.

## Consequences

- Agent callers can key on `edge` (`u<->v`, node ids) to fix the named line
  instead of re-reading the whole certificate.
- `certificate_repair_hints` takes the metrics dict now. Its second argument
  was never a public contract (it is an in-repo helper), and every caller in
  the tree passes a plain mapping.
- Regression cover: unit cases for both detail shapes and for "no tag on a
  non-geometric gate", plus an end-to-end certificate on a non-planar family
  whose `visual_crossings_zero` necessarily fails.
