# -*- coding: utf-8 -*-
"""Size limits (T15): explicit, structured refusal instead of a costly
layout attempt that ends in an honest-but-late "uncertified".

Two boundaries (both ratified, see docs/agent-interface.md and
docs/validation-tiers.md):

  MAX_LAYOUT_NODES (15)   service limit for agent callers: the CLI refuses
                          to start the layout pipeline and returns a
                          structured refusal (refusal.json, exit code 3)
                          with a split-by-loops suggestion.
  HARD_CEILING_NODES (20) the engine capability ceiling (n<=20 scope
                          ruling). Even with the explicit validation-sweep
                          escape (--allow-oversize) nothing beyond 20 is
                          ever laid out; n30/n50 corpora are retired and
                          refused by design.

--allow-oversize exists ONLY for the byte-gate validation infrastructure
(benchmarks/tools/sweep_tiers.py tier A runs the CLI on the random-n20
corpus): it extends the service limit to the hard ceiling without changing
any output byte for the graphs it lets through.
"""

MAX_LAYOUT_NODES = 15
HARD_CEILING_NODES = 20


def size_refusal(graph, limit: int = MAX_LAYOUT_NODES,
                 ceiling: int = HARD_CEILING_NODES) -> dict:
    """Structured refusal payload (T15). Pure: reads the graph, returns a dict."""
    declared = [
        {"id": lp.id, "label": lp.label, "kind": lp.kind, "nodes": list(lp.nodes)}
        for lp in graph.loops
    ]
    out = {
        "rejected": True,
        "reason": "node_limit_exceeded",
        "limit": limit,
        "hard_ceiling": ceiling,
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "declared_loops": len(graph.loops),
        "advice": ("split the graph by loops: lay out each loop (or a small "
                   "bundle of tightly-coupled loops) as its own stdraw graph "
                   "and keep the shared variables consistent across the parts; "
                   "see docs/agent-interface.md"),
    }
    if declared:
        out["split_hint"] = {
            "note": "declared loops, one candidate split unit each",
            "loops": declared,
        }
    return out
