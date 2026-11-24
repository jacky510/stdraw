# -*- coding: utf-8 -*-
"""M0 quality gate (anchors-as-prior S3).

The ranking replacement per docs/proposals/anchor-prior-candidate-generation
section 3.1:

    viability hard gate (unchanged)
      -> M0 quality gate: the COMMITTED v2 pointwise model
         (stdraw/data/model-v2.json, packaged) scores each candidate; a
         candidate is eliminated when it sits more than epsilon below the
         pool best.  epsilon = the committed cross-session noise-gate
         calibration (M0 epsilon P75 = 58.6 over the 18 both-good pairs,
         pref-ranking-final-v2) -- a RELATIVE, paired caliber: epsilon is a
         v2 score DIFFERENCE, only ever compared within one graph's pool,
         never across graphs.  No absolute threshold is invented here.

Scoring is a thin layer over the committed machinery (single source, zero
re-implementation): stdraw.aesthetic_score's normalized-caliber scalar row
-> family routing -> logistic score_row -- exactly the diagnose-collapse
Scorer caliber, asserted numerically equal by the offline A/B script.

The model and family labels are DATA files (committed, read-only).  When
they cannot be resolved the caller degrades honestly: the M0 gate is
recorded inactive and the previous ranking caliber applies -- never a
silent approximation.
"""
import json
from pathlib import Path

from . import _datafiles
from .aesthetic_score import route_shape, scalars_for_layout, score_row

MODEL_SCHEMA = "stdraw.aesthetic_model/v1"
CALIBER = "normalized"          # committed v2 winner caliber

# Committed calibration constant (stdraw/data/model-v2.json retrieval
# calibration -> epsilon_calibration.per_arm.M0.p75_initial,
# P75 over the 18 both-good pairs).  A named constant on purpose: it is the
# documented threshold of the gate, re-derived by the calibration artifacts,
# never tuned per graph.
M0_EPS_P75 = 58.6

# Packaged runtime data (importlib.resources; identical for pip installs
# and git clones).
DEFAULT_MODEL_PATH = _datafiles.data_file("model-v2.json")
DEFAULT_LABELS_PATH = _datafiles.data_file("topology-families.json")


def load_model(model_path=None, labels_path=None):
    """Load the committed M0 model + family labels (data, read-only).
    Returns {"model":..., "labels":...} or None (honest degradation)."""
    from .aesthetic_score import load_family_labels
    mp = Path(model_path) if model_path else DEFAULT_MODEL_PATH
    lp = Path(labels_path) if labels_path else DEFAULT_LABELS_PATH
    try:
        model = json.loads(_datafiles.read_text(mp))
        labels = load_family_labels(lp)
    except (OSError, ValueError):
        return None
    if model.get("schema") != MODEL_SCHEMA:
        return None
    return {"model": model, "labels": labels}


def score_doc(doc, graph_name, m0):
    """Committed M0 pointwise score of one layout doc (0-100, one decimal).
    Returns (score, shape); raises on an unreadable doc (caller records the
    candidate not-evaluable -- three-state, never zero)."""
    row = scalars_for_layout(doc, CALIBER)
    shape = route_shape(graph_name, row, m0["labels"])
    return score_row(m0["model"]["models"].get(shape)
                     or m0["model"]["models"]["global"], row), shape


def relative_gate(scores, eps=M0_EPS_P75):
    """Paired-caliber elimination: drop candidates more than eps below the
    pool best.  ``scores``: {cid: float-or-None}; None = not evaluable (kept
    out of the gate decision, reported as such -- three-state discipline).
    Returns (kept_cids, record)."""
    evaluable = {c: s for c, s in scores.items() if s is not None}
    if not evaluable:
        return sorted(scores), {"eliminated": [], "pool_best": None,
                                "note": "no evaluable scores"}
    best = max(evaluable.values())
    kept = sorted(c for c, s in scores.items()
                  if s is None or (best - s) <= eps)
    eliminated = sorted(c for c, s in scores.items()
                        if s is not None and (best - s) > eps)
    return kept, {"eliminated": eliminated, "pool_best": best,
                  "epsilon": eps}
