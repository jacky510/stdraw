# -*- coding: utf-8 -*-
"""Certificate gate registry (T17 refactor, pure move from metrics.py).

Every quality gate = an independent check function; every placement mode's
gate set = an ordered registry entry; the historical ``if ring_mode: ...
elif ... else:`` chain in ``certificate_auto`` is now data
(``MODE_GATE_SETS`` below, first match wins — the order IS the old elif
order).  The overlay section (visual crossings, annotations, routing
consistency, external gates, manual-mode N/A slots) is likewise an ordered
registry (``OVERLAYS``).

EFFECT POLICY (生效策略) — every registry entry carries a ``when`` slot so
applicability stays data-expressible:

* first version: ``when=None`` on every entry = "applies whenever this
  mode's gate set applies", exactly replicating the historical branches;
* the historical N/A slots (manual-mode ``pitch_uniform`` /
  ``column_snap24_ge_060``, planarized-L1 anchors/regularity slots,
  lens ``mutual_pairs_closed``) stay literal ``"N/A"`` entries — they are
  applicability facts, not thresholds;
* a future downgrade (e.g. "regularity gates become report items for
  n>10", stdraw20 calibration) is a ONE-LINE data change: set
  ``when=lambda ctx: ctx.n_nodes <= 10`` on the affected entries.  That
  change is owner-gated (jacky authorization) and must NOT happen as a
  side effect of this refactor.

Repair hints (T13): the hint text single source stays ``repair.GATE_HINTS``
(keyed by gate key) — this registry deliberately does NOT copy the wording;
``certificate_repair_hints`` keeps consuming it unchanged.

Extension points (declared only, NOT implemented — card requirement):
* ``GateContext.family`` slot reserved for a detect-level layout-family
  output (chain / star / single-ring / coupled-rings / nested-rings /
  mesh) to later drive a family x weight table;
* no routing-feedback hook yet (detour / fold-point counts back into
  placement) — the overlay ordering leaves room for a post-routing
  overlay stage;
* gate entries never hard-code the 16-anchor set (checks read metrics
  counters), so an anchor-vocabulary extension to multi-slot
  (n/s/e/w x 1..k, src/dst split) does not change gate signatures.
"""
from .gates import LENS_BULGE_MIN, arc_bulge
from .routing import CLEARANCE

N_A = "N/A"


class GateContext:
    """Everything the gate builders read — assembled verbatim from
    ``certificate_auto`` locals (pure move; no new computation)."""

    def __init__(self, scene, metrics, nodes, edges, ids, crossings, plz,
                 exactness, gates_param, routing_consistent,
                 annotation_layer, notes, ring_mode, radial_mode,
                 column_mode, sym_mode, bowtie_mode, spine_mode, comb_mode,
                 lens_mode, layered_mode, manual_mode, plz_l1, ring_nodes,
                 radial, comb, lens, spine_wing, symmetry, pitch_uniform,
                 snap_rate, mutual_min_sep, mutual_pairs_closed, pair_infos):
        self.scene = scene
        self.metrics = metrics
        self.nodes = nodes
        self.edges = edges
        self.ids = ids
        self.crossings = crossings
        self.plz = plz
        self.exactness = exactness
        self.gates_param = gates_param
        self.routing_consistent = routing_consistent
        self.annotation_layer = annotation_layer
        self.notes = notes
        self.ring_mode = ring_mode
        self.radial_mode = radial_mode
        self.column_mode = column_mode
        self.sym_mode = sym_mode
        self.bowtie_mode = bowtie_mode
        self.spine_mode = spine_mode
        self.comb_mode = comb_mode
        self.lens_mode = lens_mode
        self.layered_mode = layered_mode
        self.manual_mode = manual_mode
        self.plz_l1 = plz_l1
        self.ring_nodes = ring_nodes
        self.radial = radial
        self.comb = comb
        self.lens = lens
        self.spine_wing = spine_wing
        self.symmetry = symmetry
        self.pitch_uniform = pitch_uniform
        self.snap_rate = snap_rate
        self.mutual_min_sep = mutual_min_sep
        self.mutual_pairs_closed = mutual_pairs_closed
        self.pair_infos = pair_infos
        # scratch slots for builder pre-computation (radial form battery,
        # comb hub-edge scan, lens arc audit)
        self._radial_fm = None
        self._hub_bad = 0
        self._pairs = []
        self._lens_bad = 0
        # regularity gates demoted to report items by the entries' ``when``
        # policies (key -> measured boolean; filled by build_gates)
        self.demoted_gates = {}

    @property
    def n_nodes(self):
        return len(self.ids)


