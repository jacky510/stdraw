# -*- coding: utf-8 -*-
"""Anchor-prior retrieval (anchors-as-prior candidate generation, S1).

Layer 1 family gate + Layer 2 in-family layout-feature distance, per
docs/proposals/anchor-prior-candidate-generation.zh.md section 1:

  - Layer 1 (family gate): reuse the SAME detect_* structural analyzers the
    auto-v2 mode chain and the candidate template sources use (zero new
    features).  A preregistered priority order maps the fired-detector set to
    one canonical family key; the same function is applied to the input graph
    and (at library build time) to every anchor's graph, so both sides share
    one vocabulary.  Detection is a topological fact -- no thresholds.
  - Layer 2 (in-family distance): single-source feature rows from
    stdraw.features (via the aesthetic scorer's thin normalized-caliber
    layer -- the same extractor/keys as everywhere else; this module never
    re-implements geometry).  Equal weights (preregistered starting point;
    any non-equal weighting must first pass 18-anchor LOGO calibration).
    Per-key robust z-scale (median / IQR) comes from the anchor library
    itself; the hit threshold is auto-derived from the should-hit
    (same-family anchor-to-anchor) vs should-not-hit (anchor vs
    negatives-library) distributions and lives in the library sidecar file
    -- never in code constants.

Honest failure modes (section 1.1): the retrieval cannot save families the
library does not cover.  Every non-hit is explicit: the caller records
``anchor_hit=null`` with a reason (``family-unmatched`` when the family gate
finds no anchors, ``no-anchor-within-threshold`` when the closest anchor is
beyond the calibrated threshold, ``library-unavailable`` / ``row-not-
evaluable`` for degraded inputs).  Silence is not an option.

The library is DATA (stdraw/data/anchor-features.json, packaged with the
wheel, only-add): anchors are jacky's hand-drawn layouts and their
precomputed feature rows; the code never embeds anchor coordinates or
thresholds.
"""
import json
import math
from pathlib import Path

from . import _datafiles
from .aesthetic_score import scalars_for_layout

LIBRARY_SCHEMA = "stdraw.anchor-library/1"
CALIBER = "normalized"

# Default sidecar location: packaged runtime data (stdraw/data/, resolved
# via importlib.resources so pip installs and git clones behave identically).
# Candidate-v1 only; absence degrades honestly (provenance records it)
# instead of raising.
_DEFAULT_LIBRARY = _datafiles.data_file("anchor-features.json")

# Minimum evaluable key share for a distance to count as evaluable
# (three-state discipline: below this the distance is "not evaluable",
# never zero).  Preregistered constant.
MIN_EVALUABLE_KEY_SHARE = 0.5


# ---------------------------------------------------------------- family gate

def family_of_graph(graph, edges):
    """Canonical family key of a graph via the shared detect_* analyzers.

    ``graph`` is a parsed DSL graph model; ``edges`` the sorted undirected
    edge tuple.  Returns the family key or None when nothing fires (the
    family-unmatched degradation case -- chains and the round-3 topologies
    land here by design).  A detector raising is treated as not fired and
    recorded in the returned trace (fail-visible, not swallowed).
    """
    trace = {}
    if not core_is_planar(edges):
        return "nonplanar", {"nonplanar": True}
    checks = (
        ("comb", _detect_comb),
        ("bowtie", _detect_bowtie_vertex),
        ("bowtie", _detect_bowtie),
        ("fan", _detect_radial),
        ("ring", _detect_ring),
        ("hub", _detect_spine_wing),
        ("column", _detect_column),
    )
    for fam, fn in checks:
        try:
            if fn(graph) is not None:
                return fam, {fn.__name__: True}
        except Exception as exc:  # noqa: BLE001 - honest per-detector record
            trace[fn.__name__] = "error:%s" % type(exc).__name__
    return None, trace


def _detect_comb(graph):
    from . import comblayout
    why = {}
    plan = comblayout.detect_comb(graph, why=why)
    return plan


def _detect_bowtie_vertex(graph):
    from . import bowtielayout
    why = {}
    return bowtielayout.detect_bowtie_vertex(graph, why=why)


def _detect_bowtie(graph):
    from . import symlayout
    why = {}
    return symlayout.detect_bowtie(graph, why=why)


def _detect_radial(graph):
    from . import radellayout
    why = {}
    return radellayout.detect_radial(graph, why=why)


def _detect_ring(graph):
    from . import ringlayout
    why = {}
    return ringlayout.detect_ring(graph, why=why)


