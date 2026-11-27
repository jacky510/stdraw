# stdraw DSL Draft v0.1

Status: M0 draft (minimal closed loop). Parser: `stdraw/dsl.py`, CLI: `python -m stdraw layout <file.cld>`.

## Design Principles

1. **Text in, certified diagram out** — the DSL is the input interface for an agent; a single `.cld` file yields the layout + quality certificate;
2. **Minimal closed loop**: variables / polarity edges / loop tags / grouping (optional), without borrowing semantics from M1+;
3. **Auditable semantics**: loop tags (`loop`) are not comments but verification targets of the lint layer (`stdraw/loops.py`) — closure + R/B polarity edge counting are verified per tag, cross-checked against an independent enumeration of all loops in the graph (in practice this has caught "declared loop does not close" and "wrong polarity tag");
4. **Tension between grouping and "relations decide layout"**: grouping is merely a semantic annotation; the M0 layout layer does **not** consume groups — layout is determined solely by relations (graph structure), with zero manual intent; automatic group derivation (community detection) belongs to M1+.

## Syntax

Line-oriented; `#` starts a comment **outside quoted fields only** (a `#`
inside a quoted label is data); blank lines are ignored. Quoted fields
(graph name / labels / `@value` text) support the escapes `\"` and `\\`;
`dumps` emits the same escaping, so `parse(dumps(g)) == g` holds for
arbitrary label text. `validate()` rejects self-loops (`a -> + a`) and
duplicate directed edges (the same `(a, b)` pair twice; opposite-direction
mutual pairs remain legal).

```
graph "图名"                              # optional, graph name (goes into the certificate)

var <id> "<标签>" [@value "<数值文本>"]     # variable (must be declared before use)
                 [@group <gid>]           # optional group membership
                 [@w <补余量px>]           # optional: measured padding for mixed-script titles (multiple of 2)

<a> -> <+|-> <b> [@loops <id1>,<id2>]      # polarity edge; @loops declares the loops this edge participates in
                 [@anchors src=<aid>,dst=<aid>]   # optional per-end anchor designation (see Appendix C)

loop <id> "<标签>" "<R|B>" [<n1>, <n2>, ...]   # declare a loop: node sequence + expected type
group <gid> "<分组标签>"                   # optional group declaration
```

- Polarity: `+` same-direction change / `-` opposite-direction change (rendered as arrow coloring / hover label, decided by the viewer layer);
- The node sequence of `loop` is written in order along the cycle (closure is verified against that sequence on the tagged-edge subgraph);
- `R` = reinforcing loop (even number of negative-polarity tagged edges) / `B` = balancing loop (odd number) — lint warns when the declared type disagrees with the actual parity.

## Audit Rules (lint layer, runs automatically with every layout)

| # | Rule | Description |
|---|---|---|
| L1 | Loop closure | Uses only that loop's tagged edges; walks from the first node through all loop nodes back to itself (DFS ≤12 steps) |
| L2 | R/B polarity edge count | Parity of negative-polarity tagged edges ↔ matches the declared type |
| L3 | Tag existence | A declared loop has at least one edge carrying its tag; loops referenced by an edge must already be declared |
| L4 | Independent enumeration cross-check | Simple cycles of the whole graph (≤10 steps) enumerated independently; loops that exist but are not declared are reported as-is |

Audit conclusions go into `loops_audit.json`, and the issue list is printed at the same time; **the audit does not block layout** (semantic issues and layout quality are kept separate, but both go into the quality-layer report).

## Round-trip Consistency

`parse(dumps(g)) == g`: graph model → DSL text → graph model, field-by-field equal (deterministic serialization).

## Known Boundaries (not in M0, deferred to M1+)

- Stock/flow annotations;
- Delay markers (`||`) on edges;
- Automatic group derivation (community detection) and grouping consumed by layout;
- Multi-graph/subgraph, versioned schema.

## Appendix A. Edge delay marker `@delay`

