# stdraw DSL Draft v0.1

Status: M0 draft (minimal closed loop). Parser: `stdraw/dsl.py`, CLI: `python -m stdraw layout <file.cld>`.

## Design Principles

1. **Text in, certified diagram out** — the DSL is the input interface for an agent; a single `.cld` file yields the layout + quality certificate;
2. **Minimal closed loop**: variables / polarity edges / loop tags / grouping (optional), without borrowing semantics from M1+;
3. **Auditable semantics**: loop tags (`loop`) are not comments but verification targets of the lint layer (`stdraw/loops.py`) — closure + R/B polarity edge counting are verified per tag, cross-checked against an independent enumeration of all loops in the graph (in practice this has caught "declared loop does not close" and "wrong polarity tag");
4. **Tension between grouping and "relations decide layout"**: grouping is merely a semantic annotation; the M0 layout layer does **not** consume groups — layout is determined solely by relations (graph structure), with zero manual intent; automatic group derivation (community detection) belongs to M1+.

## Syntax

Line-oriented; `#` starts a comment; blank lines are ignored.

```
graph "图名"                              # optional, graph name (goes into the certificate)

var <id> "<标签>" [@value "<数值文本>"]     # variable (must be declared before use)
                 [@group <gid>]           # optional group membership
                 [@w <补余量px>]           # optional: measured padding for mixed-script titles (multiple of 2)

<a> -> <+|-> <b> [@loops <id1>,<id2>]      # polarity edge; @loops declares the loops this edge participates in

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
