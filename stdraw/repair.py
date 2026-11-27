# -*- coding: utf-8 -*-
"""Structured repair hints (T13): every FAIL in a certificate or a loop
audit carries an actionable, machine-readable suggestion — instead of a
bare False the agent gets {"gate", "edge"?, "hint", "retry"}.

The hints reference the DSL semantic hints (@main / @order / @pair, T14)
where those are the right lever, and the split-by-loops advice for graphs
near the size limit (T15). Hints are attached ONLY to failing entries:
every all-pass certificate/audit keeps its historical bytes byte-for-byte.
"""

# gate key -> hint text. Keys not listed fall back to GENERIC_HINT.
#
# Wording discipline (default memo 2026-11-26, grounded in the stdraw20
# manual-calibration lessons): for cv_le_035 / pitch_uniform /
# column_snap24_ge_060 / anchors_standard the hints must NOT push agents
# toward mechanical grid/anchor placement — those gates penalize
# human-style arrangements (measured: the former 16-anchor-set membership
# criterion blocked ~80% of manually calibrated drawings; since the
# 2026-11-26 criterion change anchors_standard = on-border + angle-met).
# Hints point to the semantic hints and the split-by-loops lever only.
# Gate thresholds and grade semantics are NOT touched by the wording layer.
GATE_HINTS = {
    "box_press_zero":
        "a line presses a card: reduce density — declare @main so the main "
        "structure centers, @order to band the loops, or split the graph by "
        "loops if it exceeds ~12 nodes",
    "edge_box_clear_ge_16":
        "an edge runs closer than 16px to an unrelated card: split the graph "
        "by loops, or use @pair to pull heavily-connected variables onto the "
        "same row",
    "anchors_smooth":
        "an edge depends too shallowly from its border anchor: re-run — "
        "anchor snapping is density-gated; splitting the graph by loops "
        "lowers density",
    "min_gap_ge_16":
        "cards closer than 16px: reduce the node count — split the graph by "
        "loops",
    "cv_le_035":
        "row spacing uneven: try @order to group loops into reading bands, "
        "or split the graph by loops",
    "pitch_uniform":
        "row pitch uneven: split the graph by loops, or declare @order so "
        "related loops share rows",
    "column_snap24_ge_060":
        "columns off the 24px snap: declare @pair on the variables that "
        "should align, or split the graph by loops",
    "mutual_pairs_separated":
        "a <-> bidirectional pair's two lines run closer than 4px: declare "
        "@pair for the two variables and simplify their shared neighbors",
    "mutual_pairs_closed":
        "a mutual pair did not close as a lens: declare @pair for the two "
        "variables; if the pair sits in a dense neighborhood, split the "
        "graph by loops",
    "lines_no_coincidence":
        "two lines coincide: use @order to band the loops that share those "
        "edges, or split the graph by loops",
    "anchors_standard":
        "an endpoint is off its box border or its arrival angle is too "
        "shallow (criterion: on-border + angle-met): re-run — anchor "
        "snapping is density-gated; splitting the graph by loops lowers "
        "density",
    "visual_crossings_zero":
        "lines cross mid-air: declare @main (center the main structure) and "
        "@order (reading order) to steer placement, or split the graph by "
        "loops",
    "lens_pairs_closed":
        "a lens did not close: declare @pair for the two variables of the "
        "open loop",
    "lens_pair_min_sep_ge_12":
        "two lenses closer than 12px: split the graph by loops",
    "loop_labels_clear":
        "a loop label collides with drawing: shorten the loop label, or "
        "re-run with --no-loop-labels (annotation layer off, gate recorded "
        "N/A honestly)",
    "delay_marks_clear":
        "a delay mark collides with drawing: move the @delay tag to a "
        "different edge of the loop",
    "topology_form_fallback":
        "structural form detected but abandoned (form misfit precedes every "
        "hygiene metric): try @main to steer mode detection, or accept the "
        "honest downgrade",
}
GENERIC_HINT = ("hard gate failed: re-run with the semantic hints @main / "
                "@order / @pair to constrain placement; near the size limit "
                "(>12 nodes) prefer splitting the graph by loops")



def certificate_repair_hints(gates: dict, scene: dict) -> list:
    """T13: one structured suggestion per failing hard gate.

    Scope caliber: only FAILING BOOLEAN GATES produce hints. Report items
    (crossings_zero / row_align_ge_060 / loop_edges_arced) are soft targets
    by ruling — not gate FAILs — and all-pass certificates must keep their
    bytes byte-for-byte (golden set is byte-pinned; re-blessing needs
    explicit authorization). Annotation dicts (dense_mode /
    planarization_deferred) are not gates. "edge" context is attached when
    the certificate scene carries it (visual crossing details). Empty list
    = caller omits the block (byte-identity).
    """
    hints = []
    for k, v in (gates or {}).items():
        if v is False:
            item = {"gate": k, "hint": GATE_HINTS.get(k, GENERIC_HINT),
                    "retry": True}
            hints.append(item)
    details = (scene or {}).get("visual_crossing_details") or []
    if details and isinstance(details[0], dict):
        a, b = details[0].get("a"), details[0].get("b")
        if a and b:
            for item in hints:
                if item["gate"] in ("visual_crossings_zero",
                                    "lines_no_coincidence"):
                    item["edge"] = f"{a}<->{b}"
                    break
    return hints


def hints_block(graph) -> dict:
    """T14 certificate record: which semantic hints this run declared and
    what each is expected to do. Emitted only when hints exist."""
    h = getattr(graph, "hints", None)
    if not h or h.empty():
        return {}
    mech = {}
    if h.main:
        mech["main"] = ("placement objective centering term on the main-loop "
                        "nodes (cp-sat) / centering shift (construct)")
    if h.order:
        mech["order"] = ("loops reordered to the reading sequence at pipeline "
                         "entry (loop audit listing, loop-arc scope, "
                         "annotation order follow)")
    if h.pairs:
        mech["pair"] = ("placement objective adjacency term for same-row "
                        "pairs (cp-sat) / adjacent packing (construct); "
                        "cross-row pairs are reported unapplied")
    return {
        "main": list(h.main),
        "order": list(h.order),
        "pairs": [[a, b] for (a, b) in h.pairs],
        "mechanism": mech,
        "note": ("DSL semantic hints (T14); the pixel parameters --pitch / "
                 "--hub-side / --column-order are deprecated"),
    }