An edge line may end with `@delay` (after the optional `@loops` tag list; the
two tags may appear in either order, each at most once):

```
a -> + b @loops R1,B1 @delay
b -> + a @delay @loops R1
```

`@delay` is a semantic marker (the effect takes time). The engine records it
on the edge (`delay: true`, written only when set) and draws a delay mark:
two short perpendicular ticks at the arc-length midpoint of the delivered
route. The mark is checked on the delivered coordinates (certificate gate
`delay_marks_clear`: every tick >= 16px from every card, crossing no other
line and no other mark). The canonical dump order is `@loops ... @delay`;
`parse(dumps(g)) == g` holds with and without delay markers. An unknown
token, a repeated `@delay` or a trailing token after the tags is rejected
with a DSL error.

## Appendix C. Per-end anchor designation `@anchors` (2026-11-26)

An edge line may carry `@anchors src=<aid>[,dst=<aid>]` (the three edge
tags `@loops` / `@anchors` / `@delay` may appear in any order, each at most
once; the canonical dump order is `@loops ... @anchors ... @delay` and
`parse(dumps(g)) == g` holds):

```
a -> + b @anchors src=s-g2,dst=n-g3     # both ends
b -> + c @anchors src=ne                # one end only
```

`<aid>` comes from the anchors.py vocabulary: side midpoints (`n` / `e` /
`s` / `w`), corners (`ne` / `se` / `sw` / `nw`), and numbered side slots
(`<side>-g<j>`, j = 1..7 at fixed context-free fractions — g1/g2 are the
legacy golden pair 0.382 / 0.618, g3 the side midpoint, g4/g5 the quarter
pair, g6/g7 the near-corner pair). The slot count a side actually uses is
adaptive (it follows the number of lines attached to that side); the
id -> coordinate mapping never depends on it, so ids stay unambiguous
across DSL, exports (`layout.json` `edges[].anchor_ids`), the interactive
manual-layout export (`edges[].anchors`) and the `--from-layout` replay.

A designation is a user intent, not a license: the designated endpoints
are frozen out of the repair passes, and a designation whose straight
delivery would breach a hard gate (box press / clearance / angle) falls
back to the engine's own delivery (reported on stderr, same accounting as
the `--from-layout` channel). Syntax errors (unknown id, duplicate key,
unknown token) are rejected with a DSL error.

## Appendix B. Semantic hints `@main` / `@order` / `@pair` (T14)

Line-oriented directives starting with `@` that declare layout INTENT at the
loop/variable level — the machine-consumable replacement for the deprecated
pixel parameters (`--pitch` / `--hub-side` / `--column-order`; see
docs/agent-interface.md):

```
@main R1          # main loop(s): the engine centers the declared structure
                  # (ring mode: forces the main-ring selection; layered mode:
                  # centering term in the placement objective)
@order R1,B1,R2   # loop reading order (the pipeline reorders the loop
                  # sequence; the loop audit listing, the loop-arc scope and
                  # the annotation order follow)
@pair a,b         # two variables that should sit adjacent (ring mode:
                  # consecutive ring slots; layered mode: adjacency term in
                  # the placement objective / adjacent packing)
```

- `@main` and `@order` take comma-separated loop ids (multiple `@main`
  lines accumulate); `@pair` takes exactly two variable ids (multiple lines
  accumulate). Referencing an undeclared loop/variable is a validation
  error;
- The certificate records the hints actually declared (`certificate.json`
  `hints` block: ids + the mechanism each hint feeds) — emitted only when
  hints exist, so hints-free graphs keep their bytes byte-for-byte;
- `dumps` emits the hints after the groups in the canonical order (`@main`
  lines, then `@order`, then `@pair` lines); `parse(dumps(g)) == g` holds
  with and without hints (property-tested in tests/test_dsl_hints.py);
- Cross-row `@pair` pairs cannot be adjacent and are reported unapplied
  (honest boundary).
