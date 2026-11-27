# -*- coding: utf-8 -*-
"""T17 guard: the cert_gates registry must keep replicating the historical
per-mode gate key order and the N/A applicability slots (the reconciliation
table posted on the refactor card).  Key ORDER matters: certificate.json
bytes depend on dict insertion order."""
import ast
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
CERT_GATES = os.path.join(HERE, "..", "stdraw", "cert_gates.py")

EXPECTED = {
    "_gates_ring": ["box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
                    "anchors_standard", "min_gap_ge_16",
                    "ring_spacing_cv_le_050", "ring_template_fit_le_070",
                    "mutual_pairs_separated", "mutual_pairs_closed",
                    "lines_no_coincidence"],
    "_gates_radial": ["box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
                      "anchors_standard", "radial_min_gap_ge_pack_floor",
                      "radial_hub_center_le_2px", "radial_centroid_dev_le_24px",
                      "radial_azimuth_cv_le_050", "radial_radius_cv_le_015",
                      "radial_long_edge_rate_zero",
                      "radial_total_edge_fit_le_125",
                      "mutual_pairs_separated", "mutual_pairs_closed",
                      "lines_no_coincidence"],
    "_gates_column": ["box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
                      "anchors_standard", "min_gap_ge_16", "cv_le_035",
                      "column_axis_aligned", "spine_pitch_uniform",
                      "mutual_pairs_separated", "mutual_pairs_closed",
                      "lines_no_coincidence"],
    "_gates_comb": ["box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
                    "anchors_standard", "min_gap_ge_16",
                    "column_axis_aligned", "column_pitch_uniform",
                    "hub_symmetry_le_2px", "hub_edges_straight",
                    "mutual_pairs_separated", "mutual_pairs_closed",
                    "lines_no_coincidence"],
    "_gates_sym_bowtie": ["box_press_zero", "edge_box_clear_ge_16",
                          "anchors_smooth", "anchors_standard", "min_gap_ge_16",
                          "cv_le_035", "symmetry_mirror_le_2px",
                          "mutual_pairs_separated", "mutual_pairs_closed",
                          "lines_no_coincidence"],
    "_gates_spine": ["box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
                     "anchors_standard", "min_gap_ge_16", "cv_le_035",
                     "spine_axis_le_2px", "midline_adherence_le_2px",
                     "symmetry_mirror_le_2px", "mutual_pairs_separated",
                     "mutual_pairs_closed", "lines_no_coincidence"],
    "_gates_lens": ["box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
                    "anchors_standard", "min_gap_ge_16", "cv_le_035",
                    "pitch_uniform", "column_snap24_ge_060",
                    "lens_pairs_closed", "lens_pair_min_sep_ge_12",
                    "mutual_pairs_separated", "mutual_pairs_closed",
                    "lines_no_coincidence"],
    "_gates_plz_l1": ["box_press_zero", "edge_box_clear_ge_16", "min_gap_ge_16",
                      "mutual_pairs_separated", "mutual_pairs_closed",
                      "lines_no_coincidence", "anchors_smooth",
                      "anchors_standard", "cv_le_035", "pitch_uniform",
                      "column_snap24_ge_060"],
    "_gates_layered": ["box_press_zero", "edge_box_clear_ge_16",
                       "anchors_smooth", "anchors_standard", "min_gap_ge_16",
                       "cv_le_035", "pitch_uniform", "column_snap24_ge_060",
                       "mutual_pairs_separated", "lines_no_coincidence",
                       "mutual_pairs_closed"],
}
NA_KEYS = {
    "_gates_lens": ["mutual_pairs_closed"],
    "_gates_plz_l1": ["mutual_pairs_closed", "anchors_smooth",
                      "anchors_standard", "cv_le_035", "pitch_uniform",
                      "column_snap24_ge_060"],
}

# mode registry order = the historical elif order (first match wins)
MODE_ORDER = ["ring-cycle", "radial", "column-chain", "comb-bilateral",
              "symmetric|bowtie-vertex", "spine-wing", "lens-chain",
              "planarized-L1", "layered"]


def _builders():
    src = open(CERT_GATES, encoding="utf-8").read()
    tree = ast.parse(src)
    out = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in EXPECTED:
            assign = next(st for st in node.body
                          if isinstance(st, ast.Assign)
                          and isinstance(st.value, ast.Dict))
            keys = [k.value for k in assign.value.keys]
            na = [k.value for k, v in zip(assign.value.keys, assign.value.values)
                  if (isinstance(v, ast.Constant) and v.value == "N/A")
                  or (isinstance(v, ast.Name) and v.id == "N_A")]
            out[node.name] = (keys, na)
    return out


def test_registry_mode_order_matches_historical_elif_chain():
    import sys
    sys.path.insert(0, os.path.join(HERE, ".."))
    from stdraw import cert_gates
    got = [s["mode"] for s in cert_gates.MODE_GATE_SETS]
    assert got == MODE_ORDER


@pytest.mark.parametrize("fnname", sorted(EXPECTED))
def test_gate_key_order_and_na_slots(fnname):
    keys, na = _builders()[fnname]
    assert keys == EXPECTED[fnname], (
        f"{fnname} gate key order drifted from the reconciliation table:\n"
        f"  got      {keys}\n  expected {EXPECTED[fnname]}")
    assert sorted(na) == sorted(NA_KEYS.get(fnname, [])), (
        f"{fnname} N/A slots drifted: got {na}")
