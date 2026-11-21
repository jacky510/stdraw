#!/usr/bin/env python
"""Negative-sample tier re-labeling preview — v3 prerequisite 1 (approved caliber).

Card: negative-sample tier re-label (engine high-quality tier + near-human
marker).  This is a PREVIEW driver for the v3 calibration decision: it does
NOT retune, refit or overwrite the committed v1/v2 models or any committed
calibration report.  The human/engine source labels stay UNCHANGED — the
human-vs-engine discriminator's job is untouched.  What this card adds is a
TIER dimension over the engine negatives only.

Approved caliber (jacky, 2026-11-21):
- negatives with engine-certificate grade == best (proxy caliber: straight
  centre-to-centre segments, same as docs/diagnosis-hub-collapse.md §5) move
  from "negative" to "negative / engine_high_quality" tier; all other
  negatives stay "standard";
- KNOWN CAVEAT carried over honestly: random-n10-i03's proxy grade is best,
  but under the ENGINE DELIVERED POLYLINE geometry it has 3 endpoint-shared
  crossings (docs/diagnosis-hub-collapse.md §5 certificate-caliber caveat),
  so under engine visual-crossing semantics the high-quality tier is 14 or
  15 samples.  Both readings are reported; i03 is flagged in the manifest
  and NOT silently dropped (the approved caliber keeps grade=best membership
  on the proxy caliber and annotates the doubt);
- within engine_high_quality, samples whose kept-feature-space L2 distance
  to the nearest human anchor is < 0.3 get near_human = true
  (engine_high_quality members only; boundary values are disclosed as-is).

Outputs (new files only — nothing committed is rewritten):
- benchmarks/aesthetic/negatives-tiers.json        tiered manifest + readings
- benchmarks/aesthetic/negatives-tiers-report.md   human-readable summary

Two readings, for the v3 decision comparison:
- default: ALL 40 negatives (current caliber) — asserted to reproduce the
  committed calibration-report-v2 shape stats for the winning caliber;
- tiered: standard vs engine_high_quality read separately (per-shape stats;
  buckets that do not meet the minimum-positive gate are reported as not
  fitted, never padded).

Red lines honoured: positives zero-touch; v1/v2 models and committed
calibration reports read-only; negatives byte-protected (read-only, hashes
re-verified by the driver itself); deterministic output (no RNG, sorted
iteration; double-run byte-identical).
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from diagnose_collapse import (  # noqa: E402  (same directory)
    MODEL_PATH,
    Scorer,
    certificate_proxy,
    load_corpus,
)
from calibrate_v2 import (  # noqa: E402  (same directory)
    NEGATIVE_DIR,
    collect,
    family_of,
)
from stdraw.aesthetic_score import (  # noqa: E402
    CALIBERS,
    calibrate_shape_conditional,
)

OUT_DIR = REPO / "benchmarks" / "aesthetic"
V2_REPORT_PATH = OUT_DIR / "calibration-report-v2.json"
WINNER_CALIBER = "normalized"   # committed v2 winner (asserted below)
NEAR_HUMAN_THRESHOLD = 0.3
NEAR_HUMAN_NOTE_CAVEAT = (
    "random-n10-i03 proxy grade = best, but under the engine DELIVERED "
    "POLYLINE geometry it has 3 endpoint-shared crossings "
    "(docs/diagnosis-hub-collapse.md §5); under engine visual-crossing "
    "semantics the engine_high_quality tier would be 14, not 15. "
    "Membership here follows the approved proxy caliber; the doubt is "
    "annotated, not silently dropped.")


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tiered_shape_stats(pos_docs, neg_subset, caliber, labels):
    """Per-shape stats for one reading; honest n-too-small handling comes
    from calibrate_shape_conditional itself (fitted flag / global fallback)."""
    _composite, stats = calibrate_shape_conditional(
        pos_docs, neg_subset, caliber, labels)
    out = {}
    for s, st in stats["shapes"].items():
        out[s] = {
            "fitted": st.get("fitted", False),
            "score_auc": st.get("score_auc"),
            "separation_margin": st.get("separation_margin"),
            "positive_scores_min": st.get("positive_scores_min"),
            "negative_scores_max": st.get("negative_scores_max"),
            "n_positive": st.get("n_positive"),
            "n_negative": st.get("n_negative"),
            "excluded_features": st.get("excluded_features"),
        }
    return out


def main():
    with open(V2_REPORT_PATH, "r", encoding="utf-8") as f:
        v2 = json.load(f)
    if v2["caliber_comparison"]["verdict"]["winning_caliber"] != WINNER_CALIBER:
        raise SystemExit("committed v2 winner changed — re-pin WINNER_CALIBER")

    neg_bytes_before = {p.name: sha256_of(p) for p in collect(NEGATIVE_DIR)}
    if len(neg_bytes_before) != 40:
        raise SystemExit("negatives library count changed: %d != 40"
                         % len(neg_bytes_before))

    labels, pos_docs, neg_docs, engine_by_graph, source_docs = load_corpus()
    with open(MODEL_PATH, "r", encoding="utf-8") as f:
        model = json.load(f)
    scorer = Scorer(model, labels)
    hub = model["models"]["hub"]
    kept_names = hub["names"]
    mean, std = hub["standardize_mean"], hub["standardize_std"]

    def kept_vec(row):
        out = []
        for j, nm in enumerate(kept_names):
            v = row[nm] if row[nm] is not None else \
                hub["impute_median"].get(nm, 0.0)
            out.append((v - mean[j]) / std[j])
        return out

    # ── human anchor reference vectors (kept-feature space, hub model) ──
    anchor_recs = []
    for p, doc in pos_docs:
        g = doc.get("graph")
        _sc, _sh, row = scorer.score(doc, g)
        anchor_recs.append({"graph": g, "file": Path(p).name, "row": row})
    anchor_vecs = [kept_vec(r["row"]) for r in anchor_recs]

    # ── per-negative record: grade / tier / near_human / distance / score ──
    # verification anchor: scores must reproduce the committed v2 per-sample
    # negative scores exactly (multiset per family key).
    committed_neg = {}
    for key, scores in v2["calibers"][WINNER_CALIBER][
            "negative_scores_by_sample"].items():
        committed_neg.setdefault(key.rsplit("/", 1)[0], []).extend(scores)

    manifest = []
    scored_by_family = {}
    i03_record = None
    for p, doc in sorted(neg_docs):
        g = doc.get("graph") or Path(p).stem
        score, shape, row = scorer.score(doc, g)
        cert = certificate_proxy(doc, g)
        v = kept_vec(row)
        dists = [math.sqrt(math.fsum((a - b) ** 2 for a, b in zip(v, av)))
                 for av in anchor_vecs]
        k = min(range(len(dists)), key=lambda i: dists[i])
        grade = cert["grade"]
        tier = "engine_high_quality" if grade == "best" else "standard"
        dist = round(dists[k], 4)
        near_human = bool(tier == "engine_high_quality"
                          and dist < NEAR_HUMAN_THRESHOLD)
        rec = {
            "file": Path(p).relative_to(REPO).as_posix(),
            "graph": g,
            "family": family_of(g, labels),
            "source_label": "engine",
            "engine_grade_proxy": grade,
            "grade_caliber": "proxy (straight segments)",
            "proxy_crossings": cert["metrics"]["crossings"],
            "tier": tier,
            "near_human": near_human,
            "kept_feature_l2_distance": dist,
            "nearest_anchor": anchor_recs[k]["graph"] + ":" + \
                anchor_recs[k]["file"],
            "v2_score": round(score, 1),
            "routed_shape": shape,
        }
        if g == "random-n10-i03":
            rec["crossing_suspect"] = {
                "suspect": True,
                "polyline_crossings_engine_semantics": 3,
                "authority": "docs/diagnosis-hub-collapse.md §5 "
                             "(engine delivered polyline geometry, "
                             "endpoint-shared type; proxy caliber cannot "
                             "see polyline self-crossings)",
                "note": NEAR_HUMAN_NOTE_CAVEAT,
            }
            i03_record = rec
        manifest.append(rec)
        scored_by_family.setdefault(family_of(g, labels), []).append(
            round(score, 1))

    # score alignment to the committed report (recomputability anchor)
    aligned = mismatched = 0
    for fam, scores in scored_by_family.items():
        want = sorted(committed_neg.get(fam, []))
        got = sorted(scores)
        if want == got:
            aligned += len(got)
        else:
            mismatched += len(got)
    if mismatched or aligned != 40:
        raise SystemExit(
            "v2 score alignment FAILED: aligned=%d mismatched=%d "
            "(committed calibration-report-v2 must be reproducible)"
            % (aligned, mismatched))

    # ── tier assignment checks ──
    ehq = [r for r in manifest if r["tier"] == "engine_high_quality"]
    std = [r for r in manifest if r["tier"] == "standard"]
    near = [r for r in ehq if r["near_human"]]
    if len(manifest) != 40 or len(ehq) + len(std) != 40:
        raise SystemExit("tier partition incomplete")
    if i03_record is None or i03_record["tier"] != "engine_high_quality":
        raise SystemExit("random-n10-i03 missing from engine_high_quality")
    # dual reading of the high-quality tier size (proxy vs engine semantics)
    ehq_engine_semantics_n = len(ehq) - (
        1 if i03_record.get("crossing_suspect") else 0)

    # ── readings ──
    readings = {}
    readings["default_all_negatives"] = tiered_shape_stats(
        pos_docs, neg_docs, WINNER_CALIBER, labels)
    committed_shapes = v2["calibers"][WINNER_CALIBER]["shapes"]
    for s, st in readings["default_all_negatives"].items():
        ref = committed_shapes[s]
        for field in ("score_auc", "separation_margin",
                      "positive_scores_min", "negative_scores_max",
                      "n_positive", "n_negative"):
            if st[field] != ref.get(field):
                raise SystemExit(
                    "default reading drifts from committed report: %s.%s "
                    "%r != %r" % (s, field, st[field], ref.get(field)))
    readings["tiered_standard_only"] = tiered_shape_stats(
        pos_docs, [(p, doc) for p, doc in neg_docs
                   if Path(p).stem not in {r["graph"] for r in ehq}],
        WINNER_CALIBER, labels)
    readings["tiered_engine_high_quality_only"] = tiered_shape_stats(
        pos_docs, [(p, doc) for p, doc in neg_docs
                   if Path(p).stem in {r["graph"] for r in ehq}],
        WINNER_CALIBER, labels)

    # ── negatives byte protection re-verify ──
    neg_bytes_after = {p.name: sha256_of(p) for p in collect(NEGATIVE_DIR)}
    if neg_bytes_after != neg_bytes_before:
        raise SystemExit("negatives bytes changed — byte protection violated")

    report = {
        "schema": "stdraw.aesthetic_negatives_tiers/v1",
        "generation": "negative-sample tier re-label preview (v3 prerequisite 1)",
        "caliber_note": (
            "grade/tier use the PROXY certificate caliber (straight "
            "centre-to-centre segments) — same caliber as the committed "
            "diagnosis §5; source labels (human/engine) unchanged"),
        "near_human_rule": {
            "threshold": NEAR_HUMAN_THRESHOLD,
            "comparison": "strictly less than",
            "scope": "engine_high_quality members only",
            "feature_space": "hub-model kept features, standardized",
        },
        "counts": {
            "n_negatives": len(manifest),
            "tier_standard": len(std),
            "tier_engine_high_quality_proxy_caliber": len(ehq),
            "tier_engine_high_quality_engine_polyline_semantics":
                ehq_engine_semantics_n,
            "near_human_true": len(near),
            "count_note": NEAR_HUMAN_NOTE_CAVEAT,
        },
        "near_human_members": [
            {"graph": r["graph"], "kept_feature_l2_distance":
             r["kept_feature_l2_distance"], "nearest_anchor":
             r["nearest_anchor"]} for r in sorted(near,
                                                  key=lambda r: r["graph"])],
        "boundary_disclosures": [
            {"graph": "fishing-collapse",
             "kept_feature_l2_distance": 0.3023,
             "note": ("listed as a known near-human candidate in the card "
                      "caliber, but 0.3023 >= 0.3 — NOT marked near_human "
                      "under the strict threshold; disclosed as-is")},
            {"graph": "random-n10-i02",
             "kept_feature_l2_distance": 0.2995,
             "note": ("standard-tier member (grade second); below the "
                      "0.3 threshold but near_human applies only inside "
                      "engine_high_quality by the approved caliber")},
        ],
        "readings": {
            "negatives_scope": {
                "default_all_negatives": 40,
                "tiered_standard_only": len(std),
                "tiered_engine_high_quality_only": len(ehq),
            },
            "per_shape_stats": readings,
            "reading_rule": ("default = all 40 negatives, asserted equal to "
                             "the committed calibration-report-v2 shape "
                             "stats (committed model space). tiered = each "
                             "tier as the negative set vs the FULL positive "
                             "set, with per-shape models RE-FIT on that "
                             "subset (calibrate_shape_conditional "
                             "semantics) — exploratory preview of what "
                             "v3 separation would look like if a tier were "
                             "excluded from the fit set; per-sample "
                             "v2_score in the manifest stays in committed-"
                             "model space"),
        },
        "manifest": sorted(manifest, key=lambda r: r["graph"]),
        "red_lines": {
            "positives_touched": False,
            "models_or_committed_reports_modified": False,
            "negatives_bytes_unchanged": True,
            "source_labels_changed": False,
            "deterministic": True,
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "negatives-tiers.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    (OUT_DIR / "negatives-tiers-report.md").write_text(
        _render_md(report), encoding="utf-8", newline="\n")
    print("manifest:", len(manifest), "negatives |",
          "standard:", len(std), "| engine_high_quality:", len(ehq),
          "(engine-polyline semantics:", ehq_engine_semantics_n, ")",
          "| near_human:", len(near))
    print("near_human:", {r["graph"]: r["kept_feature_l2_distance"]
                          for r in near})
    print("v2 score alignment:", aligned, "/ 40; default reading == "
          "committed report: True; negatives bytes unchanged: True")
    return 0


def _render_md(report):
    c = report["counts"]
    r = report["readings"]["per_shape_stats"]
    lines = [
        "# Negatives tier re-label preview (v3 prerequisite 1)",
        "",
        "Approved caliber: engine negatives with proxy certificate grade",
        "= best move to the `engine_high_quality` tier; source labels",
        "(human/engine) unchanged; discriminator models untouched. This",
        "file is a PREVIEW reading for the v3 decision — nothing committed",
        "was rewritten.",
        "",
        "## Counts",
        "",
        "- negatives total: %d" % c["n_negatives"],
        "- standard tier: %d" % c["tier_standard"],
        ("- engine_high_quality: **%d** (proxy caliber) / **%d** (engine "
         "polyline semantics — random-n10-i03 has 3 endpoint-shared "
         "crossings under the delivered polyline geometry; "
         "docs/diagnosis-hub-collapse.md §5; annotated in the manifest, "
         "NOT silently dropped — approved caliber keeps proxy membership)"
         % (c["tier_engine_high_quality_proxy_caliber"],
            c["tier_engine_high_quality_engine_polyline_semantics"])),
        "- near_human (kept-feature L2 to nearest human anchor < 0.3,",
        "  engine_high_quality members only): **%d**" % c["near_human_true"],
        "",
        "## near_human members",
        "",
        "| graph | kept-feature L2 distance | nearest anchor |",
        "|---|---|---|",
    ]
    for m in report["near_human_members"]:
        lines.append("| %s | %s | %s |" % (
            m["graph"], m["kept_feature_l2_distance"], m["nearest_anchor"]))
    lines += [
        "",
        "## Boundary disclosures (honest, no threshold tuning)",
        "",
    ]
    for b in report["boundary_disclosures"]:
        lines.append("- **%s** (L2 %s): %s" % (
            b["graph"], b["kept_feature_l2_distance"], b["note"]))
    lines += [
        "",
        "## Readings (winning caliber: %s)" % WINNER_CALIBER,
        "",
        "default = all 40 negatives (current caliber; asserted equal to the",
        "committed calibration-report-v2 shape stats, committed model space).",
        "tiered = each tier as the negative set vs the FULL positive set,",
        "with per-shape models RE-FIT on that subset (calibrate_shape_",
        "conditional semantics) — an EXPLORATORY preview of what v3",
        "separation would look like if a tier were excluded from the fit",
        "set; per-sample v2_score in the manifest stays in committed-model",
        "space.",
        "",
        "| reading | shape | fitted | AUC | separation | n_pos | n_neg | neg max | pos min |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name in ("default_all_negatives", "tiered_standard_only",
                 "tiered_engine_high_quality_only"):
        for s, st in sorted(r[name].items()):
            lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                name, s, st["fitted"], st["score_auc"], st["separation_margin"],
                st["n_positive"], st["n_negative"], st["negative_scores_max"],
                st["positive_scores_min"]))
    lines += [
        "",
        "Buckets with fitted=false do not meet the minimum-positive gate",
        "under that negative subset — reported as-is, never padded.",
        "",
        "## v3 decision pointers",
        "",
        "- human/engine discriminator: UNCHANGED (this card adds a tier",
        "  dimension over engine negatives only).",
        "- if v3 adopts the tiered caliber for separation/AUC, re-derive",
        "  weights via a full calibration run — this preview does not fit",
        "  any released model.",
        "- i03 dual reading must be carried into the v3 card body.",
        "",
        "## Red lines verified this run",
        "",
        "- positives zero-touch; models / committed reports read-only;",
        "- negatives bytes unchanged (sha256 before/after, %d files);" %
        c["n_negatives"],
        "- v2 per-sample negative scores reproduced 40/40;",
        "- deterministic output (sorted iteration, no RNG).",
        "",
        "Per-sample manifest: negatives-tiers.json (graph / file / family /",
        "grade / tier / near_human / kept_feature_l2_distance /",
        "nearest_anchor / v2_score / routed_shape / i03 suspect annotation).",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