# ── shared core gate checks (one function per gate) ──────────────────

def g_box_press_zero(c):
    return c.metrics["box_press_1px"] == 0


def g_edge_box_clear_ge_16(c):
    return (c.metrics["edge_box_min_clear"] or 0) >= CLEARANCE


def g_anchors_smooth(c):
    return c.metrics["anchor_violations"] == 0


def g_anchors_standard(c):
    """anchors_standard criterion (jacky 2026-11-26, multi-slot vocabulary
    card): every delivered endpoint sits ON its box border and meets the
    anchor-angle floor -- the legacy 16-set membership requirement is
    retired (W9: it blocked ~80% of manually calibrated figures)."""
    return c.metrics["anchor_standard_violations"] == 0


def g_min_gap_ge_16(c):
    return c.metrics["min_card_gap"] >= 16


def g_cv_le_035(c):
    return c.metrics["spacing_cv"] <= 0.35


def g_pitch_uniform(c):
    return c.pitch_uniform


def g_column_snap24_ge_060(c):
    return (c.snap_rate is None or c.snap_rate >= 0.60)


def g_mutual_pairs_separated(c):
    return c.mutual_min_sep is None or c.mutual_min_sep >= 4.0


def g_mutual_pairs_closed(c):
    return c.mutual_pairs_closed


def g_lines_no_coincidence(c):
    return c.metrics["line_line_coincident_pairs"] == 0


def g_visual_crossings_zero(c):
    return c.metrics["visual_crossings"] == 0


# ── mode-specific gate checks ─────────────────────────────────────────

def g_ring_spacing_cv_le_050(c):
    from . import ringlayout as _ringlayout
    return (c.metrics["ring_spacing_cv"] is not None
            and c.metrics["ring_spacing_cv"]
            <= _ringlayout.RING_SPACING_CV_MAX)


def g_ring_template_fit_le_070(c):
    from . import ringlayout as _ringlayout
    return (c.metrics["ring_template_deviation"] is not None
            and c.metrics["ring_template_deviation"]
            <= _ringlayout.RING_TEMPLATE_FIT_MAX)


def g_radial_min_gap_ge_pack_floor(c):
    from . import radellayout as _rlg
    return c.metrics["min_card_gap"] >= _rlg.RADIAL_MIN_PAIR_GAP


def g_radial_hub_center_le_2px(c):
    return (c.metrics["radial_hub_center_dev"] is not None
            and c.metrics["radial_hub_center_dev"] <= 2.0)


def g_radial_centroid_dev_le_24px(c):
    _fm = c._radial_fm
    return (_fm.get("centroid_dev") is not None
            and _fm["centroid_dev"] <= _rlg_const("RADIAL_CENTROID_DEV_MAX"))


def g_radial_azimuth_cv_le_050(c):
    from . import radellayout as _rlg
    _fm = c._radial_fm
    return (_fm.get("azimuth_cv") is not None
            and _fm["azimuth_cv"] <= _rlg.RADIAL_AZ_CV_MAX)


def g_radial_radius_cv_le_015(c):
    from . import radellayout as _rlg
    _fm = c._radial_fm
    return (_fm.get("radius_cv") is not None
            and _fm["radius_cv"] <= _rlg.RADIAL_RADIUS_CV_MAX)


def g_radial_long_edge_rate_zero(c):
    _fm = c._radial_fm
    return (_fm.get("long_edge_rate") is not None
            and _fm["long_edge_rate"] == 0.0)


def g_radial_total_edge_fit_le_125(c):
    from . import radellayout as _rlg
    _fm = c._radial_fm
    return (_fm.get("fit_ratio") is not None
            and _fm["fit_ratio"] <= _rlg.RADIAL_TOTAL_EDGE_FIT)


def _rlg_const(name):
    from . import radellayout as _rlg
    return getattr(_rlg, name)


def g_column_axis_aligned(c):
    return (c.metrics["column_axis_deviation"] is not None
            and c.metrics["column_axis_deviation"] <= 2.0)


def g_spine_pitch_uniform(c):
    # column-chain caliber: the historical gate KEY is "spine_pitch_uniform"
    return c.pitch_uniform


def g_column_pitch_uniform(c):
    # comb-bilateral caliber: the historical gate KEY is "column_pitch_uniform"
    return c.pitch_uniform


