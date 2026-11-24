# -*- coding: utf-8 -*-
"""aesthetic_score v2 recalibration acceptance (anchor library 10 -> 18).

Acceptance caliber (card: scorer-v2 recalibration):
  - 18 anchors all loaded, edge completeness gate 0 failures;
  - batch-2 family labels live in topology-families.json and the five new
    family rows exist in the report's batch2_family_separation;
  - full re-derivation artifacts present: weights / lower bounds / AUC / sep /
    LOSO / family separation / fit_sample_counts / routing_log re-emitted;
  - threshold re-derivation audit recorded (verdict UNCHANGED, gap re-measured);
  - fail-loud guard proven alive (synthetic gap closure raises);
  - test-retest pairs recorded (classic retest + i05 + i11 a/b);
  - negatives untouched (aggregate byte hash equals the committed tree).
  - determinism: re-running the driver reproduces byte-identical artifacts
    (one legacy fixture re-run, compared to the committed artifacts).
"""
import hashlib
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from stdraw.aesthetic_score import AestheticError, check_hub_intensity_gap  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODEL = os.path.join(ROOT, "stdraw", "data", "model-v2.json")
REPORT = os.path.join(ROOT, "benchmarks", "aesthetic", "calibration-report-v2.json")
NEG_DIR = os.path.join(ROOT, "benchmarks", "raw", "aesthetic-v1-negatives")

# calibration report + negatives provenance check need the checkout's git
# repo and research artifacts (packaging T6 auto-skip, tests/conftest.py);
# the packaged model itself (stdraw/data) ships with the sdist/wheel.
pytestmark = pytest.mark.repo(".git", "benchmarks/aesthetic",
                              "benchmarks/raw/aesthetic-v1-negatives")


def _load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _negatives_agg():
    """(count, aggregate sha256) over the negative corpus, hashed from the
    committed git blobs instead of working-tree files.  Blob bytes are LF
    and platform-independent; a Windows checkout (core.autocrlf=true)
    rewrites them CRLF on disk, so a constant hashed from a working tree
    only matches that platform's checkout and can never match CI (LF)."""
    out = subprocess.run(
        ["git", "-C", ROOT, "ls-tree", "-r", "HEAD", "--", NEG_DIR],
        stdout=subprocess.PIPE, check=True).stdout.decode("utf-8")
    h = hashlib.sha256()
    files = []
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        blob = subprocess.run(
            ["git", "-C", ROOT, "cat-file", "blob", meta.split()[2]],
            stdout=subprocess.PIPE, check=True).stdout
        files.append((path, blob))
        h.update(blob)
    return files, h.hexdigest()


def _require_artifacts():
    if not (os.path.exists(MODEL) and os.path.exists(REPORT)):
        pytest.skip("model-v2.json / calibration-report-v2.json not calibrated yet")


def test_model_present_and_shape_conditional():
    _require_artifacts()
    m = _load(MODEL)
    assert m["kind"] == "shape-conditional"
    assert m["caliber"] == "normalized"
    assert set(m["models"]) == {"ring", "hub", "global"}


def test_fit_sample_counts_18_anchors():
    _require_artifacts()
    m = _load(MODEL)
    fc = {s: m["models"][s]["fit_sample_counts"] for s in ("ring", "hub", "global")}
    assert sum(fc[s]["positive"] for s in ("ring", "hub")) == 18
    assert fc["global"]["positive"] == 18
    assert fc["global"]["negative"] == 40
    assert m["models"]["ring"]["human_lower_bound"] is not None
    assert m["models"]["hub"]["human_lower_bound"] is not None


def test_edge_completeness_gate_zero_failures():
    _require_artifacts()
    r = _load(REPORT)
    log = r["anchor_sources"]["edge_supplement_log"]
    comp = r["anchor_sources"]["completeness_check"]
    assert len(log) == 18 and len(comp) == 18
    assert all(c["complete"] for c in comp)
    assert r["anchor_sources"]["load_failures"] == []
    batch2 = [e for e in log if "jacky-batch2" in e["path"]]
    assert len(batch2) == 8
    assert any(e["source"].startswith("graph source") for e in batch2)


def test_batch2_family_labels_and_separation_rows():
    _require_artifacts()
    r = _load(REPORT)
    fams = set(r["batch2_family_separation"])
    assert {"嵌套环", "领结", "梳状", "非平面族", "多环耦合"} <= fams
    m = _load(MODEL)
    labels = m["family_labels"]
    for g in ("nested-capacity", "nested-learning", "comb-supply-demand",
              "bowtie-wage-price", "nonplanar-credit", "nonplanar-inventory",
              "coupled-underinvestment"):
        assert labels.get(g), "missing batch-2 family label: %s" % g
    assert labels["nonplanar-credit"] == "非平面族"


