# -*- coding: utf-8 -*-
"""Planarization candidate source (candidate-pool pipeline, M1-B).

Plan v1.3.1 section 7 M1-B + section 15(3): a planarization candidate for
near-planar graphs. Construction pipeline (exactly the card's chain):

  deletion-set enumeration  ->  embedding x outer-face enumeration  ->
  face-constrained drawing  ->  dual-variant re-insertion (A / B)

  1. Deletion sets: EVERY subset of core edges with |D| <= 2 whose removal
     makes the core planar. Edges of the loop model's PRIMARY loop are
     protected (loop-weight rule: the primary loop is never deleted). The
     enumeration is exhaustive up to preregistered resource caps (below),
     taken in deterministic (size, edge-index) order -- a resource rule,
     never a quality filter.
  2. Embedding x outer face: for each surviving D the planar subgraph G-D
     is laid out with the planar.py machinery (rotation system via
     networkx check_planarity on sorted insertion + face enumeration via
     PlanarLayout.faces_of + Even-Tarjan st-numbering + visibility
     representation). Outer-face choice = the directed st pair (s, t):
     enumerating both directions of every real edge covers every face of
     the embedding (either mirror) as the outer face.
  3. Face-constrained drawing: each (D, s, t) construction is finalized
     through the same row-compaction + pixel-packing stage as the ortho
     layer (all-integer coordinates, 2px grid).
  4. Dual-variant re-insertion: the deleted edges are evaluated as
     straight segments between card centers on each construction --
       variant A: lexicographic minimum of
         (number of crossings caused by re-inserted edges,
          the sorted tuple of crossing pair descriptors);
       variant B: minimum visual cost J_cross = sum of w(c) over those
         crossings c, where w(c) = LOOP_WEIGHT_PRIMARY (2) if either
         involved edge is a primary-loop edge, else LOOP_WEIGHT_OTHER (1).
     Per deletion set BOTH variants are emitted into the unified pipeline
     (when they pick the same construction, only A is emitted and the
     metadata records variant_b_same_construction=true -- no byte-identical
     duplicates).

Zero scoring power: the source never reads downstream quality metrics
(crossing counts here are a CONSTRUCTION parameter for the re-insertion
variants prescribed by the plan, computed before any candidate exists in
the pipeline). Emission caliber: each deletion set enumerates up to
PLANAR_MAX_ST_PER_SET face constructions at the CONSTRUCTION layer; per the
plan's dual-variant rule the best A (plus the best B when it picks a
DIFFERENT construction) is emitted into the unified pipeline -- the A/B
selection is a prescribed construction definition, not a downstream-quality
filter; the per-source generation quota of the orchestrator applies
unchanged as the preregistered structural cap.

Determinism: every iteration is over sorted structures; positions are
integers; no timestamps, no absolute paths. The embedding probe inserts
nodes/edges in sorted order -- measured identical rotation systems across
PYTHONHASHSEED 0/1/2/12345 on the K5-e / K3,3-e / Petersen families; the
all-directed-edge outer-face enumeration is invariant to the embedding's
mirror, so the emitted candidate set does not depend on which of the
embedding's mirrors the probe returns.

Preregistered resource caps (never wall-clock, never quality):
  PLANAR_MAX_DELETE = 2                  (plan scope)
  PLANAR_MAX_DELETION_SETS = 4           (first sets in enumeration order)
  PLANAR_MAX_ST_PER_SET = 12             (first viable (s, t) per set)
"""
from itertools import combinations

from .candidate_contract import LayoutCandidate

PLANAR_MAX_DELETE = 2
PLANAR_MAX_DELETION_SETS = 4
PLANAR_MAX_ST_PER_SET = 12
LOOP_WEIGHT_PRIMARY = 2
LOOP_WEIGHT_OTHER = 1


class PlanarProbeUnavailable(Exception):
    """Topological non-trigger of the planarization source."""


# ---- topology probes -------------------------------------------------------

def _core(edges):
    """(nodes, sorted edge tuples) of the core (degree >= 1)."""
    nodes = sorted({v for e in edges for v in e})
    return nodes, sorted(tuple(sorted(e)) for e in edges)


def _is_planar(nodes, edges):
    import networkx as nx
    g = nx.Graph()
    g.add_nodes_from(nodes)
    g.add_edges_from(edges)
    return nx.is_planar(g)


def core_is_planar(edges) -> bool:
    nodes, core_edges = _core(edges)
    if not core_edges:
        return True
    return _is_planar(nodes, core_edges)