def _detect_spine_wing(graph):
    from . import spinewinglayout
    why = {}
    return spinewinglayout.detect_spine_wing(graph, why=why)


def _detect_column(graph):
    from . import columnlayout
    why = {}
    return columnlayout.detect_column(graph, why=why)


def core_is_planar(edges):
    from .candidate_planar import core_is_planar as _cip
    return _cip(edges)


# ------------------------------------------------------------------- library

def load_library(path=None):
    """Load the anchor library sidecar (data, only-add).  Returns None when
    absent/mismatched -- the caller records the degradation honestly."""
    p = Path(path) if path is not None else _DEFAULT_LIBRARY
    try:
        doc = json.loads(_datafiles.read_text(p))
    except OSError:
        return None
    if doc.get("schema") != LIBRARY_SCHEMA:
        return None
    doc["_path"] = str(p)
    return doc


# ------------------------------------------------------------------ distance

def _z(row, key, center, scale):
    v = row.get(key)
    if v is None:
        return None
    if scale <= 1e-12:
        return 0.0 if abs(float(v) - center) <= 1e-12 else None
    return (float(v) - center) / scale


def feature_distance(row_a, row_b, retrieval):
    """Equal-weight robust-z distance over the library's preregistered key
    subset.  Returns (distance, n_evaluable, n_keys) -- the caller applies
    the MIN_EVALUABLE_KEY_SHARE three-state rule."""
    keys = retrieval["feature_keys"]
    centers = retrieval["key_centers"]
    scales = retrieval["key_scales"]
    acc, n = [], 0
    for k in keys:
        za = _z(row_a, k, centers[k], scales[k])
        zb = _z(row_b, k, centers[k], scales[k])
        if za is None or zb is None:
            continue
        acc.append(abs(za - zb))
        n += 1
    if not acc:
        return None, 0, len(keys)
    return math.fsum(acc) / len(acc), n, len(keys)


# ----------------------------------------------------------------- retrieval

def retrieve(graph, edges, baseline_doc, library):
    """Anchor retrieval for one input graph.

    ``baseline_doc`` is the deterministic baseline layout of the input graph
    (the incumbent auto delivery -- behavior frozen).  Returns a provenance
    dict; ``anchor_hit`` is the matched anchor key or None (with ``reason``).
    """
    if library is None:
        return {"anchor_hit": None, "reason": "library-unavailable",
                "family": None, "family_trace": {}}
    fam, trace = family_of_graph(graph, edges)
    anchors = library["anchors"]
    pool = {k: a for k, a in sorted(anchors.items())
            if a.get("family") == fam}
    if fam is None or not pool:
        return {"anchor_hit": None, "reason": "family-unmatched",
                "family": fam, "family_trace": trace}
    retrieval = library["retrieval"]
    threshold = retrieval["hit_threshold"]
    try:
        row_in = scalars_for_layout(baseline_doc, CALIBER)
    except Exception as exc:  # noqa: BLE001 - honest degradation
        return {"anchor_hit": None, "reason": "row-not-evaluable",
                "family": fam, "detail": "%s: %s" % (type(exc).__name__, exc),
                "family_trace": trace}
    scored = []
    for key, a in pool.items():
        d, n, nk = feature_distance(row_in, a["scalars"], retrieval)
        share = (n / nk) if nk else 0.0
        scored.append({"anchor": key, "distance": d, "evaluable_share":
                       round(share, 6)})
    evaluable = [s for s in scored
                 if s["distance"] is not None
                 and s["evaluable_share"] >= MIN_EVALUABLE_KEY_SHARE]
    best = min(evaluable, key=lambda s: (s["distance"], s["anchor"])) \
        if evaluable else None
    if best is None or best["distance"] > threshold:
        return {"anchor_hit": None, "reason": "no-anchor-within-threshold",
                "family": fam, "family_trace": trace,
                "threshold": threshold,
                "candidates": sorted(scored, key=lambda s: s["anchor"])}
    anchor = anchors[best["anchor"]]
    same_graph = (sorted(edges) == sorted(tuple(e) for e in
                                          anchor["graph_edges"])
                  and sorted(graph.node_ids()) == sorted(anchor["graph_nodes"]))
    return {
        "anchor_hit": best["anchor"],
        "reason": "hit",
        "mode": "anchor-replay" if same_graph else "anchor-seeded",
        "family": fam,
        "family_trace": trace,
        "anchor_path": anchor["path"],
        "distance": round(best["distance"], 6),
        "threshold": threshold,
        "evaluable_share": best["evaluable_share"],
        "candidates": sorted(scored, key=lambda s: s["anchor"]),
    }