def g_hub_symmetry_le_2px(c):
    return (c.metrics["hub_symmetry_err"] is not None
            and c.metrics["hub_symmetry_err"] <= 2.0)


def g_hub_edges_straight(c):
    return c._hub_bad == 0


def g_symmetry_mirror_le_2px(c):
    return (c.metrics["symmetry_mirror_err"] is not None
            and c.metrics["symmetry_mirror_err"] <= 2.0)


def g_spine_axis_le_2px(c):
    return (c.metrics["spine_axis_deviation"] is not None
            and c.metrics["spine_axis_deviation"] <= 2.0)


def g_midline_adherence_le_2px(c):
    return (c.metrics["midline_deviation"] is not None
            and c.metrics["midline_deviation"] <= 2.0)


def g_lens_pairs_closed(c):
    return bool(c._pairs) and c._lens_bad == 0


def g_lens_pair_min_sep_ge_12(c):
    return (c.metrics["lens_pair_min_sep"] is not None
            and c.metrics["lens_pair_min_sep"] >= 12.0)


# ── mode gate sets (ordered dict literals = the historical key order) ─

def _common_press_clear(c):
    return {
        "box_press_zero": g_box_press_zero(c),
        "edge_box_clear_ge_16": g_edge_box_clear_ge_16(c),
    }


def _common_anchor_gates(c):
    return {
        "anchors_smooth": g_anchors_smooth(c),
        "anchors_standard": g_anchors_standard(c),
    }


def _common_mutual_tail(c):
    return {
        "mutual_pairs_separated": g_mutual_pairs_separated(c),
        "mutual_pairs_closed": g_mutual_pairs_closed(c),
        "lines_no_coincidence": g_lines_no_coincidence(c),
    }


def _gates_ring(c):
    # Ring caliber gates: on-ring equal spacing CV + template fit error
    # (within 2px quantization tolerance ~= 0)
    g = {
        "box_press_zero": g_box_press_zero(c),
        "edge_box_clear_ge_16": g_edge_box_clear_ge_16(c),
        "anchors_smooth": g_anchors_smooth(c),
        "anchors_standard": g_anchors_standard(c),
        "min_gap_ge_16": g_min_gap_ge_16(c),
        # Ring regularity gates -- recalibrated 2026-11-16 against the
        # manual ground truth (benchmarks/manual brand-flywheel +
        # random-n10-i05): thresholds = the ringlayout manual-band
        # constants (single source).  The former 0.05 calibers were
        # uncalibrated and REJECTED jacky's hand-drawn good ring
        # itself (brand-flywheel CV 0.0802 / deviation 0.1197).
        "ring_spacing_cv_le_050": g_ring_spacing_cv_le_050(c),
        "ring_template_fit_le_070": g_ring_template_fit_le_070(c),
        "mutual_pairs_separated": g_mutual_pairs_separated(c),
        "mutual_pairs_closed": g_mutual_pairs_closed(c),
        "lines_no_coincidence": g_lines_no_coincidence(c),
    }
    return g


def _gates_radial_prep(c):
    # Radial caliber gates -- recalibrated 2026-11-15 against the
    # manual ground truth (benchmarks/manual fan-d12/fan-d17): the
    # battery is radellayout.form_metrics (single source with
    # check.py gate 9; thresholds = the radellayout manual-band
    # constants).  The former min_gap>=16 / azimuth CV<=0.05 calibers
    # REJECTED jacky's hand-drawn layouts themselves (manual minimum
    # rect-gap 6px, azimuth CV up to 0.486), so the band now reads
    # the fixtures, not the old engine's quantization floor.
    from . import radellayout as _rlg
    _card_h = float(next(iter(c.scene["nodes"].values())).get("h", 44))
    c._radial_fm = _rlg.form_metrics(c.scene["nodes"], _card_h,
                                     c.scene.get("radial") or {},
                                     [(e["a"], e["b"]) for e in c.scene["edges"]])


def _gates_radial(c):
    g = {
        "box_press_zero": g_box_press_zero(c),
        "edge_box_clear_ge_16": g_edge_box_clear_ge_16(c),
        "anchors_smooth": g_anchors_smooth(c),
        "anchors_standard": g_anchors_standard(c),
        "radial_min_gap_ge_pack_floor": g_radial_min_gap_ge_pack_floor(c),
        "radial_hub_center_le_2px": g_radial_hub_center_le_2px(c),
        "radial_centroid_dev_le_24px": g_radial_centroid_dev_le_24px(c),
        "radial_azimuth_cv_le_050": g_radial_azimuth_cv_le_050(c),
        "radial_radius_cv_le_015": g_radial_radius_cv_le_015(c),
        "radial_long_edge_rate_zero": g_radial_long_edge_rate_zero(c),
        "radial_total_edge_fit_le_125": g_radial_total_edge_fit_le_125(c),
        "mutual_pairs_separated": g_mutual_pairs_separated(c),
        "mutual_pairs_closed": g_mutual_pairs_closed(c),
        "lines_no_coincidence": g_lines_no_coincidence(c),
    }
    return g


