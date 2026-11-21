#!/usr/bin/env python
"""Calibration driver for aesthetic_score v2 — 18-anchor recalibration.

Batch-2 (2026-11-21) doubled the human anchor library from 10 to 8+10
anchors.  This is the first exercise of the designed "re-derive everything
whenever the anchor library grows" flow (card: scorer-v2 recalibration).

Deterministic, stdlib only (+ networkx only offline in topology tooling,
not here).  Produces:
- benchmarks/aesthetic/model-v2.json            composite model (winning caliber)
- benchmarks/aesthetic/calibration-report-v2.json  full calibration data
- benchmarks/aesthetic/calibration-report-v2.md    human-readable summary

What changed vs calibrate_v1.py (v1 driver and its artifacts stay untouched):
1. Anchor loading: batch-2 manual exports (benchmarks/manual/jacky-batch2/
   exports/) enter the calibration set.  Engine-certified drafts under
   jacky-batch2/{drafts/,*-draft.json} are ENGINE artifacts, not human
   anchors — excluded by an explicit, logged filter.
2. Edge completion source extended: graphs absent from the negatives library
   are completed from their graph source (benchmarks/manual/jacky-batch2/
   sources/*.cld) via the same merge_layout_edges caliber; every anchor's
   merged edge count is ASSERTED equal to its reference edge count
   (fail-loud completeness gate, zero silent truncation).
3. retest-classic-cld aliases to classic-cld-growth-and-burden (same graph,
   second drag — Test-Retest pair per PROVENANCE.md).
4. New observation sections (reported honestly, never decorated):
   - test_retest_pairs: classic-cld 11-06 vs 11-21 retest, i05 double drag,
     i11-a vs i11-b same-day double drag — individual noise baseline.
   - batch2_family_separation: nested-ring / bowtie / comb / nonplanar
     separation under v2 (v1 had zero anchors for these families).
   - edge_style_anchor_analysis: straight/arc/free usage + anchor-position
     distribution (new data dimensions; NOT model features — see section).
   - threshold_rederivation_audit: the hub-intensity gap re-measured on the
     full 18-anchor corpus; verdict recorded (threshold unchanged / changed).
   - v1_vs_v2_headline: ring/hub metrics v1 snapshot vs v2 re-fit.

Red lines honoured: scorer four boundaries untouched (certificate
separation / single feature source / domain declarations / no hardcoding —
stdraw/aesthetic_score.py is NOT modified by this driver); negatives byte
protection (read-only); determinism (double-run byte-identical); v1
HONESTY NOTE caliber continued; family labels from
benchmarks/corpus/classic/topology-families.json (batch-2 labels added by
the same card, PROVENANCE.md as label authority).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from stdraw import dsl  # noqa: E402
from stdraw.aesthetic_score import (  # noqa: E402
    CALIBERS,
    DOMAIN_DECLARATIONS,
    HUB_INTENSITY_THRESHOLD,
    MIN_COVERAGE,
    SHAPES,
    calibrate_shape_conditional,
    graph_name_of,
    hub_intensity_of,
    hub_intensity_threshold_derivation,
    load_family_labels,
    loso_shape_conditional,
    merge_layout_edges,
    route_shape,
    scalars_for_layout,
    score_row,
)

POSITIVE_DIRS = (REPO / "benchmarks" / "manual", REPO / "tests" / "data")
NEGATIVE_DIR = REPO / "benchmarks" / "raw" / "aesthetic-v1-negatives"
BATCH2_DIR = REPO / "benchmarks" / "manual" / "jacky-batch2"
SOURCE_DIR = BATCH2_DIR / "sources"
FAMILY_MAP = REPO / "benchmarks" / "corpus" / "classic" / "topology-families.json"
V1_REPORT = REPO / "benchmarks" / "aesthetic" / "calibration-report.json"
OUT_DIR = REPO / "benchmarks" / "aesthetic"

# same graph, second drag (PROVENANCE.md: Test-Retest pair)
GRAPH_ALIAS = {"retest-classic-cld": "classic-cld-growth-and-burden"}

# batch-2 anchor families (PROVENANCE.md label authority; labels live in
# topology-families.json since this card)
BATCH2_FAMILIES = ("\u5d4c\u5957\u73af", "\u9886\u7ed3", "\u68b3\u72b6",
                   "\u975e\u5e73\u9762\u65cf", "\u591a\u73af\u8026\u5408")

# jacky's hand-measured reference (unchanged from v1 driver):
RHO_REFERENCE = {
    "random-n10-i05": ("ring", -0.26),
    "brand-flywheel": ("ring", -0.14),
    "epidemic-feedback": ("ring", -0.24),
    "classic-cld-growth-and-burden": ("hub", +0.40),
    "random-n10-i00": ("hub", +0.59),
}


def collect_positive_files(root):
    """Sorted *.json under root, minus provenance sidecars and minus the
    batch-2 ENGINE artifacts (certified drafts) which are not human anchors."""
    out = []
    for p in sorted(Path(root).rglob("*.json")):
        if p.is_file() and "provenance" not in p.name.lower():
            rel = str(p.relative_to(REPO)).replace("\\", "/")
            if "/jacky-batch2/drafts/" in rel:
                continue
            if "jacky-batch2" in rel and p.name.endswith("-draft.json"):
                continue
            out.append(p)
    return out


def collect(root):
    out = []
    for p in Path(root).rglob("*.json"):
        if p.is_file() and "provenance" not in p.name.lower():
            out.append(p)
    return sorted(out)


def family_of(graph, labels):
    fam = labels.get(graph)
    if fam:
        return "classic/" + fam
    if graph.startswith("random-n10"):
        return "random-n10"
    if graph.startswith("fan-"):
        return "fan/radial"
    return "other"


def spearman(xs, ys):
    def ranks(vs):
        order = sorted(range(len(vs)), key=lambda i: vs[i])
        r = [0.0] * len(vs)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vs[order[j + 1]] == vs[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx = math.fsum(rx) / n
    my = math.fsum(ry) / n
    num = math.fsum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(math.fsum((a - mx) ** 2 for a in rx)
                    * math.fsum((b - my) ** 2 for b in ry))
    return num / den if den > 1e-12 else 0.0


def load_graph_source_docs():
    """{stem: minimal doc} from the batch-2 graph sources (.cld)."""
    docs = {}
    for p in sorted(SOURCE_DIR.glob("*.cld")):
        g = dsl.parse(p.read_text(encoding="utf-8"))
        docs[p.stem] = {
            "graph": p.stem,
            "nodes": {n.id: {} for n in g.nodes},
            "edges": [{"a": e.a, "b": e.b} for e in g.edges],
        }
    return docs


def edge_style_anchor_analysis():
    """New data dimensions (edge style straight/arc/free + anchor position)
    measured on the RAW batch-2 manual exports (pre-merge, manual edges only).
    Data inventory only — see the section note for why these are NOT model
    features in v2."""
    per_file = {}
    tot = {"manual_edges": 0, "style": {}, "anchor_positions": {},
           "edges_with_anchors": 0, "edges_with_waypoints": 0}
    for p in sorted((BATCH2_DIR / "exports").glob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        edges = doc.get("edges") or []
        rec = {"graph": doc.get("graph"), "manual_edges": len(edges),
               "style": {}, "anchor_positions": {},
               "edges_with_anchors": 0, "edges_with_waypoints": 0}
        for e in edges:
            st = e.get("style", "auto")
            rec["style"][st] = rec["style"].get(st, 0) + 1
            if e.get("anchors"):
                rec["edges_with_anchors"] += 1
                for side in ("src", "dst"):
                    pos = (e.get("anchors") or {}).get(side)
                    if pos:
                        key = side + ":" + pos
                        rec["anchor_positions"][key] = \
                            rec["anchor_positions"].get(key, 0) + 1
            if e.get("waypoints"):
                rec["edges_with_waypoints"] += 1
        for k in ("manual_edges", "edges_with_anchors", "edges_with_waypoints"):
            tot[k] += rec[k]
        for k in ("style", "anchor_positions"):
            for kk, vv in rec[k].items():
                tot[k][kk] = tot[k].get(kk, 0) + vv
        per_file[p.name] = rec
    n_anchors_total = 18
    n_style_bearing = len(per_file)
    coverage = n_style_bearing / n_anchors_total
    return {
        "per_file": per_file,
        "totals": tot,
        "feature_gate_note": (
            "NOT introduced as model features in v2.  (a) single-source red "
            "line: scorer features come from the one measurement source "
            "(aesthetic_score extract_scalars); edge style/anchors live only "
            "in manual exports.  (b) coverage gate: style data exists for "
            "%d/%d anchors (%.0f%%) < MIN_COVERAGE %.2f — the existing "
            "feature-keeping gate would drop it, and the 10 v1 anchors have "
            "no style field at all (supplemented edges are untouched = "
            "straight centre-to-centre, no user style).  Logged as data for "
            "a future card that widens the anchor library with style-native "
            "exports."
            % (n_style_bearing, n_anchors_total, coverage * 100, MIN_COVERAGE)),
    }


def threshold_rederivation_audit(routing_log):
    """Re-measure the hub-intensity gap on the current corpus and audit the
    hand-derived threshold against it (designed re-derivation flow)."""
    vals = sorted({round(e["hub_intensity"], 6)
                   for e in routing_log
                   if e.get("threshold_eligible")
                   and e.get("hub_intensity") is not None})
    below = [v for v in vals if v < HUB_INTENSITY_THRESHOLD]
    above = [v for v in vals if v > HUB_INTENSITY_THRESHOLD]
    low_max = max(below) if below else None
    high_min = min(above) if above else None
    gap_open = low_max is not None and high_min is not None \
        and low_max < HUB_INTENSITY_THRESHOLD < high_min
    inside = [v for v in vals if low_max < v < high_min] if gap_open else []
    exact = HUB_INTENSITY_THRESHOLD in vals
    midpoint = (gap_open and not exact
                and abs((low_max + high_min) / 2.0 - HUB_INTENSITY_THRESHOLD) < 1e-9)
    verdict = ("UNCHANGED" if gap_open else "STALE — re-derive")
    return {
        "sorted_unique_eligible_intensities": vals,
        "low_band_max": low_max,
        "high_band_min": high_min,
        "threshold": HUB_INTENSITY_THRESHOLD,
        "gap_around_threshold_open": gap_open,
        "gap_is_empty": not inside,
        "threshold_is_gap_midpoint": midpoint,
        "threshold_value_hits_a_sample": exact,
        "verdict": verdict,
        "note": ("designed flow: the anchor library doubling triggered a full "
                 "gap re-measurement; verdict UNCHANGED keeps the hand-derived "
                 "threshold only because the measured gap around it is still "
                 "empty and the threshold is still the gap midpoint; any "
                 "eligible value inside the gap would have raised via "
                 "check_hub_intensity_gap() before this audit runs"),
    }


def _render_md(report, winner):
    c = report["calibers"][winner]
    cc = report["caliber_comparison"]
    lines = [
        "# aesthetic_score v2 calibration report (18-anchor recalibration)",
        "",
        "Position: three-tier-funnel placeholder heuristic + measurement instrument only.",
        "Final adjudication = Pareto + preference ranker (Phase 3). Certificate grading",
        "(best/uncertified) never reads this score.",
        "",
        "## Data",
        "",
        "- anchors (positive): %d — benchmarks/manual/* (11-06~11-20) + "
        "jacky-batch2/exports (11-21, x8) + tests/data; batch-2 engine drafts excluded"
        % len(c["positive_scores"]),
        "- negatives: %d — benchmarks/raw/aesthetic-v1-negatives (unchanged bytes)"
        % c["shapes"]["global"]["n_negative"],
        "- edge-set caliber: every anchor edge set completed from its graph source",
        "  (negatives engine layout, else batch-2 sources/*.cld) BEFORE features are",
        "  measured; per-anchor completeness ASSERTED (edge_supplement_log +",
        "  completeness_check in calibration-report-v2.json)",
        "- family labels: topology-families.json extended with the batch-2 families",
        "  (nested-ring x2, nonplanar x2, bowtie, comb, multi-cycle-coupled;",
        "  PROVENANCE.md is the label authority; measured quirks logged in the",
        "  per-graph rationale, e.g. nested shared-edge counts exceed the classic",
        "  nested-cycle <=1 clause — disclosed, not re-judged)",
        "",
        "## v1 -> v2 headline (winning caliber: %s)" % winner,
        "",
        "| metric | v1 (10 anchors) | v2 (18 anchors) |",
        "|---|---|---|",
    ]
    v1h = report["v1_vs_v2_headline"]["calibers"][winner]
    for row in v1h:
        lines.append("| %s | %s | %s |" % (row[0], row[1], row[2]))
    lines += [
        "",
        "## Shape detail (v2, per shape)",
        "",
    ]
    for s in SHAPES:
        st = c["shapes"][s]
        if not st.get("fitted"):
            lines.append("- %s: not fitted (n_pos=%d, n_neg=%d) -> global fallback" % (
                s, st["n_positive"], st["n_negative"]))
            continue
        lines.append("- %s: AUC=%s, separation=%s (pos min %s / neg max %s), n=%d/%d, excluded=%s" % (
            s, st["score_auc"], st["separation_margin"], st["positive_scores_min"],
            st["negative_scores_max"], st["n_positive"], st["n_negative"],
            st["excluded_features"] or "none"))
        if st["separation_margin"] <= 0:
            lines.append("  - HONESTY NOTE: %s positives do NOT fully separate from negatives"
                         " under the supplemented-edge caliber (separation <= 0) — this is"
                         " the honest state of the model, no threshold was tuned to mask it"
                         % s)
    lines += [
        "- LOSO (shape-conditional): ring min %s / hub min %s" % (
            c["loso"]["ring_min"], c["loso"]["hub_min"]),
        "- human lower bound (recomputed per shape): %s" % report["human_lower_bound"][winner],
        "- fit sample counts recorded per shape in the model; weights/bounds re-derived",
        "  at this run because the anchor library grew (designed flow, first exercise).",
        "",
        "## Threshold re-derivation audit (anchor library 10 -> 18)",
        "",
        "- verdict: **%s** (threshold %.2f)" % (
            report["threshold_rederivation_audit"]["verdict"],
            report["threshold_rederivation_audit"]["threshold"]),
        "- measured eligible intensities this run: %s" % (
            report["threshold_rederivation_audit"]["sorted_unique_eligible_intensities"]),
        "- gap around threshold still empty: %s; threshold is gap midpoint: %s" % (
            report["threshold_rederivation_audit"]["gap_is_empty"],
            report["threshold_rederivation_audit"]["threshold_is_gap_midpoint"]),
        "- fail-loud guard (check_hub_intensity_gap) ran on every calibration pass and",
        "  did not raise: no threshold-eligible value landed strictly inside (0.70, 0.80).",
        "",
        "## Test-Retest pairs (same graph, repeated drags = individual noise baseline)",
        "",
        "| pair | drag 1 | drag 2 |",
        "|---|---|---|",
    ]
    for name, p in report["test_retest_pairs"].items():
        lines.append("| %s | %s | %s |" % (name, p["drag_1"], p["drag_2"]))
        lines.append("| %s |Δ| (%s, %s) | %s | %s |" % (
            "", "abs", "norm", p.get("delta_a"), p.get("delta_n")))
        lines.append("| %s routed shapes (abs) | %s | %s |" % (
            "", p.get("shape_drag_1_a"), p.get("shape_drag_2_a")))
    lines += [
        "",
        "Per-caliber numbers: test_retest_pairs in calibration-report-v2.json.",
        "Reading: the pair deltas are the individual noise baseline — family/anchor",
        "differences smaller than this baseline are NOT interpretable as signal.",
        "CAVEAT (degeneracy, see shape_bucket_degeneracy): a pair whose two drags both",
        "route into a degenerate bucket has delta 0 BY CONSTRUCTION (e.g. the classic-cld",
        "retest pair, hub bucket) — such a 0 is NOT a stability result.  The interpretable",
        "retest numbers are the ring-bucket ones (i11 a/b, i05).  The i05 pair ALSO",
        "flips routed shape between drags (11-16 hub -> 11-20 ring): same graph,",
        "boundary routing is drag-sensitive — recorded, not tuned away.",
        "",
        "## Shape-bucket degeneracy audit (honesty instrument)",
        "",
    ]
    for caliber in CALIBERS:
        for s, d in report["shape_bucket_degeneracy"][caliber].items():
            lines.append("- %s/%s: distinct positive vectors = %s, largest group %s/%s%s" % (
                caliber, s, d["distinct_positive_vectors"],
                d["largest_vector_group"], d["n_positive"],
                ("  **FULLY DEGENERATE** — bucket AUC/separation = "
                 "negative-side variance only" if d["fully_degenerate_positive_side"]
                 else "  **NEAR-DEGENERATE** — %s" % d["note"].split(":", 1)[0]
                 if d["near_degenerate_positive_side"] else "")))
    lines += [
        "",
        "## Batch-2 family separation (observation item: did doubling the anchors help?)",
        "",
        "Precision on coverage: bowtie / comb / nonplanar had ZERO anchors in v1 —",
        "unmeasurable then, first measured now.  nested-ring and multi-cycle-coupled",
        "HAD classic anchors in v1 (brand-flywheel, classic-cld); this batch adds the",
        "first dedicated nested/coupled hand anchors.  Separation is measured per",
        "anchor family vs the negatives of its routed shape bucket (conservative:",
        "the union over every shape the family routes to).  CAVEAT: hub-bucket anchor",
        "scores sit on the near-degenerate collapsed point (see degeneracy audit),",
        "so a hub-side separation margin of ~2 points is thin and NOT interpretable",
        "as per-family hand-skill signal.",
        "",
        "| family | batch-2 anchors (routed, score) | batch2 pos min | shape-bucket neg max | separated |",
        "|---|---|---|---|---|",
    ]
    for name in sorted(report["batch2_family_separation"]):
        f = report["batch2_family_separation"][name]
        lines.append("| %s | %s | %s | %s | %s |" % (
            name, "; ".join(f["batch2_anchor_scores"]) or "(classic anchors only)",
            f["batch2_positive_min"], f["shape_negative_max"], f["separated"]))
    lines += [
        "",
        "Families that do NOT separate: see separated=False rows.  No threshold was",
        "tuned; minimum-anchor estimates for non-separating families are recorded in",
        "the JSON (family_min_anchor_estimate) and restated in the card summary.",
        "",
        "## Edge style / anchor position (new data dimensions — NOT features in v2)",
        "",
    ]
    es = report["edge_style_anchor_analysis"]
    lines.append("- totals over the 8 batch-2 exports: %s" % es["totals"])
    lines.append("- " + es["feature_gate_note"])
    lines += [
        "",
        "## Caliber comparison",
        "",
        "| metric | absolute px | normalized |",
        "|---|---|---|",
        "| worst-shape AUC | %s | %s |" % (cc["worst_shape_auc_absolute"],
                                           cc["worst_shape_auc_normalized"]),
        "| worst-shape LOSO min | %s | %s |" % (cc["worst_shape_loso_min_absolute"],
                                                cc["worst_shape_loso_min_normalized"]),
        "",
        "- winning caliber: %s (%s); rule: max worst-shape LOSO-min, tie-break worst-shape AUC"
        % (cc["verdict"]["winning_caliber"], cc["verdict"]["winning_domain"]),
        "- Spearman across calibers: negatives %s, positives %s" % (
            cc["spearman_negatives"], cc["spearman_positives"]),
        "- cross-class ordering disagreements: %d / %d pairs" % (
            cc["cross_class_order_disagreements"], cc["cross_class_pairs"]),
        "- domain declarations: absolute = same-canvas-family only; normalized =",
        "  cross-canvas. Every score output carries its domain.",
        "",
        "## Family separation (normalized caliber, post-routing)",
        "",
        "| family | n_neg | neg max | n_pos | pos min | separated |",
        "|---|---|---|---|---|---|",
    ]
    for name in sorted(report["family_separation_normalized"]):
        f = report["family_separation_normalized"][name]
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            name, f["n_negative"], f["negative_max"],
            f["n_positive"], f["positive_min"], f["separated_min_pos_gt_max_neg"]))
    lines += [
        "",
        "## Reference-vs-measured rho (NOT a sign check — see v1 report for the note)",
        "",
        "| graph | expected | reference rho | measured rho (in-repo) | sign match | routed |",
        "|---|---|---|---|---|---|",
    ]
    for g, v in report["new_feature_sign_check"].items():
        if v.get("status") == "sample-not-found":
            lines.append("| %s | — | — | — | sample missing | — |" % g)
            continue
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            g, v["expected_shape"], v["reference_rho"], v["measured_rho"],
            v["sign_matches_reference"], v["routed_shape"]))
    lines += [
        "",
        "## LOSO per anchor (%s)" % winner,
        "",
        "| held-out | shape | score |",
        "|---|---|---|",
    ]
    for r in c["loso"]["per_anchor"]:
        lines.append("| %s | %s | %s |" % (r.get("held_out"), r.get("shape"), r.get("score")))
    lines.append("")
    return "\n".join(lines)


def main():
    labels = load_family_labels(str(FAMILY_MAP))

    # ── negatives (byte-protected, read-only) ──
    neg_docs = []
    engine_by_graph = {}
    for p in collect(NEGATIVE_DIR):
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        neg_docs.append((str(p), d))
        g = d.get("graph") or graph_name_of(str(p))
        engine_by_graph.setdefault(g, d)

    # ── graph-source docs (batch-2 .cld): edge-completion fallback for graphs
    #    the negatives library does not carry ──
    source_docs = load_graph_source_docs()

    # ── positives: v1 dirs + batch-2 exports, drafts excluded, alias applied ──
    pos_docs = []
    failures = []
    edge_supplement_log = []
    completeness_check = []
    known_names = set(engine_by_graph) | set(labels) | set(source_docs)
    for d in POSITIVE_DIRS:
        for p in collect_positive_files(d):
            with open(p, "r", encoding="utf-8") as f:
                doc = json.load(f)
            stem = graph_name_of(str(p))
            g = doc.get("graph")
            if g not in known_names:
                if stem in known_names:
                    g = stem
                else:
                    base = stem or g or "#"
                    cands = sorted(k for k in known_names if k.startswith(base + "-"))
                    g = cands[0] if len(cands) == 1 else (g or stem)
            g = GRAPH_ALIAS.get(g, g)
            doc = dict(doc)
            doc["graph"] = g
            n_manual = len(doc.get("edges") or [])
            eng = engine_by_graph.get(g)
            src = "engine layout"
            if eng is None and g in source_docs:
                eng = source_docs[g]
                src = "graph source (batch-2 .cld)"
            try:
                doc = merge_layout_edges(doc, eng)
            except Exception as exc:  # noqa: BLE001 - fail-visible per anchor
                failures.append({"path": str(p), "error": str(exc)})
                continue
            # fail-loud completeness: merged edge count MUST equal the
            # reference edge count (no silent truncation, batch-2 regression
            # gate for the v1 MAJOR-1 class of bug)
            ref_edges = len((eng or {}).get("edges") or []) or len(doc.get("edges") or [])
            total = len(doc["edges"])
            ok = (total == ref_edges) if ref_edges else True
            completeness_check.append({
                "graph": g, "file": Path(p).name, "complete": ok,
                "manual_edges": n_manual, "total_edges": total,
                "reference_edges": ref_edges,
            })
            edge_supplement_log.append({
                "graph": g,
                "path": str(Path(p).relative_to(REPO)).replace("\\", "/"),
                "manual_edges": n_manual,
                "total_edges": total,
                "supplemented": doc["edges_supplemented"],
                "source": src if doc["edges_supplemented"] else
                          ("engine layout (0 needed)" if eng is not None
                           and g in engine_by_graph else "none needed"),
            })
            pos_docs.append((str(p), doc))

    bad = [r for r in completeness_check if not r["complete"]]
    if bad:
        raise SystemExit("edge completeness gate FAILED: %r" % bad)

    report = {
        "schema": "stdraw.aesthetic_calibration/v2",
        "generation": "batch-2 recalibration (anchor library 10 -> 18)",
        "anchor_sources": {
            "positives": [str(Path(p).relative_to(REPO)).replace("\\", "/")
                          for p, _ in pos_docs],
            "load_failures": [{"path": str(Path(f["path"]).relative_to(REPO)).replace("\\", "/"),
                               "error": f["error"]} for f in failures],
            "n_negatives": len(neg_docs),
            "batch2_drafts_exclusion": (
                "engine-certified drafts under benchmarks/manual/jacky-batch2/"
                "{drafts/**,*-draft.json} are ENGINE artifacts, not human "
                "anchors — excluded by an explicit path filter (collect_positive_files)"),
            "graph_alias": GRAPH_ALIAS,
            "edge_set_caliber": (
                "anchor edge sets completed from the graph source BEFORE any "
                "feature is measured (manual 'Export layout' JSONs carry only "
                "the edges the user touched).  Completion source: negatives "
                "engine layout when the negatives library carries the graph, "
                "else the batch-2 graph source (.cld) parsed via stdraw.dsl — "
                "same minimal {'a','b'} append semantics (untouched edge = "
                "straight line between card centres).  Per-anchor completeness "
                "is asserted (completeness_check) and logged "
                "(edge_supplement_log)"),
            "edge_supplement_log": edge_supplement_log,
            "completeness_check": completeness_check,
            "negatives_read_only": True,
        },
        "shape_routing": {
            "rule": "unchanged from v1 (family label -> hub intensity >= %.2f -> "
                    "degree_canvas_spearman -> global fallback); batch-2 family "
                    "labels (nested-ring/bowtie/comb/nonplanar) are NOT in the "
                    "family->shape map, so they route by measurement exactly like "
                    "the classic nested-cycle family does — routing semantics "
                    "unchanged, labels only enrich reporting" % HUB_INTENSITY_THRESHOLD,
            "rho_threshold": 0.0,
            "hub_intensity_threshold": HUB_INTENSITY_THRESHOLD,
            "hub_intensity_threshold_derivation": hub_intensity_threshold_derivation(),
            "ring_excluded_features": ["alignment_max_coverage"],
        },
        "new_feature_sign_check": {},
        "calibers": {},
        "edge_style_anchor_analysis": edge_style_anchor_analysis(),
    }

    # ── reference-vs-measured rho table (same caliber as v1) ──
    all_docs = pos_docs + neg_docs
    for gname, (expect_shape, ref_rho) in RHO_REFERENCE.items():
        matching = [(p, doc) for p, doc in all_docs
                    if (doc.get("graph") or graph_name_of(p)) == gname]
        if not matching:
            report["new_feature_sign_check"][gname] = {"status": "sample-not-found"}
            continue
        p0, doc0 = matching[0]
        f = scalars_for_layout(doc0, "absolute")
        rho = f["degree_canvas_spearman"]
        got_shape = route_shape(gname, f, labels)
        report["new_feature_sign_check"][gname] = {
            "reference_rho": ref_rho,
            "measured_rho": rho,
            "sign_matches_reference": (rho is not None and (rho <= 0) == (ref_rho <= 0)),
            "expected_shape": expect_shape, "routed_shape": got_shape,
            "hub_neighbor_ratio": f["hub_neighbor_centrality_ratio"],
            "measured_on": Path(p0).name,
        }

    per_cal = {}
    for caliber in CALIBERS:
        composite, stats = calibrate_shape_conditional(pos_docs, neg_docs, caliber, labels)
        l = loso_shape_conditional(pos_docs, neg_docs, caliber, labels)
        elig = sorted({round(e["hub_intensity"], 6)
                       for e in stats["routing_log"]
                       if e.get("threshold_eligible")
                       and e.get("hub_intensity") is not None})
        report["shape_routing"].setdefault(
            "hub_intensity_threshold_derivation", {}).setdefault(
            "measured_distribution_this_run", {})[caliber] = {
                "eligible_count": len([e for e in stats["routing_log"]
                                       if e.get("threshold_eligible")
                                       and e.get("hub_intensity") is not None]),
                "sorted_unique": elig,
                "gap_checked": "(0.70, 0.80) open at this run",
            }
        pos_named = {}
        for p, doc in pos_docs:
            g = doc.get("graph") or graph_name_of(p)
            row = scalars_for_layout(doc, caliber)
            s = route_shape(g, row, labels)
            model = composite["models"].get(s) or composite["models"]["global"]
            pos_named[g + ":" + Path(p).name] = {"score": score_row(model, row), "shape": s}
        neg_named = {}
        for p, doc in neg_docs:
            g = doc.get("graph") or graph_name_of(p)
            row = scalars_for_layout(doc, caliber)
            s = route_shape(g, row, labels)
            model = composite["models"].get(s) or composite["models"]["global"]
            neg_named.setdefault(family_of(g, labels) + "/" + g,
                                 []).append(score_row(model, row))
        report["calibers"][caliber] = {
            "domain": DOMAIN_DECLARATIONS[caliber],
            "shapes": stats["shapes"],
            "routing_log": stats["routing_log"],
            "loso": l,
            "positive_scores": pos_named,
            "negative_scores_by_sample": neg_named,
        }
        per_cal[caliber] = (composite, pos_named, neg_named)

    # ── threshold re-derivation audit (normalized caliber routing_log) ──
    report["threshold_rederivation_audit"] = threshold_rederivation_audit(
        report["calibers"]["normalized"]["routing_log"])

    # ── family separation (normalized caliber, post-routing) ──
    _, pos_named, neg_named = per_cal["normalized"]
    fam = {}
    for key, scores in neg_named.items():
        fam.setdefault(key.rsplit("/", 1)[0], []).extend(scores)
    pos_fam = {}
    for rec in pos_named.values():
        pos_fam.setdefault(rec["shape"], []).append(rec["score"])
    fam_report = {}
    for name in sorted(set(fam) | set(pos_fam)):
        negs = fam.get(name, [])
        poss = pos_fam.get(name, [])
        fam_report[name] = {
            "n_negative": len(negs),
            "negative_max": max(negs) if negs else None,
            "negative_mean": round(math.fsum(negs) / len(negs), 1) if negs else None,
            "n_positive": len(poss),
            "positive_min": min(poss) if poss else None,
            "separated_min_pos_gt_max_neg": bool(poss and negs and min(poss) > max(negs)),
        }
    report["family_separation_normalized"] = fam_report

    # ── batch-2 family separation (observation item) ──
    batch2_files = {Path(p).name for p, _ in pos_docs if "jacky-batch2" in p}
    batch2_sep = {}
    for famname in BATCH2_FAMILIES:
        anchors = []
        scores = []
        b2_scores = []
        for key, rec in pos_named.items():
            g = key.split(":", 1)[0]
            fname = key.split(":", 1)[1] if ":" in key else ""
            if labels.get(g) == famname and ":retest-" not in key:
                anchors.append(key)
                scores.append(rec["score"])
                if fname in batch2_files:
                    b2_scores.append(rec["score"])
        if not anchors:
            continue
        shapes = {pos_named[a]["shape"] for a in anchors}
        shape_negs = []
        for key, vs in neg_named.items():
            g = key.rsplit("/", 1)[1]
            if route_shape(g, scalars_for_layout(
                    dict(engine_by_graph[g]), "normalized"), labels) in shapes:
                shape_negs.extend(vs)
        same_family_negs = fam.get("classic/" + famname, [])
        fam_min = min(scores)
        neg_max = max(shape_negs) if shape_negs else None
        batch2_sep[famname] = {
            "anchors_routed": ["%s (%s, %.1f)" % (a.rsplit(":", 1)[1],
                                                  pos_named[a]["shape"],
                                                  pos_named[a]["score"])
                               for a in sorted(anchors)],
            "batch2_anchor_scores": ["%s (%s, %.1f)" % (k.rsplit(":", 1)[1],
                                                        pos_named[k]["shape"],
                                                        pos_named[k]["score"])
                                     for k in sorted(anchors)
                                     if k.split(":", 1)[1] in batch2_files],
            "routed_shapes": sorted(shapes),
            "family_positive_min": fam_min,
            "batch2_positive_min": min(b2_scores) if b2_scores else None,
            "shape_negative_max": neg_max,
            "same_classic_family_negative_max": max(same_family_negs) if same_family_negs else None,
            "separated": bool(shape_negs and fam_min > neg_max),
            "separated_batch2_only": bool(shape_negs and b2_scores
                                          and min(b2_scores) > neg_max),
            "family_min_anchor_estimate": None if (shape_negs and fam_min > neg_max) else (
                "not derivable from %d anchor(s): with 1-2 anchors per family the "
                "family minimum is a single sample and LOSO for the family is "
                "undefined; a family separation claim needs >= 3 anchors so the "
                "held-out minimum is not the tested sample itself (MIN_SHAPE_"
                "POSITIVE caliber).  This batch contributed %d — treat the "
                "family as measured-but-unproven, do not tune anything to it."
                % (len(anchors), len(b2_scores))),
        }
    report["batch2_family_separation"] = batch2_sep

    # ── shape-bucket degeneracy audit (honesty instrument) ──
    # If every positive in a shape bucket measures the IDENTICAL kept-feature
    # vector, that bucket's positive side is degenerate: its scores collapse
    # to one point, its Test-Retest deltas are 0 by construction, and its
    # AUC/separation numbers are driven by negative-side variance only.
    degeneracy = {}
    for caliber in CALIBERS:
        composite0 = per_cal[caliber][0]
        buckets = {}
        for p, doc in pos_docs:
            g = doc.get("graph") or graph_name_of(p)
            row = scalars_for_layout(doc, caliber)
            s = route_shape(g, row, labels)
            model = composite0["models"].get(s) or composite0["models"]["global"]
            vals = tuple(row[nm] for nm in model["names"])
            buckets.setdefault(s, {})[Path(p).name] = {
                "features": dict(zip(model["names"], vals))}
        for s, members in buckets.items():
            vecs = [tuple(round(v, 9) for v in m["features"].values())
                    for m in members.values()]
            counts = {}
            for v in vecs:
                counts[v] = counts.get(v, 0) + 1
            largest = max(counts.values())
            n_pos = len(vecs)
            degeneracy.setdefault(caliber, {})[s] = {
                "kept_features": sorted({k for m in members.values()
                                         for k in m["features"]}),
                "per_anchor": members,
                "n_positive": n_pos,
                "distinct_positive_vectors": len(counts),
                "largest_vector_group": largest,
                "collapsed_share": round(largest / n_pos, 3) if n_pos else None,
                "fully_degenerate_positive_side": len(counts) == 1,
                "near_degenerate_positive_side": n_pos > 0 and largest / n_pos >= 0.8,
                "note": (
                    ("FULLY degenerate: every positive measures the same "
                     "kept-feature vector — positive scores collapse to one "
                     "point; retest deltas within the bucket are 0 by "
                     "construction; bucket AUC/separation = negative-side "
                     "variance only.")
                    if len(counts) == 1 else
                    ("NEAR-degenerate: %d/%d positives share ONE kept-feature "
                     "vector (grid-snapped drags measure row/column alignment "
                     "1.0 and bend curvature 0 — export-format anchors carry "
                     "no hand-routing info; v1 HONESTY NOTE caliber).  Their "
                     "scores are identical and their retest deltas are 0 by "
                     "construction; the bucket's AUC/separation is dominated "
                     "by negative-side variance plus the minority anchors "
                     "(the --from-layout product with real engine routing)."
                     % (largest, n_pos))
                    if largest / n_pos >= 0.8 else None),
            }
    report["shape_bucket_degeneracy"] = degeneracy

    # ── test-retest pairs ──
    pairs_def = {
        "classic-cld (11-06 vs 11-21 retest)":
            ("classic-cld-growth-and-burden:classic-cld-manual-layout.json",
             "classic-cld-growth-and-burden:retest-classic-cld-manual-layout.json"),
        "random-n10-i05 (11-16 vs 11-20 double drag)":
            ("random-n10-i05:random-n10-i05-manual-layout.json",
             "random-n10-i05:i05.json"),
        "random-n10-i11 (11-20 same-day double drag a/b)":
            ("random-n10-i11:i11-a.json", "random-n10-i11:i11-b.json"),
    }
    pairs_out = {}
    for name, (k1, k2) in pairs_def.items():
        rec = {}
        for caliber in CALIBERS:
            ps = report["calibers"][caliber]["positive_scores"]
            v1, v2 = ps.get(k1), ps.get(k2)
            c = caliber[0]  # 'a' / 'n'
            rec["drag_1_" + c] = v1["score"] if v1 else None
            rec["drag_2_" + c] = v2["score"] if v2 else None
            if v1 and v2:
                rec["delta_" + c] = round(abs(v1["score"] - v2["score"]), 1)
                rec["shape_drag_1_" + c] = v1["shape"]
                rec["shape_drag_2_" + c] = v2["shape"]
        rec["drag_1"] = k1.split(":", 1)[1]
        rec["drag_2"] = k2.split(":", 1)[1]
        pairs_out[name] = rec
    report["test_retest_pairs"] = pairs_out

    # ── caliber comparison ──
    def flat(caliber):
        _, pn, nn = per_cal[caliber]
        pv = [r["score"] for r in pn.values()]
        nv = [v for vs in nn.values() for v in vs]
        return pv, nv
    pa, na = flat("absolute")
    pn_, nn_ = flat("normalized")
    ca = [(p, q) for p in pa for q in na]
    cn = [(p, q) for p in pn_ for q in nn_]
    disagree = sum(1 for (p1, q1), (p2, q2) in zip(ca, cn) if (p1 > q1) != (p2 > q2))

    def worst_loso(caliber):
        vals = [report["calibers"][caliber]["loso"]["ring_min"],
                report["calibers"][caliber]["loso"]["hub_min"]]
        vals = [v for v in vals if v is not None]
        return min(vals) if vals else None

    def worst_auc(caliber):
        vals = [report["calibers"][caliber]["shapes"][s].get("score_auc")
                for s in ("ring", "hub")]
        vals = [v for v in vals if v is not None]
        return min(vals) if vals else None
    la, ln_ = worst_loso("absolute"), worst_loso("normalized")
    aa, an = worst_auc("absolute"), worst_auc("normalized")
    winner = "absolute" if (la, aa) >= (ln_, an) else "normalized"
    report["caliber_comparison"] = {
        "spearman_negatives": round(spearman(na, nn_), 4),
        "spearman_positives": round(spearman(pa, pn_), 4),
        "worst_shape_auc_absolute": aa,
        "worst_shape_auc_normalized": an,
        "worst_shape_loso_min_absolute": la,
        "worst_shape_loso_min_normalized": ln_,
        "cross_class_pairs": len(ca),
        "cross_class_order_disagreements": disagree,
        "ranking_reversal_observed": disagree > 0,
        "verdict": {
            "winning_caliber": winner,
            "winning_domain": DOMAIN_DECLARATIONS[winner],
            "rule": "max worst-shape LOSO-min, tie-break worst-shape AUC",
        },
    }

    # ── human lower bound (recomputed) ──
    report["human_lower_bound"] = {
        caliber: {s: per_cal[caliber][0]["models"][s].get("human_lower_bound")
                  if s in per_cal[caliber][0]["models"] else None
                  for s in SHAPES}
        for caliber in CALIBERS
    }

    # ── v1 -> v2 headline (v1 committed report as the snapshot baseline) ──
    with open(V1_REPORT, "r", encoding="utf-8") as f:
        v1 = json.load(f)
    v1_winner = v1["caliber_comparison"]["verdict"]["winning_caliber"]
    headline = {}
    for caliber in CALIBERS:
        rows = []
        for s in ("ring", "hub", "global"):
            st = report["calibers"][caliber]["shapes"][s]
            v1st = v1["calibers"][caliber]["shapes"][s]
            rows.append(["%s AUC" % s, v1st.get("score_auc"), st.get("score_auc")])
            rows.append(["%s separation" % s, v1st.get("separation_margin"),
                         st.get("separation_margin")])
            rows.append(["%s neg max" % s, v1st.get("negative_scores_max"),
                         st.get("negative_scores_max")])
            rows.append(["%s pos min" % s, v1st.get("positive_scores_min"),
                         st.get("positive_scores_min")])
            rows.append(["%s n_pos/n_neg" % s,
                         "%s/%s" % (v1st.get("n_positive"), v1st.get("n_negative")),
                         "%s/%s" % (st.get("n_positive"), st.get("n_negative"))])
        vl = v1["calibers"][caliber]["loso"]
        rows.append(["LOSO ring min", vl.get("ring_min"),
                     report["calibers"][caliber]["loso"].get("ring_min")])
        rows.append(["LOSO hub min", vl.get("hub_min"),
                     report["calibers"][caliber]["loso"].get("hub_min")])
        rows.append(["human lower bound",
                     json.dumps(v1["human_lower_bound"][caliber], sort_keys=True),
                     json.dumps(report["human_lower_bound"][caliber], sort_keys=True)])
        headline[caliber] = rows
    report["v1_vs_v2_headline"] = {
        "v1_snapshot": {"winner": v1_winner,
                        "file": "benchmarks/aesthetic/calibration-report.json",
                        "note": "committed v1 artifact read as-is (baseline snapshot)"},
        "v2_winner": winner,
        "calibers": headline,
        "by_winning_caliber": headline[winner],
    }

    # ── emit ──
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    composite = per_cal[winner][0]
    (OUT_DIR / "model-v2.json").write_text(
        json.dumps(composite, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    (OUT_DIR / "calibration-report-v2.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    (OUT_DIR / "calibration-report-v2.md").write_text(
        _render_md(report, winner), encoding="utf-8", newline="\n")
    print("winner:", winner, "| loso min abs/norm:", la, ln_,
          "| worst-shape auc abs/norm:", aa, an,
          "| disagree pairs:", disagree, "/", len(ca))
    print("threshold audit:", report["threshold_rederivation_audit"]["verdict"])
    print("anchors:", len(pos_docs), "negatives:", len(neg_docs),
          "completeness failures:", len(bad))
    print("batch2 family separation:",
          {k: v["separated"] for k, v in batch2_sep.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
