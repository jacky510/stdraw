"""aesthetic_score v1 tests — thin layer, determinism, separation, red lines.

Model/report fixtures are the committed calibration products
(benchmarks/aesthetic/model-v1.json + calibration-report.json); negatives are
the committed engine outputs under benchmarks/raw/aesthetic-v1-negatives.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from stdraw.features import FEATURE_KEYS, FeatureError, extract_features
from stdraw.aesthetic_score import (  # noqa: E402
    AestheticError,
    CALIBERS,
    DOMAIN_DECLARATIONS,
    HUB_INTENSITY_THRESHOLD,
    RHO_RING_THRESHOLD,
    SCALAR_SPECS,
    extract_scalars,
    calibrate,
    route_shape,
    scalars_for_layout,
    score_layout,
    load_family_labels,
)

MANUAL = REPO / "benchmarks" / "manual"
NEGATIVES = REPO / "benchmarks" / "raw" / "aesthetic-v1-negatives"
MODEL = REPO / "benchmarks" / "aesthetic" / "model-v1.json"
REPORT = REPO / "benchmarks" / "aesthetic" / "calibration-report.json"
FAMILY_MAP = REPO / "benchmarks" / "corpus" / "classic" / "topology-families.json"


def _load(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _first_negative():
    for p in sorted(NEGATIVES.rglob("layout.json")):
        return p
    pytest.skip("no committed negatives found")


# ── features: single-source extension keys ──

def test_feature_keys_extended():
    for key in ("avg_edge_length", "symmetry_axis_err_px",
                "degree_canvas_spearman", "hub_neighbor_centrality_ratio"):
        assert key in FEATURE_KEYS


def test_extension_keys_emitted(tmp_path):
    doc = _load(MANUAL / "random-n10-i05-manual-layout.json")
    feats = extract_features(doc)["features"]
    assert feats["avg_edge_length"]["mean_px"] > 0
    assert "rho" in feats["degree_canvas_spearman"]
    assert "ratio" in feats["hub_neighbor_centrality_ratio"]


# ── thin layer: take keys -> normalize ──

def test_scalars_cover_all_specs():
    doc = _load(MANUAL / "random-n10-i05-manual-layout.json")
    fd = extract_features(doc)
    for caliber in CALIBERS:
        row = extract_scalars(fd, caliber)
        for name, *_ in SCALAR_SPECS:
            assert name in row
        assert "layout_n_nodes" in row


def test_calibers_scale_px_by_diagonal():
    doc = _load(MANUAL / "random-n10-i05-manual-layout.json")
    fd = extract_features(doc)
    diag = fd["canvas"]["diagonal"]
    abs_row = extract_scalars(fd, "absolute")
    norm_row = extract_scalars(fd, "normalized")
    assert abs_row["avg_edge_length"] == pytest.approx(norm_row["avg_edge_length"] * diag, rel=1e-9)
    # caliber-neutral scalars identical
    assert abs_row["edge_length_cv"] == norm_row["edge_length_cv"]


# ── shape routing ──

def _labels():
    return load_family_labels(str(FAMILY_MAP))


def test_routing_family_labels():
    labels = _labels()
    row = {"layout_n_nodes": 10, "hub_degree": 4, "degree_canvas_spearman": -0.5}
    assert route_shape("arms-race", row, labels) == "ring"            # single-cycle family
    assert route_shape("bullwhip", row, labels) == "hub"              # multi-cycle coupled
    assert route_shape("graph-not-in-map", row, labels) == "ring"     # rho<0 -> ring


def test_routing_hub_intensity_before_rho():
    labels = _labels()
    row = {"layout_n_nodes": 8, "hub_degree": 7, "degree_canvas_spearman": -0.5}
    assert route_shape("classic-cld-growth-and-burden", row, labels) == "hub"
    # DERIVED threshold (review MAJOR-3: re-measured on a real run): midpoint
    # of the measured empty gap [0.70, 0.80] in the threshold-eligible
    # population — induced-demand (0.80) and classic-cld (0.875) sit above it,
    # so the superseded "empty band [0.70, 0.923]" claim is gone.
    assert HUB_INTENSITY_THRESHOLD == 0.75
    assert RHO_RING_THRESHOLD == 0.0


def test_routing_induced_demand_real_measurement():
    # Real-corpus behavior (supplemented-edge caliber): induced-demand measures
    # hub_degree/n = 0.80 with rho = -0.289 — the threshold routes it HUB
    # before rho could route it ring.  This pins the honest reclassification
    # consequence of the 0.75 choice (vs the superseded 0.81 snapshot).
    labels = _labels()
    row = {"layout_n_nodes": 5, "hub_degree": 4, "degree_canvas_spearman": -0.289}
    assert route_shape("induced-demand", row, labels) == "hub"


def test_routing_degenerate_falls_back_global():
    row = {"layout_n_nodes": 0, "hub_degree": None, "degree_canvas_spearman": None}
    assert route_shape("unknown-graph", row, {}) == "global"


# ── model: committed composite scores deterministically ──

@pytest.fixture(scope="module")
def composite():
    if not MODEL.exists():
        pytest.skip("model-v1.json not calibrated yet")
    return _load(MODEL)


def test_score_deterministic_and_bounded(composite):
    doc = _load(MANUAL / "random-n10-i05-manual-layout.json")
    s1 = score_layout(doc, composite)
    s2 = score_layout(doc, composite)
    assert s1 == s2
    assert 0.0 <= s1 <= 100.0


def test_score_output_carries_domain(composite):
    assert composite["domain"] == DOMAIN_DECLARATIONS[composite["caliber"]]
    assert composite["caliber"] in CALIBERS


def test_composite_has_global_fallback(composite):
    assert "global" in composite["models"]
    assert composite["models"]["global"]["caliber"] == composite["caliber"]


# ── separation on the committed calibration report ──

@pytest.fixture(scope="module")
def report():
    if not REPORT.exists():
        pytest.skip("calibration-report.json not generated yet")
    return _load(REPORT)


def test_report_has_three_views(report):
    assert set(CALIBERS) <= set(report["calibers"])          # both calibers
    assert "loso" in report["calibers"]["absolute"]
    assert "family_separation_normalized" in report          # per-family view
    # MINOR-2: the family table crosses 4 canvas families -> normalized caliber
    # (the absolute caliber declares same-canvas-family ~960px only)
    assert "family_separation_absolute" not in report
    assert "caliber_comparison" in report                    # caliber view


def test_shape_models_separate_anchors_from_engine(report):
    # Supplemented-edge caliber (review MAJOR-1): anchor edge sets completed
    # from the graph source before measurement.  Under this honest caliber
    # hub NO LONGER fully separates (independent review predicted +7.8 ->
    # -6.7); the assertions below encode the supplemented-edge state, not
    # the truncated-edge numbers.
    for caliber in CALIBERS:
        hub = report["calibers"][caliber]["shapes"]["hub"]
        ring = report["calibers"][caliber]["shapes"]["ring"]
        assert hub["score_auc"] >= 0.95
        # residual pos/neg overlap is a documented v1 finding — the margin
        # must stay in the report, never tuned away
        assert isinstance(hub["separation_margin"], float)
        # ring shape: strong AUC; residual overlap is a documented v1 finding
        # (separation margin reported as a number, may be negative)
        assert ring["score_auc"] >= 0.9
        assert isinstance(ring["separation_margin"], float)


def test_loso_held_out_anchors_stay_high(report, composite):
    # Supplemented-edge caliber (review MAJOR-1): LOSO on the honest caliber
    # includes LOW held-out rows (e.g. epidemic-feedback ~15-16, random-n10
    # ring rows ~0-3 under the absolute caliber) — that is the documented
    # honest generalization state, reported fail-visible in the report, NOT
    # tuned away.  This test is a gross-failure tripwire on the committed
    # model's caliber only: every held-out anchor keeps a score, and no
    # score collapses below the gross-regression floor.
    loso = report["calibers"][composite["caliber"]]["loso"]
    scored = [a["score"] for a in loso["per_anchor"] if a.get("score") is not None]
    assert len(scored) >= 5, "expected LOSO rows for every routable anchor"
    assert all(0.0 <= s <= 100.0 for s in scored), scored
    assert min(scored) >= 10.0, (
        "gross-regression tripwire (low outliers stay in the report; see "
        "report LOSO table — honest state, do not tune the model to pass): %s" % scored)
    for s in ("ring", "hub"):
        sub = [a["score"] for a in loso["per_anchor"]
               if a.get("shape") == s and a.get("score") is not None]
        if sub:
            assert loso["%s_min" % s] == min(sub)
    # fail-visible: any low outlier stays in the report, never silently dropped
    assert min(scored) == min(a["score"] for a in loso["per_anchor"] if a.get("score") is not None)


def test_human_lower_bound_recomputed_not_hardcoded(report, composite):
    # bound in the model equals the recomputed min positive routed score
    for shape, st in report["calibers"][composite["caliber"]]["shapes"].items():
        if not st.get("fitted"):
            continue
        bound = composite["models"][shape]["human_lower_bound"]
        assert bound == st["positive_scores_min"]
    # and no legacy hardcoded constant lives in the module source
    src = (REPO / "stdraw" / "aesthetic_score.py").read_text(encoding="utf-8")
    assert "83.6" not in src


def test_ring_model_excludes_alignment(composite):
    ring = composite["models"].get("ring")
    if ring is None:
        pytest.skip("ring model not fitted")
    assert "alignment_max_coverage" not in ring["names"]
    assert composite["routing"]["shape_excluded_features"]["ring"] == ["alignment_max_coverage"]


# ── calibration invariants on a fresh small fit ──

def test_recalibration_changes_bound_with_data(tmp_path):
    pos = [
        MANUAL / "random-n10-i05-manual-layout.json",
        MANUAL / "random-n10-i00-manual-layout.json",
        MANUAL / "user-2026-11-20" / "i05.json",
    ]
    negs = sorted(NEGATIVES.rglob("layout.json"))[:6]
    if not negs:
        pytest.skip("no committed negatives")
    pos_docs = [(str(p), _load(p)) for p in pos]
    neg_docs = [(str(p), _load(p)) for p in negs]
    from stdraw.aesthetic_score import calibrate_shape_conditional
    labels = _labels()
    comp1, _ = calibrate_shape_conditional(pos_docs, neg_docs, "absolute", labels)
    bound1 = comp1["models"]["global"]["human_lower_bound"]
    comp2, _ = calibrate_shape_conditional(pos_docs[:-1], neg_docs, "absolute", labels)
    bound2 = comp2["models"]["global"]["human_lower_bound"]
    assert bound1 == comp1["models"]["global"]["positive_scores_min"]
    # dropping an anchor changes the recomputed bound — nothing hardcoded
    assert (bound1 != bound2) or (len(pos_docs) == 1)


def test_calibrate_requires_both_classes():
    one = MANUAL / "random-n10-i05-manual-layout.json"
    with pytest.raises(AestheticError):
        calibrate([str(one)], [], "absolute")


# ── negative self-check ──

def test_bad_layout_raises_feature_error():
    with pytest.raises(FeatureError):
        extract_features({"nodes": {}})


def test_unknown_caliber_raises():
    doc = _load(MANUAL / "random-n10-i05-manual-layout.json")
    with pytest.raises(AestheticError):
        scalars_for_layout(doc, "bogus")


# ── boundary: scorer never enters the certificate/gate path ──

def test_certificate_never_reads_score():
    for mod in ("gates.py", "recipes.py", "delivery.py", "check.py"):
        src = (REPO / "stdraw" / mod).read_text(encoding="utf-8")
        assert "aesthetic" not in src.lower(), mod