def _gates_column(c):
    g = {
        "box_press_zero": g_box_press_zero(c),
        "edge_box_clear_ge_16": g_edge_box_clear_ge_16(c),
        "anchors_smooth": g_anchors_smooth(c),
        "anchors_standard": g_anchors_standard(c),
        "min_gap_ge_16": g_min_gap_ge_16(c),
        "cv_le_035": g_cv_le_035(c),
        "column_axis_aligned": g_column_axis_aligned(c),
        "spine_pitch_uniform": g_spine_pitch_uniform(c),
        "mutual_pairs_separated": g_mutual_pairs_separated(c),
        "mutual_pairs_closed": g_mutual_pairs_closed(c),
        "lines_no_coincidence": g_lines_no_coincidence(c),
    }
    return g


def _gates_comb_prep(c):
    # comb-bilateral caliber gates: column axis alignment + constant
    # column pitch + hub-pair mirror symmetry + all hub edges straight
    # (the comb contract); spacing CV is not applicable as a gate (the
    # hub wings are structurally far from the column, reported only)
    _hl, _hr = c.comb.get("hubs") or (None, None)
    c._hub_bad = 0
    if _hl and _hr:
        for _e, _k in zip(c.edges, c.scene.get("line_kinds") or []):
            if (_e["a"] in (_hl, _hr) or _e["b"] in (_hl, _hr)) \
                    and _k != "line":
                c._hub_bad += 1


def _gates_comb(c):
    g = {
        "box_press_zero": g_box_press_zero(c),
        "edge_box_clear_ge_16": g_edge_box_clear_ge_16(c),
        "anchors_smooth": g_anchors_smooth(c),
        "anchors_standard": g_anchors_standard(c),
        "min_gap_ge_16": g_min_gap_ge_16(c),
        "column_axis_aligned": g_column_axis_aligned(c),
        "column_pitch_uniform": g_column_pitch_uniform(c),
        "hub_symmetry_le_2px": g_hub_symmetry_le_2px(c),
        "hub_edges_straight": g_hub_edges_straight(c),
        "mutual_pairs_separated": g_mutual_pairs_separated(c),
        "mutual_pairs_closed": g_mutual_pairs_closed(c),
        "lines_no_coincidence": g_lines_no_coincidence(c),
    }
    return g


def _gates_sym_bowtie(c):
    g = {
        "box_press_zero": g_box_press_zero(c),
        "edge_box_clear_ge_16": g_edge_box_clear_ge_16(c),
        "anchors_smooth": g_anchors_smooth(c),
        "anchors_standard": g_anchors_standard(c),
        "min_gap_ge_16": g_min_gap_ge_16(c),
        "cv_le_035": g_cv_le_035(c),
        "symmetry_mirror_le_2px": g_symmetry_mirror_le_2px(c),
        "mutual_pairs_separated": g_mutual_pairs_separated(c),
        "mutual_pairs_closed": g_mutual_pairs_closed(c),
        "lines_no_coincidence": g_lines_no_coincidence(c),
    }
    return g


def _gates_spine(c):
    # spine-wing equivalent gates: the equivalent of ring CV/template fit
    # for the spine-wing shape = spine x alignment <=2px + midline
    # adherence <=2px + mirror-pair error <=2px (crossings is a soft-target
    # report item; determinism is carried by the CLI double-run
    # byte-identical gate)
    g = {
        "box_press_zero": g_box_press_zero(c),
        "edge_box_clear_ge_16": g_edge_box_clear_ge_16(c),
        "anchors_smooth": g_anchors_smooth(c),
        "anchors_standard": g_anchors_standard(c),
        "min_gap_ge_16": g_min_gap_ge_16(c),
        "cv_le_035": g_cv_le_035(c),
        "spine_axis_le_2px": g_spine_axis_le_2px(c),
        "midline_adherence_le_2px": g_midline_adherence_le_2px(c),
        "symmetry_mirror_le_2px": g_symmetry_mirror_le_2px(c),
        "mutual_pairs_separated": g_mutual_pairs_separated(c),
        "mutual_pairs_closed": g_mutual_pairs_closed(c),
        "lines_no_coincidence": g_lines_no_coincidence(c),
    }
    return g