def primary_loop_edge_set(analysis) -> frozenset:
    """Edges (frozensets) of the loop model's PRIMARY loop -- the protected
    set of the loop-weight rule. Empty when there is no primary loop."""
    loop = getattr(getattr(analysis, "loop_model", None), "primary_loop",
                   None)
    if loop is None:
        return frozenset()
    nodes = list(loop.nodes)
    out = set()
    for i in range(len(nodes)):
        out.add(frozenset((nodes[i], nodes[(i + 1) % len(nodes)])))
    return frozenset(out)


def planar_deletion_sets(edges, protected=frozenset(),
                         max_delete=PLANAR_MAX_DELETE,
                         cap=PLANAR_MAX_DELETION_SETS):
    """All edge subsets (size 1..max_delete) whose removal makes the core
    planar, protected edges excluded, in deterministic (size, index-tuple)
    order, capped by a preregistered resource rule. Returns
    (list_of_sorted_edge_tuples, capped_flag)."""
    nodes, core_edges = _core(edges)
    if not core_edges:
        return [], False
    deletable = [e for e in core_edges if frozenset(e) not in protected]
    found, capped = [], False
    for size in range(1, max_delete + 1):
        for combo in combinations(deletable, size):
            if len(found) >= cap:
                capped = True
                return found, capped
            kept = [e for e in core_edges if e not in combo]
            if _is_planar(nodes, kept):
                found.append(tuple(sorted(combo)))
    return found, capped


# ---- construction-stage re-insertion metrics -------------------------------

