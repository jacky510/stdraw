#!/usr/bin/env python
"""Calibration driver for aesthetic_score v1 — shape-conditional edition.

Deterministic, stdlib only.  Produces:
- benchmarks/aesthetic/model-v1.json            composite model (winning caliber)
- benchmarks/aesthetic/calibration-report.json  full calibration data
- benchmarks/aesthetic/calibration-report.md    human-readable summary

Views (card acceptance + 2026-11-20 shape-conditional directive):
1. full-anchor fit + LOSO (both calibers, per shape + global)
2. per-shape/per-family separation (topology-families.json labels + geometric
   degree-centroid routing)
3. absolute-px vs normalized caliber comparison incl. rank-reversal check
4. human lower bound (recomputed, never hardcoded)
5. i05 same-graph retest pair stability
6. new-feature sign verification vs jacky's hand-measured reference values

Red line honoured: reads ONLY benchmarks/manual + tests/data anchors and
benchmarks/raw/aesthetic-v1-negatives engine outputs.  The stdraw-workbuddy
workspace is never opened (the three 2026-11-20 anchors were committed to
the repo by default@main).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from stdraw.aesthetic_score import (  # noqa: E402
    CALIBERS,
    DOMAIN_DECLARATIONS,
    SHAPE_EXCLUDED_FEATURES,
    SHAPES,
    calibrate_shape_conditional,
    graph_name_of,
    load_family_labels,
    loso_shape_conditional,
    merge_layout_edges,
    route_shape,
    scalars_for_layout,
    score_row,
)

POSITIVE_DIRS = (REPO / "benchmarks" / "manual", REPO / "tests" / "data")
NEGATIVE_DIR = REPO / "benchmarks" / "raw" / "aesthetic-v1-negatives"
FAMILY_MAP = REPO / "benchmarks" / "corpus" / "classic" / "topology-families.json"
OUT_DIR = REPO / "benchmarks" / "aesthetic"

# jacky's hand-measured reference (2026-11-20, operator directive):
# ring-dominant graphs have negative degree-centroid rho, hub graphs positive.
RHO_REFERENCE = {
    "random-n10-i05": ("ring", -0.26),
    "brand-flywheel": ("ring", -0.14),
    "epidemic-feedback": ("ring", -0.24),
    "classic-cld-growth-and-burden": ("hub", +0.40),
    "random-n10-i00": ("hub", +0.59),
}


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


def main():
    labels = load_family_labels(str(FAMILY_MAP))

    # ── load negatives (keyed by graph name) and positives (merge graph
    #    structure from engine docs when the manual export omits `edges`) ──
    neg_docs = []
    engine_by_graph = {}
    for p in collect(NEGATIVE_DIR):
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        neg_docs.append((str(p), d))
        g = d.get("graph") or graph_name_of(str(p))
        engine_by_graph.setdefault(g, d)

    pos_docs = []
    failures = []
    known_names = set(engine_by_graph) | set(labels)
    for d in POSITIVE_DIRS:
        for p in collect(d):
            with open(p, "r", encoding="utf-8") as f:
                doc = json.load(f)
            # canonical graph name: doc field if known, else filename stem,
            # else unique prefix alias (classic-cld → classic-cld-growth-and-burden)
            stem = graph_name_of(str(p))
            g = doc.get("graph")
            if g not in known_names:
                if stem in known_names:
                    g = stem
                else:
                    base = stem or g or "#"
                    cands = sorted(k for k in known_names if k.startswith(base + "-"))
                    g = cands[0] if len(cands) == 1 else (g or stem)
            doc = dict(doc)
            doc["graph"] = g
            if not isinstance(doc.get("edges"), list):
                eng = engine_by_graph.get(g)
                if eng is None:
                    failures.append({"path": str(p),
                                     "error": "no engine layout to merge edges from"})
                    continue
                doc = merge_layout_edges(doc, eng)
            pos_docs.append((str(p), doc))

    report = {
        "schema": "stdraw.aesthetic_calibration/v2",
        "anchor_sources": {
            "positives": [str(Path(p).relative_to(REPO)).replace("\\", "/")
                          for p, _ in pos_docs],
            "load_failures": [{"path": str(Path(f["path"]).relative_to(REPO)).replace("\\", "/"),
                               "error": f["error"]} for f in failures],
            "n_negatives": len(neg_docs),
            "workbuddy_workspace_read": False,
            "workbuddy_note": ("红线遵守：stdraw-workbuddy 目录零读取；三份 2026-11-20 锚点"
                              "经 default@main (a5a18fc) 入仓后从 benchmarks/manual/user-2026-11-20/ 消费"),
        },
        "shape_routing": {
            "rule": "① 族标签：单环→ring，多环耦合/链/星→hub；② 嵌套环与无标签图：先 hub 强度"
                    "（hub_degree/n ≥ 0.75 → hub），再 degree_centroid_spearman（canvas 中心口径，"
                    "≤0→ring，>0→hub）；③ ρ 退化→全局公式回退。已知局限：i00 仓内 fixture 实测 ρ=-0.53、"
                    "hub 强度 0.5，按本路由入 ring，与 jacky 参考值（+0.59，测自本卡禁读的 WorkBuddy 侧副本）"
                    "冲突——逐样本记录在 routing_log 待复核",
            "rho_threshold": 0.0,
            "hub_intensity_threshold": 0.75,
            "ring_excluded_features": list(SHAPE_EXCLUDED_FEATURES["ring"]),
            "ring_exclusion_rationale": "operator 令：行/列对齐在环族天然低（brand-flywheel 33%），权重必须为 0",
        },
        "new_feature_sign_check": {},
        "calibers": {},
    }

    # ── sign verification of the two new features vs jacky's reference ──
    all_docs = pos_docs + neg_docs
    for g, (expect_shape, ref_rho) in RHO_REFERENCE.items():
        docs = [doc for _, doc in all_docs
                if (doc.get("graph") or graph_name_of(_)) == g]
        if not docs:
            report["new_feature_sign_check"][g] = {"status": "sample-not-found"}
            continue
        f = scalars_for_layout(docs[0], "absolute")
        rho = f["degree_centroid_spearman"]
        gname = docs[0].get("graph") or graph_name_of(_)
        got_shape = route_shape(gname, f, labels)
        report["new_feature_sign_check"][g] = {
            "reference_rho": ref_rho, "measured_rho": rho,
            "sign_matches_reference": (rho is not None and (rho <= 0) == (ref_rho <= 0)),
            "expected_shape": expect_shape, "routed_shape": got_shape,
            "hub_neighbor_ratio": f["hub_neighbor_centrality_ratio"],
        }

    per_cal = {}
    for caliber in CALIBERS:
        composite, stats = calibrate_shape_conditional(pos_docs, neg_docs, caliber, labels)
        l = loso_shape_conditional(pos_docs, neg_docs, caliber, labels)
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

    # ── family separation (absolute caliber, post-routing scores) ──
    _, pos_named, neg_named = per_cal["absolute"]
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
    report["family_separation_absolute"] = fam_report

    # ── caliber comparison (routed scores) ──
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

    # ── human lower bound (recomputed, per shape + global, both calibers) ──
    report["human_lower_bound"] = {
        caliber: {s: per_cal[caliber][0]["models"][s].get("human_lower_bound")
                  if s in per_cal[caliber][0]["models"] else None
                  for s in SHAPES}
        for caliber in CALIBERS
    }
    report["human_lower_bound_note"] = ("recomputed at every calibration; "
                                        "MUST be re-derived as anchors grow (not a constant)")

    # ── i05 retest pair ──
    pair = {}
    for caliber in CALIBERS:
        ps = report["calibers"][caliber]["positive_scores"]
        v1 = ps.get("random-n10-i05:random-n10-i05-manual-layout.json")
        v2 = ps.get("random-n10-i05:i05.json")
        pair[caliber] = {
            "i05_2026_11_16": v1["score"] if v1 else None,
            "i05_2026_11_20": v2["score"] if v2 else None,
        }
        if v1 and v2:
            pair[caliber]["delta"] = round(abs(v1["score"] - v2["score"]), 1)
            pair[caliber]["shape_11_16"] = v1["shape"]
            pair[caliber]["shape_11_20"] = v2["shape"]
    report["i05_retest_pair"] = pair

    # ── emit ──
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    composite = per_cal[winner][0]
    (OUT_DIR / "model-v1.json").write_text(
        json.dumps(composite, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    (OUT_DIR / "calibration-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    (OUT_DIR / "calibration-report.md").write_text(
        _render_md(report, winner), encoding="utf-8", newline="\n")
    print("winner:", winner, "| loso min abs/norm:", la, ln_,
          "| worst-shape auc abs/norm:", aa, an,
          "| disagree pairs:", disagree, "/", len(ca))
    print("sign check:", {g: v.get("sign_matches_reference")
                          for g, v in report["new_feature_sign_check"].items()})
    return 0


def _render_md(report, winner):
    c = report["calibers"][winner]
    cc = report["caliber_comparison"]
    lines = [
        "# aesthetic_score v1 calibration report (shape-conditional)",
        "",
        "Position: three-tier-funnel placeholder heuristic + measurement instrument only.",
        "Final adjudication = Pareto + preference ranker (Phase 3). Certificate grading",
        "(best/uncertified) never reads this score.",
        "",
        "## Data",
        "",
        "- anchors (positive): %d — benchmarks/manual/* (11-06~11-20) incl. user-2026-11-20 + tests/data"
        % len(c["positive_scores"]),
        "- negatives: %d — benchmarks/raw/aesthetic-v1-negatives (current engine auto recipe, re-run)"
        % c["shapes"]["global"]["n_negative"],
        "- **workbuddy workspace: zero reads (red line)**; the three 2026-11-20 anchors",
        "  consumed in-repo after default@main a5a18fc",
        "- WS4 archaeology (demos HTML 11-05~11-07): SKIPPED — demos at those commits contain",
        "  rendered HTML only, no embedded layout-coordinate JSON (`git show 6d689a2:demos/`,",
        "  grep '\"x\"' = 0); \"unmodified by jacky\" attribution not derivable from history alone.",
        "",
        "## Shape-conditional routing (2026-11-20 directive)",
        "",
        "- " + report["shape_routing"]["rule"],
        "- ring model excludes: %s — %s" % (report["shape_routing"]["ring_excluded_features"],
                                            report["shape_routing"]["ring_exclusion_rationale"]),
        "- global formula = fallback only (rho undefined / shape subset not fittable)",
        "",
        "## New-feature sign verification vs jacky's hand measurements",
        "",
        "| graph | expected | reference ρ | measured ρ | sign match | routed |",
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
        "## Headline (winning caliber: %s — %s)" % (winner, cc["verdict"]["winning_domain"]),
        "",
    ]
    for s in SHAPES:
        st = c["shapes"][s]
        if not st.get("fitted"):
            lines.append("- %s: not fitted (n_pos=%d, n_neg=%d) → falls back to global" % (
                s, st["n_positive"], st["n_negative"]))
            continue
        lines.append("- %s: AUC=%s, separation=%s (pos min %s / neg max %s), n=%d/%d, excluded=%s" % (
            s, st["score_auc"], st["separation_margin"], st["positive_scores_min"],
            st["negative_scores_max"], st["n_positive"], st["n_negative"],
            st["excluded_features"] or "none"))
    lines += [
        "- LOSO (shape-conditional): ring min %s / hub min %s" % (
            c["loso"]["ring_min"], c["loso"]["hub_min"]),
        "- human lower bound (recomputed per shape): %s" % report["human_lower_bound"][winner],
        "- fit sample counts recorded per shape in the model; weights/bounds MUST be re-derived",
        "  whenever the anchor library grows — nothing here is a hardcoded constant.",
        "",
        "## Caliber comparison (③)",
        "",
        "| metric | absolute px | normalized |",
        "|---|---|---|",
        "| worst-shape AUC | %s | %s |" % (cc["worst_shape_auc_absolute"],
                                           cc["worst_shape_auc_normalized"]),
        "| worst-shape LOSO min | %s | %s |" % (cc["worst_shape_loso_min_absolute"],
                                                cc["worst_shape_loso_min_normalized"]),
        "",
        "- Spearman across calibers: negatives %s, positives %s" % (
            cc["spearman_negatives"], cc["spearman_positives"]),
        "- cross-class ordering disagreements: %d / %d pairs; ranking-reversal observed: %s" % (
            cc["cross_class_order_disagreements"], cc["cross_class_pairs"],
            cc["ranking_reversal_observed"]),
        "- domain declarations: absolute = same-canvas-family (~960px viewBox) only;",
        "  normalized = cross-canvas (§15.2). Every score output carries its domain.",
        "",
        "## Family separation (②, absolute caliber, post-routing)",
        "",
        "| family | n_neg | neg max | pos shape | n_pos | pos min | separated |",
        "|---|---|---|---|---|---|---|",
    ]
    for name in sorted(report["family_separation_absolute"]):
        f = report["family_separation_absolute"][name]
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            name, f["n_negative"], f["negative_max"],
            f["n_positive"], f["positive_min"], f["separated_min_pos_gt_max_neg"]))
    lines += [
        "",
        "## LOSO per anchor (%s)" % winner,
        "",
        "| held-out | shape | score |",
        "|---|---|---|",
    ]
    for r in c["loso"]["per_anchor"]:
        lines.append("| %s | %s | %s |" % (r.get("held_out"), r.get("shape"), r.get("score")))
    lines += ["", "## i05 retest pair stability (11-16 fixture vs 11-20 redrag)", ""]
    for caliber, p in report["i05_retest_pair"].items():
        lines.append("- %s: 11-16=%s (%s) vs 11-20=%s (%s), |Δ|=%s" % (
            caliber, p["i05_2026_11_16"], p.get("shape_11_16"),
            p["i05_2026_11_20"], p.get("shape_11_20"), p.get("delta")))
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