def _gates_lens_prep(c):
    # lens-chain caliber gates (docs/layout-modes.md, lens-chain): the
    # layered regularity set (spacing CV / uniform row pitch / 24px
    # column snap) PLUS the lens contract -- every mutual pair of the
    # chain delivered as two arcs (one closed ring per 2-node loop):
    # both arcs visibly bow (apex / chord >= LENS_BULGE_MIN, opposite
    # sides -- a flattened pair is not a ring) and stay
    # >= LENS_PAIR_SEP_MIN apart (the routing
    # lens-pair joint-snap floor, routing._lens_pair_joint_snap)
    _lk = c.scene.get("line_kinds") or []
    _sep_by = {p["pair"][0]: p["pair"][1] for p in c.pair_infos}
    c._pairs = c.lens.get("pairs") or []
    _lens_bad, _lens_seps, _lens_bulges = 0, [], []
    for _row in c._pairs:
        _A, _B = _row[0], _row[1]
        _ia = [i for i, e in enumerate(c.edges) if (e["a"], e["b"]) == (_A, _B)]
        _ib = [i for i, e in enumerate(c.edges) if (e["a"], e["b"]) == (_B, _A)]
        if not _ia or not _ib or _lk[_ia[0]] != "arc" or _lk[_ib[0]] != "arc":
            _lens_bad += 1
        else:
            # closed ring = both arcs visibly bow (apex / chord >=
            # LENS_BULGE_MIN) to OPPOSITE sides of the chord
            _pl = c.scene["polylines"]
            _ct = c.scene.get("ctrls") or {}
            _ra, _sa = arc_bulge(_pl[_ia[0]], _ct.get(_ia[0]))
            _rb, _sb = arc_bulge(_pl[_ib[0]], _ct.get(_ib[0]),
                                 flip=True)
            if (_ra is None or _rb is None or _ra < LENS_BULGE_MIN
                    or _rb < LENS_BULGE_MIN or _sa == 0 or _sa == _sb):
                _lens_bad += 1
            else:
                _lens_bulges += [_ra, _rb]
        _s = _sep_by.get(f"{_A}<->{_B}", _sep_by.get(f"{_B}<->{_A}"))
        if _s is not None:
            _lens_seps.append(_s)
    c.metrics["lens_pair_min_sep"] = (round(min(_lens_seps), 1)
                                      if _lens_seps else None)
    c.metrics["lens_pair_min_bulge"] = (round(min(_lens_bulges), 3)
                                        if _lens_bulges else None)
    c._lens_bad = _lens_bad


def _gates_lens(c):
    g = {
        "box_press_zero": g_box_press_zero(c),
        "edge_box_clear_ge_16": g_edge_box_clear_ge_16(c),
        "anchors_smooth": g_anchors_smooth(c),
        "anchors_standard": g_anchors_standard(c),
        "min_gap_ge_16": g_min_gap_ge_16(c),
        "cv_le_035": g_cv_le_035(c),
        "pitch_uniform": g_pitch_uniform(c),
        "column_snap24_ge_060": g_column_snap24_ge_060(c),
        "lens_pairs_closed": g_lens_pairs_closed(c),
        "lens_pair_min_sep_ge_12": g_lens_pair_min_sep_ge_12(c),
        "mutual_pairs_separated": g_mutual_pairs_separated(c),
        # lens engine constructs its lenses before routing (lens_pairs_closed
        # above carries the contract); the non-lens rebuild pass does not run
        "mutual_pairs_closed": N_A,
        "lines_no_coincidence": g_lines_no_coincidence(c),
    }
    return g


def _gates_plz_l1(c):
    # planarized witness-marked caliber: anchors / row-column
    # regularity gates are inapplicable to the straight-line
    # planarized drawing (same N/A pattern as manual coordinates,
    # P1-2); crossings_witnessed replaces visual_crossings_zero
    # (contract section 4.3/4.6)
    g = {
        "box_press_zero": g_box_press_zero(c),
        "edge_box_clear_ge_16": g_edge_box_clear_ge_16(c),
        "min_gap_ge_16": g_min_gap_ge_16(c),
        "mutual_pairs_separated": g_mutual_pairs_separated(c),
        "mutual_pairs_closed": N_A,
        "lines_no_coincidence": g_lines_no_coincidence(c),
        "anchors_smooth": N_A,
        "anchors_standard": N_A,
        "cv_le_035": N_A,
        "pitch_uniform": N_A,
        "column_snap24_ge_060": N_A,
    }
    return g