def _orient(o, a, b):
    v = (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    return (v > 0) - (v < 0)


def _segments_cross(p1, p2, p3, p4):
    """Strict proper crossing (integer-exact); shared endpoints and
    collinear overlaps are not crossings."""
    d1, d2 = _orient(p3, p4, p1), _orient(p3, p4, p2)
    d3, d4 = _orient(p1, p2, p3), _orient(p1, p2, p4)
    return d1 * d2 < 0 and d3 * d4 < 0


def reinsertion_crossings(positions, all_edges, deleted):
    """Crossings caused by the re-inserted (deleted) edges, drawn as
    straight segments between card centers. Returns the list of sorted
    crossing pair descriptors (each: (edge_a, edge_b) with edge_a < edge_b);
    a descriptor pair contains at least one deleted edge; pairs sharing an
    endpoint are exempt (same exemption as the certificate metric)."""
    deleted_set = {tuple(sorted(e)) for e in deleted}
    segs = {e: (positions[e[0]], positions[e[1]]) for e in all_edges}
    order = sorted(all_edges)
    hits = []
    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            e1, e2 = order[i], order[j]
            if e1 not in deleted_set and e2 not in deleted_set:
                continue
            if set(e1) & set(e2):
                continue                      # shared endpoint exemption
            if _segments_cross(*segs[e1], *segs[e2]):
                hits.append((e1, e2))
    return sorted(hits)


def variant_keys(hits, primary_edges):
    """(A_key, B_cost): A = (count, sorted descriptor tuple) lexicographic;
    B = J_cross = sum of w(c) with the loop-weight rule."""
    a_key = (len(hits), tuple(hits))
    j = 0
    for e1, e2 in hits:
        primary = (frozenset(e1) in primary_edges
                   or frozenset(e2) in primary_edges)
        j += LOOP_WEIGHT_PRIMARY if primary else LOOP_WEIGHT_OTHER
    return a_key, j


# ---- source runner ---------------------------------------------------------

def run_planarized(ctx):
    """Construction core of the 'planarized' source. Returns a list of
    (pos, y, meta, cost) tuples (may be empty -> caller raises
    SourceUnavailable with the recorded reason). Raises PlanarProbeUnavailable
    for topological non-triggers."""
    edges = sorted(tuple(sorted(e)) for e in ctx.edges)
    nodes, core_edges = _core(edges)
    if not core_edges:
        raise PlanarProbeUnavailable("no core edges")
    if _is_planar(nodes, core_edges):
        raise PlanarProbeUnavailable("core already planar")
    protected = primary_loop_edge_set(ctx.analysis)
    sets, capped_sets = planar_deletion_sets(core_edges, protected)
    if not sets:
        raise PlanarProbeUnavailable(
            "no deletion set of size <= "
            f"{PLANAR_MAX_DELETE} restores planarity")

    from .model import Edge, Graph, Node
    from .planar import LayoutConfig, PlanarLayout

    emitted = []
    for di, deleted in enumerate(sets):
        deleted_set = set(deleted)
        kept = [e for e in core_edges if e not in deleted_set]
        sub = Graph(
            name="planarized-probe",
            nodes=[Node(id=v, label=v) for v in nodes],
            edges=[Edge(a=a, b=b, polarity="+") for a, b in kept])
        # Construction caliber = evaluation caliber: the visibility layout's
        # card metrics must match what the pipeline's stage-1 gate measures
        # (ctx.card_h from the auto text metrics; row/column clearance from
        # cfg.min_gap). The planar module's own defaults (card_h=42,
        # pitch=56, gap 8) describe the ortho face only -- reusing them here
        # produced candidates structurally eliminated by the card-gap gate
        # (measured min_card_gap=12 < 16 on every trigger graph). This only
        # parameterizes the CONSTRUCTION: planar.py defaults (the ortho-v1
        # frozen path) are untouched.
        min_gap = getattr(ctx.cfg, "min_gap", 16)
        lc = LayoutConfig(
            card_h=ctx.card_h,
            pitch=ctx.card_h + min_gap,   # inter-row gap = min_gap exactly
            card_gap=min_gap,
            gap_col=min_gap,
        )
        pl = PlanarLayout(sub, lc)
        try:
            rot, dummy = pl.augment(pl.build_rotation())
        except Exception as e:                 # honest construction failure
            raise PlanarProbeUnavailable(
                f"embedding failed for deletion set {di}: "
                f"{type(e).__name__}: {e}") from e
        primary_edges = protected
        all_edges_for_hits = kept + list(deleted)
        best_a = best_b = None                # (key, index, positions)
        used = 0
        for a, b in pl.edges:                 # real edges of G-D
            for s, t in ((a, b), (b, a)):
                if used >= PLANAR_MAX_ST_PER_SET:
                    break
                st1 = pl._stage1_candidate(rot, s, t)
                if not st1:
                    continue
                try:
                    r = pl._stage2_candidate(rot, dummy, s, t,
                                             st1[0], st1[1], st1[2])
                    v4 = pl.stage3(r[5], r[9], r[7])
                except AssertionError:
                    continue
                used += 1
                pos = {v: (int(n["x"]), int(n["y"]))
                       for v, n in sorted(v4["nodes"].items())}
                hits = reinsertion_crossings(pos, all_edges_for_hits,
                                             deleted)
                a_key, j = variant_keys(hits, primary_edges)
                cand_key_a = (a_key, used, pos)
                cand_key_b = (j, a_key, used, pos)
                if best_a is None or cand_key_a[:2] < best_a[:2]:
                    best_a = cand_key_a
                if best_b is None or cand_key_b[:3] < best_b[:3]:
                    best_b = cand_key_b
            if used >= PLANAR_MAX_ST_PER_SET:
                break
        if best_a is None:
            continue                          # no viable construction: skip
        for variant, best in (("A", best_a), ("B", best_b)):
            best_used = best[1] if variant == "A" else best[2]
            if variant == "B" and best_used == best_a[1]:
                continue                      # same construction as A
            pos = best[-1]
            hits = reinsertion_crossings(pos, all_edges_for_hits, deleted)
            a_key, j = variant_keys(hits, primary_edges)
            meta = {
                "engine": "planarized-visibility",
                "variant": variant,
                "deleted_edges": [list(e) for e in deleted],
                "deletion_set_index": di,
                "reinsert_crossings": a_key[0],
                "j_cross": j,
                "constructions_enumerated": used,
                "deletion_sets_capped": capped_sets,
                "st_per_set_capped": used >= PLANAR_MAX_ST_PER_SET,
                "primary_loop_protected": sorted(
                    sorted(e) for e in protected) if protected else [],
                "internal_filter": "none",
            }
            cost = (len(nodes) + len(core_edges) + 2 * len(deleted) + used)
            emitted.append((pos, {v: pos[v][1] for v in nodes}, meta, cost))
        if best_b is not None and best_b[2] == best_a[1]:
            # stamp the honest merge note on A's metadata
            for item in emitted:
                if item[2]["deletion_set_index"] == di \
                        and item[2]["variant"] == "A":
                    item[2]["variant_b_same_construction"] = True
    return emitted


def planarized_candidates(ctx, seq: int = 0):
    """Adapter to the LayoutCandidate contract. Returns all variant
    candidates (the orchestrator applies its preregistered quota)."""
    out = []
    for k, (pos, y, meta, cost) in enumerate(run_planarized(ctx)):
        out.append(LayoutCandidate(
            candidate_id=f"planarized:{seq + k:03d}",
            source="planarized",
            node_positions={v: pos[v] for v in sorted(pos)},
            metadata=meta,
            generation_cost=cost))
    return out