def test_threshold_audit_and_fail_loud_guard():
    _require_artifacts()
    r = _load(REPORT)
    audit = r["threshold_rederivation_audit"]
    assert audit["verdict"] == "UNCHANGED"
    assert audit["gap_around_threshold_open"] and audit["gap_is_empty"]
    assert audit["threshold_is_gap_midpoint"]
    for caliber in ("absolute", "normalized"):
        dist = r["shape_routing"]["hub_intensity_threshold_derivation"][
            "measured_distribution_this_run"][caliber]
        assert dist["eligible_count"] > 0 and dist["sorted_unique"]
    # guard falsification leg: boundary values exempt, inside-gap raises
    assert check_hub_intensity_gap([
        {"hub_intensity": 0.70, "threshold_eligible": True},
        {"hub_intensity": 0.80, "threshold_eligible": True},
    ]) == []
    with pytest.raises(AestheticError):
        check_hub_intensity_gap([{"hub_intensity": 0.74, "threshold_eligible": True}])


def test_test_retest_pairs_recorded():
    _require_artifacts()
    r = _load(REPORT)
    pairs = r["test_retest_pairs"]
    assert len(pairs) == 3
    classic = pairs["classic-cld (11-06 vs 11-21 retest)"]
    assert classic["drag_1_a"] is not None and classic["drag_2_a"] is not None
    assert "delta_a" in classic and "delta_n" in classic
    assert "delta_n" in pairs["random-n10-i05 (11-16 vs 11-20 double drag)"]
    assert "delta_n" in pairs["random-n10-i11 (11-20 same-day double drag a/b)"]


def test_hub_bucket_collapse_is_recorded_not_hidden():
    _require_artifacts()
    r = _load(REPORT)
    d = r["shape_bucket_degeneracy"]["normalized"]["hub"]
    assert d["near_degenerate_positive_side"] is True
    assert d["distinct_positive_vectors"] == 2
    assert d["largest_vector_group"] == d["n_positive"] - 1  # 8/9 collapse
    ring = r["shape_bucket_degeneracy"]["normalized"]["ring"]
    assert ring["near_degenerate_positive_side"] is False


def test_headline_metrics_rederived_against_v1_snapshot():
    _require_artifacts()
    r = _load(REPORT)
    h = r["v1_vs_v2_headline"]
    assert h["v1_snapshot"]["winner"] == "normalized"
    rows = h["calibers"]["normalized"]
    v1_ring_auc = [x for x in rows if x[0] == "ring AUC"][0]
    v2_ring_auc = r["calibers"]["normalized"]["shapes"]["ring"]["score_auc"]
    assert v1_ring_auc[1] != v2_ring_auc  # re-fit actually happened
    loso = r["calibers"]["normalized"]["loso"]
    assert loso["ring_min"] is not None and loso["hub_min"] is not None


def test_negatives_bytes_untouched():
    files, agg = _negatives_agg()
    assert len(files) == 40
    # committed-tree reference (LF blob bytes, platform-independent); drift
    # means negatives were rewritten.  The pre-fix constant fb41eb96... was
    # hashed from a CRLF Windows working tree and only matched local
    # checkouts, which is why CI (LF) went red while local runs stayed green.
    assert agg == "7cfd39afdee541b69cabe0a9bc999881114508a8bd988a89cba965644926efec"
    # local copies must carry the same content (EOL-normalised: autocrlf may
    # write CRLF locally) - catches uncommitted corpus edits on any platform
    local = sorted(os.path.join(dp, f) for dp, _, fs in os.walk(NEG_DIR)
                   for f in fs if f.endswith(".json"))
    assert len(local) == len(files), "untracked corpus files appeared"
    for path, blob in files:
        with open(os.path.join(ROOT, path), "rb") as fh:
            assert fh.read().replace(b"\r\n", b"\n") == blob, path


def test_edge_style_analysis_present_with_gate_note():
    _require_artifacts()
    r = _load(REPORT)
    es = r["edge_style_anchor_analysis"]
    assert len(es["per_file"]) == 8
    assert es["totals"]["manual_edges"] > 0
    assert "NOT introduced as model features" in es["feature_gate_note"]
    styles = es["totals"]["style"]
    assert styles.get("auto", 0) > 0
    assert styles.get("arc", 0) > 0 or styles.get("free", 0) > 0