def _gates_layered(c):
    g = {
        "box_press_zero": g_box_press_zero(c),
        "edge_box_clear_ge_16": g_edge_box_clear_ge_16(c),
        "anchors_smooth": g_anchors_smooth(c),
        "anchors_standard": g_anchors_standard(c),
        "min_gap_ge_16": g_min_gap_ge_16(c),
        "cv_le_035": g_cv_le_035(c),
        # Row alignment demoted to report item (14 hand-pulled samples show
        # row_align delta ~= 0, users do not care; placement regularity is
        # carried by uniform row pitch + column snap)
        "pitch_uniform": g_pitch_uniform(c),
        "column_snap24_ge_060": g_column_snap24_ge_060(c),
        # F1 hard gate: mutual-pair two-line minimum distance >= 4px
        # (trivially passes when no mutual pair exists)
        "mutual_pairs_separated": g_mutual_pairs_separated(c),
        # Hard gate: line-line visual coincidence pairs = 0
        "lines_no_coincidence": g_lines_no_coincidence(c),
        # closed-ring contract (mutual_pairs_closed; True without a mutual pair)
        "mutual_pairs_closed": g_mutual_pairs_closed(c),
    }
    return g


# ── THE REGISTRY ──────────────────────────────────────────────────────
# Entry = {key, check, when}.  ``when=None`` = applies whenever the mode
# set applies (first version, replicates the historical branches verbatim).
# Order of MODE_GATE_SETS = the historical elif order; first match wins.

def _regularity_applies(c):
    # ``when`` policy (jacky ruling 2026-11-26, stdraw20 manual-calibration
    # lessons doc section 5.1): the mechanical-grid regularity gates
    # (``cv_le_035`` / ``pitch_uniform`` family / ``column_snap24_ge_060``)
    # reward mechanical grids and penalize human arrangements -- on the
    # automatic pipeline they gate only n<=10 figures (the human-parity
    # tier); for n>10 they demote to certificate report items (measured
    # boolean kept in ``reports``, excluded from gates_passed / hard_ok,
    # grade semantics otherwise unchanged).  The manual (--from-layout)
    # caliber is NOT touched: manual figures keep today's slots
    # (pitch_uniform / column_snap24_ge_060 = N/A per the P1-2 ruling,
    # cv_le_035 still gating).
    return c.n_nodes <= 10 or c.manual_mode


def _entry(key, check, when=None):
    return {"key": key, "check": check, "when": when}


def _set(name, detector, builder, entries):
    return {"mode": name, "detect": detector, "builder": builder,
            "entries": entries}


def _entries(*pairs):
    return [_entry(k, fn) for k, fn in pairs]


RING_SET = _set("ring-cycle", lambda c: c.ring_mode, _gates_ring,
                _entries(("ring_spacing_cv_le_050", g_ring_spacing_cv_le_050),
                         ("ring_template_fit_le_070", g_ring_template_fit_le_070)))

RADIAL_SET = _set("radial", lambda c: c.radial_mode, _gates_radial,
                  _entries(("radial_min_gap_ge_pack_floor", g_radial_min_gap_ge_pack_floor),
                           ("radial_hub_center_le_2px", g_radial_hub_center_le_2px),
                           ("radial_centroid_dev_le_24px", g_radial_centroid_dev_le_24px),
                           ("radial_azimuth_cv_le_050", g_radial_azimuth_cv_le_050),
                           ("radial_radius_cv_le_015", g_radial_radius_cv_le_015),
                           ("radial_long_edge_rate_zero", g_radial_long_edge_rate_zero),
                           ("radial_total_edge_fit_le_125", g_radial_total_edge_fit_le_125)))

COLUMN_SET = _set("column-chain", lambda c: c.column_mode, _gates_column,
                  _entries(("column_axis_aligned", g_column_axis_aligned),)
                           + [_entry("spine_pitch_uniform", g_spine_pitch_uniform,
                                     when=_regularity_applies),
                              _entry("cv_le_035", g_cv_le_035,
                                     when=_regularity_applies)])

