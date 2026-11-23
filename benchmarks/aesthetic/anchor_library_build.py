#!/usr/bin/env python
"""Build the anchor-prior library sidecar (anchors-as-prior S1, data only).

One-shot precompute per docs/proposals/anchor-prior-candidate-generation
section 1.2: every anchor's stored layout gets the SAME feature extraction
as any other layout (single source stdraw.features via the aesthetic
scorer's normalized-caliber thin layer), and the hit threshold is derived
from two deterministic distributions:

  should-hit    distances between same-family anchor pairs (leave-one-out
                spirit: each anchor is matched against the REST of the
                library; self and same-graph twins excluded from the hit
                distribution's "other anchor" side only by identity, they
                are the easy tail and reported as-is)
  should-not-hit distances between each anchor and each of the 40
                negatives-library engine deliveries

Threshold rule (preregistered, exported with the distributions):
  midpoint between hit-P90 and not-hit-P10 when the distributions are
  separated (hit_p90 < not_p10); otherwise the distributions overlap and
  the conservative hit-P95 is exported with an explicit "overlapping"
  flag so consumers can see the weaker calibration.

The sidecar is a DATA file (benchmarks/manual/anchor-library/, only-add):
anchors are jacky's hand-drawn layouts; coordinates travel verbatim from
the committed anchor files, nothing is invented here.

Read-only on the committed corpus: nothing outside the sidecar file is
written.  Deterministic: sorted iteration, math.fsum, no wall-clock.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "benchmarks" / "aesthetic"))

import diagnose_collapse as dc  # noqa: E402  (merge caliber + helpers)
import calibrate_v1 as c1  # noqa: E402  (FAMILY_MAP / NEGATIVE_DIR / collect)
import calibrate_v2 as c2  # noqa: E402  (positive sweep + GRAPH_ALIAS)
from stdraw import dsl  # noqa: E402
from stdraw.anchor_prior import CALIBER, LIBRARY_SCHEMA, family_of_graph
from stdraw.aesthetic_score import graph_name_of, scalars_for_layout  # noqa: E402

OUT = REPO / "benchmarks" / "manual" / "anchor-library" / "anchor-features.json"

# The 18th anchor lives with the preference-pool candidates (it entered the
# library with the pool); the other 17 come from the committed positive dirs
# via the proven merge caliber.
EXTRA_ANCHOR = REPO / "benchmarks" / "aesthetic" / "pref-synthetic" / \
    "candidates" / "epidemic-feedback-manual-layout-human.json"


def load_anchor_corpus():
    """18 hand anchors, edge-completed with the committed merge caliber.

    Deliberately NOT dc.load_corpus: the shared loader sweeps every *.json
    under benchmarks/manual and currently chokes on the pairwise annotation
    sessions (answers/candidates/questions carry no layout and no graph
    source).  This loader keeps the SAME merge caliber but filters to
    kind == "manual-layout" documents -- the actual hand anchors.  (The
    shared-loader breakage is reported upstream; not fixed in this card.)
    """
    labels = dc.load_family_labels(str(c1.FAMILY_MAP))
    neg_docs, engine_by_graph = [], {}
    for p in c1.collect(c1.NEGATIVE_DIR):
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        neg_docs.append((str(p), d))
        g = d.get("graph") or dc.graph_name_of(str(p))
        engine_by_graph.setdefault(g, d)
    source_docs = c2.load_graph_source_docs()
    known_names = set(engine_by_graph) | set(labels) | set(source_docs)
    pos_docs = []
    for d_ in c1.POSITIVE_DIRS:
        for p in c2.collect_positive_files(d_):
            with open(p, "r", encoding="utf-8") as f:
                doc = json.load(f)
            if not isinstance(doc, dict) or doc.get("kind") != "manual-layout":
                continue
            stem = dc.graph_name_of(str(p))
            g = doc.get("graph")
            if g not in known_names:
                if stem in known_names:
                    g = stem
                else:
                    base = stem or g or "#"
                    cands = sorted(k for k in known_names
                                   if k.startswith(base + "-"))
                    g = cands[0] if len(cands) == 1 else (g or stem)
            g = c2.GRAPH_ALIAS.get(g, g)
            doc = dict(doc)
            doc["graph"] = g
            eng = engine_by_graph.get(g) or source_docs.get(g)
            doc = dc.merge_layout_edges(doc, eng, backfill_loop_meta=True)
            pos_docs.append((str(p), doc))
    assert len(pos_docs) == 17, len(pos_docs)
    return labels, pos_docs, neg_docs, engine_by_graph, source_docs

# Anchor -> graph source resolution (data table; the fan graphs are
# synthesized HUB+spokes DSLs, mirroring the committed radial calibration
# fixture construction -- no .cld file exists for them).
CLASSIC_DIR = REPO / "benchmarks" / "corpus" / "classic"
RANDOM_DIR = REPO / "benchmarks" / "corpus" / "random"
BATCH2_SOURCES = REPO / "benchmarks" / "manual" / "jacky-batch2" / "sources"


def _fan_dsl(k):
    s = 'graph "fan-d%d"\n\n' % (k + 1)
    s += "".join('var L%02d "L%02d"\n' % (i, i) for i in range(k))
    s += 'var HUB "HUB"\n\n'
    s += "".join("HUB -> + L%02d\n" % i for i in range(k))
    return s


def graph_source_of(graph):
    if graph.startswith("fan-d"):
        k = int(graph.split("fan-d")[1]) - 1
        return dsl.parse(_fan_dsl(k)), "synthesized HUB+%d spokes" % k
    for base in (CLASSIC_DIR, RANDOM_DIR, BATCH2_SOURCES,
                 REPO / "tests" / "data"):
        p = base / (graph + ".cld")
        if p.exists():
            return dsl.parse(p.read_text(encoding="utf-8")), \
                str(p.relative_to(REPO))
    raise SystemExit("no graph source for anchor graph %r" % graph)


def median(vals):
    v = sorted(vals)
    n = len(v)
    if n == 0:
        return None
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def quantile(vals, q):
    v = sorted(vals)
    if not v:
        return None
    pos = q * (len(v) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(v) - 1)
    frac = pos - lo
    return v[lo] * (1.0 - frac) + v[hi] * frac


def main():
    labels, pos_docs, neg_docs, engine_by_graph, source_docs = \
        load_anchor_corpus()
    assert len(neg_docs) == 40, len(neg_docs)

    # append the pool-side epidemic anchor with the same merge caliber
    extra_raw = json.loads(EXTRA_ANCHOR.read_text(encoding="utf-8"))
    g_extra = extra_raw.get("graph")
    eng = engine_by_graph.get(g_extra) or source_docs.get(g_extra)
    extra_doc = dc.merge_layout_edges(dict(extra_raw), eng,
                                      backfill_loop_meta=True)
    pos_docs.append((str(EXTRA_ANCHOR), extra_doc))
    assert len(pos_docs) == 18, "expected 17 committed + 1 pool-side anchor," \
        " got %d" % len(pos_docs)

    anchors = {}
    for path, doc in sorted(pos_docs, key=lambda t: t[0]):
        g = doc["graph"]
        graph, src = graph_source_of(g)
        edges = tuple(sorted((e.a, e.b) for e in graph.edges))
        fam, trace = family_of_graph(graph, edges)
        scalars = scalars_for_layout(doc, CALIBER)
        anchors[graph_name_of(str(path)) or g] = {
            "path": str(Path(path).relative_to(REPO)),
            "graph": g,
            "graph_source": src,
            "graph_nodes": sorted(graph.node_ids()),
            "graph_edges": sorted(list(e) for e in edges),
            "family": fam,
            "family_trace": trace,
            "viewBox": doc.get("viewBox"),
            "nodes": doc["nodes"],
            "scalars": {k: v for k, v in sorted(scalars.items())},
            "family_label": labels.get(g),
        }

    # ---- feature key subset: non-None on ALL anchors AND ALL negatives,
    # non-constant across the anchor library (zero-variance keys carry no
    # retrieval information; the exclusion is exported, never silent).
    neg_rows = [scalars_for_layout(d, CALIBER) for _p, d in neg_docs]
    all_rows = [a["scalars"] for a in anchors.values()] + neg_rows
    keys = []
    for k in sorted(all_rows[0]):
        if not all(r.get(k) is not None for r in all_rows):
            continue
        vals = [float(r[k]) for r in all_rows[:len(anchors)]]
        if max(vals) - min(vals) <= 1e-12:
            continue
        keys.append(k)
    excluded = [k for k in sorted(all_rows[0]) if k not in keys]
    assert keys, "no evaluable retrieval keys"

    # ---- robust per-key z-scale from the anchor library itself
    centers, scales = {}, {}
    for k in keys:
        vals = sorted(float(a["scalars"][k]) for a in anchors.values())
        med = median(vals)
        q1, q3 = quantile(vals, 0.25), quantile(vals, 0.75)
        centers[k] = med
        scales[k] = (q3 - q1) / 1.349

    def dist(row_a, row_b):
        acc, n = [], 0
        for k in keys:
            va, vb = row_a.get(k), row_b.get(k)
            if va is None or vb is None:
                continue
            if scales[k] <= 1e-12:
                continue
            acc.append(abs((float(va) - centers[k]) / scales[k]
                           - (float(vb) - centers[k]) / scales[k]))
            n += 1
        if not acc:
            return None, 0
        return math.fsum(acc) / len(acc), n

    # ---- should-hit / should-not-hit distributions
    # Calibration mirrors the runtime decision exactly: Layer 2 compares
    # WITHIN the family only, so should-not-hit = negatives whose graph
    # resolves to the SAME family; negatives whose graph is the anchor's own
    # graph (the replay targets) are excluded -- they are the easy
    # should-hit tail, not negatives.  Negatives without a resolvable graph
    # source are counted and skipped honestly.
    by_fam = {}
    for key, a in anchors.items():
        by_fam.setdefault(a["family"], []).append(key)
    neg_family = {}
    neg_skipped = []
    for (np_path, nd), nr in zip(sorted(neg_docs), neg_rows):
        g = nd.get("graph") or dc.graph_name_of(str(np_path))
        try:
            graph, _src = graph_source_of(g)
        except SystemExit:
            neg_skipped.append(g)
            continue
        edges = tuple(sorted((e.a, e.b) for e in graph.edges))
        fam, _trace = family_of_graph(graph, edges)
        neg_family[str(np_path)] = fam
    anchor_graphs = {a["graph"] for a in anchors.values()}
    hit = []
    for fam, keys_fam in sorted(by_fam.items(), key=lambda t: str(t[0])):
        if fam is None or len(keys_fam) < 2:
            continue
        for i, ka in enumerate(keys_fam):
            for kb in keys_fam[i + 1:]:
                d, n = dist(anchors[ka]["scalars"], anchors[kb]["scalars"])
                if d is not None:
                    hit.append({"a": ka, "b": kb, "family": fam,
                                "distance": round(d, 6)})
    hit_vals = sorted(h["distance"] for h in hit)
    not_hit = []
    for key, a in anchors.items():
        for (np_path, nd), nr in zip(sorted(neg_docs), neg_rows):
            if nd.get("graph") in anchor_graphs:
                continue          # replay target, not a negative
            if neg_family.get(str(np_path)) != a["family"]:
                continue          # Layer 2 compares within the family only
            d, n = dist(a["scalars"], nr)
            if d is not None:
                not_hit.append({"anchor": key, "negative": Path(np_path).stem,
                                "distance": round(d, 6)})
    not_vals = sorted(x["distance"] for x in not_hit)
    assert hit_vals and not_vals, "calibration distributions empty"

    hit_p90 = quantile(hit_vals, 0.90)
    not_p10 = quantile(not_vals, 0.10)
    if hit_p90 < not_p10:
        threshold = (hit_p90 + not_p10) / 2.0
        separated = True
    else:
        threshold = quantile(hit_vals, 0.95)
        separated = False

    lib = {
        "schema": LIBRARY_SCHEMA,
        "note": (
            "anchors-as-prior retrieval sidecar (data, only-add): 18 hand "
            "anchors + the pool-side epidemic anchor; feature rows from the "
            "single-source extractor at normalized caliber; threshold "
            "auto-derived from same-family anchor-pair distances vs "
            "anchor-vs-negatives distances. Regenerate by re-running the "
            "build script; anchors are never edited in place."),
        "caliber": CALIBER,
        "anchors": {k: anchors[k] for k in sorted(anchors)},
        "retrieval": {
            "feature_keys": keys,
            "excluded_keys": excluded,
            "exclusion_rule": (
                "keys null on any anchor or any negative, or constant "
                "across the anchor library (zero information)"),
            "key_centers": {k: centers[k] for k in keys},
            "key_scales": {k: scales[k] for k in keys},
            "scale_rule": "median center, IQR/1.349 scale, library self",
            "weights": "equal (preregistered starting point)",
            "min_evaluable_key_share": 0.5,
            "calibration": {
                "should_hit_distribution": hit,
                "should_not_hit_distribution": not_hit,
                "hit_p50": quantile(hit_vals, 0.50),
                "hit_p75": quantile(hit_vals, 0.75),
                "hit_p90": hit_p90,
                "hit_p95": quantile(hit_vals, 0.95),
                "not_hit_min": not_vals[0],
                "not_hit_p10": not_p10,
                "not_hit_p25": quantile(not_vals, 0.25),
                "separated": separated,
                "threshold_rule": (
                    "midpoint(hit_p90, not_p10) when separated; "
                    "hit_p95 with separated=false otherwise"),
            },
            "hit_threshold": threshold,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(lib, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print("wrote %s" % OUT)
    print("anchors: %d  families: %s"
          % (len(anchors), {str(k): len(v) for k, v in sorted(by_fam.items(),
                                                             key=str)}))
    print("feature keys: %d (excluded %d)" % (len(keys), len(excluded)))
    print("hit n=%d  p50=%s p90=%s p95=%s" % (
        len(hit_vals), quantile(hit_vals, 0.5), hit_p90,
        quantile(hit_vals, 0.95)))
    print("not-hit n=%d  min=%s p10=%s p25=%s" % (
        len(not_vals), not_vals[0], not_p10, quantile(not_vals, 0.25)))
    print("threshold=%s separated=%s" % (threshold, separated))


if __name__ == "__main__":
    main()