COMB_SET = _set("comb-bilateral", lambda c: c.comb_mode, _gates_comb,
                _entries(("column_axis_aligned", g_column_axis_aligned),)
                         + [_entry("column_pitch_uniform", g_column_pitch_uniform,
                                   when=_regularity_applies),
                            _entry("hub_symmetry_le_2px", g_hub_symmetry_le_2px),
                            _entry("hub_edges_straight", g_hub_edges_straight)])

SYM_BOWTIE_SET = _set("symmetric|bowtie-vertex",
                      lambda c: c.sym_mode or c.bowtie_mode, _gates_sym_bowtie,
                      _entries(("symmetry_mirror_le_2px", g_symmetry_mirror_le_2px),)
                               + [_entry("cv_le_035", g_cv_le_035,
                                         when=_regularity_applies)])

SPINE_SET = _set("spine-wing", lambda c: c.spine_mode, _gates_spine,
                 _entries(("spine_axis_le_2px", g_spine_axis_le_2px),
                          ("midline_adherence_le_2px", g_midline_adherence_le_2px),
                          ("symmetry_mirror_le_2px", g_symmetry_mirror_le_2px))
                          + [_entry("cv_le_035", g_cv_le_035,
                                    when=_regularity_applies)])

LENS_SET = _set("lens-chain", lambda c: c.lens_mode, _gates_lens,
                _entries(("lens_pairs_closed", g_lens_pairs_closed),
                         ("lens_pair_min_sep_ge_12", g_lens_pair_min_sep_ge_12))
                         + [_entry("cv_le_035", g_cv_le_035, when=_regularity_applies),
                            _entry("pitch_uniform", g_pitch_uniform, when=_regularity_applies),
                            _entry("column_snap24_ge_060", g_column_snap24_ge_060,
                                   when=_regularity_applies)])

PLZ_L1_SET = _set("planarized-L1", lambda c: c.plz_l1, _gates_plz_l1,
                  _entries())  # N/A slots live in the builder (applicability facts)

LAYERED_SET = _set("layered", lambda c: True, _gates_layered,
                   [_entry("cv_le_035", g_cv_le_035, when=_regularity_applies),
                    _entry("pitch_uniform", g_pitch_uniform, when=_regularity_applies),
                    _entry("column_snap24_ge_060", g_column_snap24_ge_060,
                           when=_regularity_applies)])

MODE_GATE_SETS = [RING_SET, RADIAL_SET, COLUMN_SET, COMB_SET, SYM_BOWTIE_SET,
                  SPINE_SET, LENS_SET, PLZ_L1_SET, LAYERED_SET]

# Shared core carried by every builder (kept literal inside each builder's
# dict literal above so the delivered key ORDER stays the historical one;
# the shared helpers _common_* document the commonality without reordering).


# ── overlays (mode-independent, ordered = the historical sequence) ────

def _overlay_visual_crossings(c, g):
    # ref-scrubbed: visual crossings (all-edge-pair caliber incl.
    # shared-endpoint fan pairs) is a HARD gate in every placement mode --
    # the 3-figure fan-X sweep (population-logistic / renewable-resource /
    # shifting-the-burden) closed the last legacy nonzero counts, so the
    # "awaits a legacy-number decision" report item becomes an assertion.
    # hard_ok below folds it in: a drawing with a fan X can no longer
    # grade best (honest grading: the certificate must see what the eye
    # sees).
    g["visual_crossings_zero"] = g_visual_crossings_zero(c)
    if c.plz_l1:
        # witness-marked caliber (contract section 4.2/4.6): every
        # geometric crossing must map to a planarization witness and the
        # three accounts must agree (geometry == witnesses == oracle UB)
        wit_pts = [m.get("point") for m in (c.plz.get("markers") or [])]
        from .metrics import _witness_match
        g["crossings_witnessed"] = _witness_match(
            [x.get("point") for x in c.crossings], wit_pts)
        ex_cn = (c.exactness or {}).get("crossing_number")
        g["three_account_consistent"] = bool(
            ex_cn is not None and len(c.crossings) == len(wit_pts)
            and abs(len(c.crossings) - ex_cn) < 0.5)
        g["visual_crossings_zero"] = N_A      # replaced (contract 4.6)


def _overlay_annotations(c, g):
    # annotation layer hard gates (single source stdraw/annotations.py): the
    # loop-label and delay-mark geometry is re-read from the delivered
    # coordinates and tested against the delivered boxes and lines.  Each key
    # is written only when the drawing carries the annotation (trigger writes
    # the key -- corpus bytes stay identical); hard_ok folds both in below.
    # annotation_layer=False (the CLI --no-loop-labels request): the identity
    # marks are not part of the delivered face, so their gates honestly read
    # "N/A" (same caliber as the manual-mode N/A slots: excluded from
    # gates_passed, never blocking, grade semantics unchanged).  The metrics
    # rows stay measured -- they describe layout.json, which still carries
    # the placed annotations.
    from . import annotations as _ann
    _lbls = c.scene.get("loop_labels") or []
    if _lbls:
        _vw = c.scene.get("viewBox") or [0, 0, 0, 0]
        _chh = float(next(iter(c.nodes.values())).get("h", 44))
        _lok, _lbad = _ann.labels_clear(c.nodes, list(c.scene["polylines"].values()),
                                        _lbls, _chh, _vw[2], _vw[3])
        g["loop_labels_clear"] = _lok if c.annotation_layer else N_A
        c.metrics["loop_labels"] = [
            {k: l.get(k) for k in ("id", "kind", "placed", "x", "y", "offset",
                                   "dir")}
            for l in _lbls]
        c.metrics["loop_labels_unplaced"] = sum(1 for l in _lbls if not l.get("placed"))
        if _lbad:
            c.notes.append("loop labels overlapping cards/lines: " + ", ".join(_lbad))
    _dly = c.scene.get("delay_edges") or []
    if _dly:
        _dok, _dbad, _dmin = _ann.delays_clear(
            c.nodes, [c.scene["polylines"][i] for i in range(len(c.edges))], _dly,
            [f"{e['a']}->{e['b']}" for e in c.edges],
            float(next(iter(c.nodes.values())).get("h", 44)))
        g["delay_marks_clear"] = _dok if c.annotation_layer else N_A
        c.metrics["delay_mark_min_box"] = _dmin
        c.metrics["delay_mark_count"] = sum(1 for _ in _dly)
        for _p in _dbad:
            c.notes.append("delay mark: " + _p)
    if not c.annotation_layer and (_lbls or _dly):
        c.notes.append("annotation layer suppressed by request "
                       "(--no-loop-labels): loop_labels_clear / "
                       "delay_marks_clear recorded N/A (excluded from the "
                       "pass count, never blocking; grade semantics unchanged)")


def _overlay_routing_consistent(c, g):
    if c.routing_consistent is not None:
        g["routing_consistent"] = c.routing_consistent


def _overlay_external_gates(c, g):
    if c.gates_param:
        for k, v in c.gates_param.items():
            g[k] = v


def _overlay_manual_na(c, g):
    # P1-2: manual coordinates mark the two automatic-pipeline structural
    # gates "N/A" (check.py 6a/9 caliber, jacky 2026-11-13 ruling); they are
    # excluded from the pass count and never block. This is a caliber
    # alignment, not a threshold change — no other gate is touched.
    if c.manual_mode and c.layered_mode:
        g["pitch_uniform"] = N_A
        g["column_snap24_ge_060"] = N_A


OVERLAYS = [
    ("visual_crossings", _overlay_visual_crossings),
    ("annotations", _overlay_annotations),
    ("routing_consistent", _overlay_routing_consistent),
    ("external_gates", _overlay_external_gates),
    ("manual_na", _overlay_manual_na),
]


def build_gates(c):
    """Assemble the certificate gates dict: mode gate set (registry, first
    match wins) + ordered overlays.  Returns g in the historical key order."""
    for mode_set in MODE_GATE_SETS:
        if mode_set["detect"](c):
            if mode_set["mode"] == "radial":
                _gates_radial_prep(c)
            elif mode_set["mode"] == "comb-bilateral":
                _gates_comb_prep(c)
            elif mode_set["mode"] == "lens-chain":
                _gates_lens_prep(c)
            g = mode_set["builder"](c)
            # ``when`` effect policies: a demoted entry's measured boolean
            # leaves the gates dict (no longer counted in gates_passed, no
            # longer read by hard_ok) and lands in ``c.demoted_gates`` for
            # the certificate reports transport.  n<=10 / manual figures
            # have when(c) True everywhere -> zero bytes change.
            _demoted = {}
            for entry in mode_set["entries"]:
                _w = entry["when"]
                if _w is not None and not _w(c):
                    _k = entry["key"]
                    if isinstance(g.get(_k), bool):
                        _demoted[_k] = g.pop(_k)
            c.demoted_gates = _demoted
            break
    else:
        raise AssertionError("unreachable: LAYERED_SET detects everything")
    for _name, fn in OVERLAYS:
        fn(c, g)
    return g
