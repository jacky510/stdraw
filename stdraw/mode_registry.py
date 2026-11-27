# -*- coding: utf-8 -*-
"""Mode registry (T17 refactor, pure move from layout_auto): the layout
mode priority chain as DATA, plus the registry-driven placement dispatch.

Three-interface unification per mode:
  detect  -- the topology detector (stdraw.<mode>layout.detect_*, unchanged)
  place   -- the plan-consumption function (stdraw.layout_auto._place_*)
  gates   -- the certificate gate set (stdraw.cert_gates.MODE_GATE_SETS,
             keyed by the same placement vocabulary)

MODE_CHAIN order = the historical evaluation order; every trace entry is
appended by the same code path as before (bytes unchanged).  The coupled
column/comb/ring tier keeps its historical cross-conditions verbatim
(_run_trio); its three members are still separately registered on the
place side.

EXTENSION POINTS (declared per card T17, design-only -- NOT implemented):
1. layout family: ``ChainState.family`` is reserved for a detect-level
   family output (chain / star / single-ring / coupled-rings / nested-
   rings / mesh) to later drive a family x weight table;
2. routing-feedback hook: a post-routing overlay slot between place and
   the routing optimization loop (detour / fold-point counts fed back
   into placement) -- PLACE_CHAIN and run_mode_chain leave the seam;
3. anchor vocabulary: detect/place signatures pass opaque node/plan
   structures and never hard-code the 16-anchor set, so a multi-slot
   anchor vocabulary (n/s/e/w x 1..k, src/dst split) lands without a
   signature change.
"""
from .anchors import standard_anchors as _std_anchors  # noqa: F401 (vocab pointer)

M6 = ("sym", "bw", "sw", "comb", "column", "ring")
M7 = M6 + ("radial",)
M8 = M7 + ("lens",)


class ChainState:
    """Per-layout-run state for the mode chain (pure carrier, no logic)."""

    def __init__(self, graph, nodes, adj, widths, card_h, cfg, edges, cap,
                 dense_hub, linestyle, core, deg0, mode_rules,
                 form_fallbacks, rule_hit):
        self.graph = graph
        self.nodes = nodes
        self.adj = adj
        self.widths = widths
        self.card_h = card_h
        self.cfg = cfg
        self.edges = edges
        self.cap = cap
        self.dense_hub = dense_hub
        self.linestyle = linestyle
        self.core = core
        self.deg0 = deg0
        self.mode_rules = mode_rules
        self.form_fallbacks = form_fallbacks
        self.rule_hit = rule_hit
        self.family = None          # extension point 1 (reserved)
        self.plans = {"sym": None, "bw": None, "sw": None, "comb": None,
                      "column": None, "ring": None, "radial": None,
                      "lens": None}
        self.pos = None
        self.y = None
        self.rows = None
        self.engine = None
        self.pos_meta = None
        self.constructed = {}
        self.routes_final = None


def _resolve(dotted):
    mod, _, name = dotted.rpartition(".")
    import importlib
    return getattr(importlib.import_module(mod), name)


def _record_cap_skip(st):
    """n>12: structural modes not evaluated -- the historical tier-0 trace."""
    nodes = st.nodes
    _mode_rules = st.mode_rules
    _cap_reason = (f"n={len(nodes)} > 12 — structural modes cap at "
                   "12 nodes")
    for _nm in ("symmetric (shared-edge bowtie)", "bowtie-vertex",
                "spine-wing", "column-chain", "comb-bilateral",
                "ring-cycle"):
        _mode_rules.append({"tier": 0, "rule": _nm,
                            "triggered": False,
                            "reason": f"not evaluated: {_cap_reason}",
                            "trial_gate": None})


def _run_generic(spec, st):
    """Generic chain step: detect -> trial -> trace.  Trace policies:
    always (sym/bw/sw: entry regardless of detection),
    on_detect (radial: entry only when the detector fires),
    on_activity (lens: entry when detected or the trial produced notes)."""
    detect = _resolve(spec["detect"])
    trial = _resolve(spec["trial"])
    _why, _tw = {}, {}
    det = detect(st.graph, why=_why)
    if det is not None:
        kw = {"dense_hub": st.dense_hub} if spec.get("dense_hub") else {}
        st.plans[spec["plan_key"]] = trial(det, st.nodes, st.widths,
                                           st.card_h, st.cfg, st.edges,
                                           why=_tw, **kw)
    pol = spec["hit_policy"]
    if pol == "always":
        st.rule_hit(spec["rule"], spec["tier"], det is not None,
                    st.plans[spec["plan_key"]], _why, _tw)
    elif pol == "on_detect" and det is not None:
        st.rule_hit(spec["rule"], spec["tier"], True,
                    st.plans[spec["plan_key"]], _why, _tw)
    elif pol == "on_activity" and (det is not None or _tw):
        st.rule_hit(spec["rule"], spec["tier"], det is not None,
                    st.plans[spec["plan_key"]], _why, _tw)


def _run_trio(st):
    """The coupled column/comb/ring tier (verbatim historical block: the
    three detectors share one evaluation with cross-conditions)."""
    # late import: the trial functions live in layout_auto (call time only,
    # no import cycle)
    from .layout_auto import _column_trial, _comb_trial, _ring_trial
    graph, nodes = st.graph, st.nodes
    cfg, edges, widths, card_h, _chain_cap = (st.cfg, st.edges, st.widths,
                                              st.card_h, st.cap)
    sym_plan = st.plans["sym"]
    bw_plan = st.plans["bw"]
    sw_plan = st.plans["sw"]
    comb_plan = st.plans["comb"]
    column_plan = st.plans["column"]
    ring_plan = st.plans["ring"]
    _mode_rules = st.mode_rules
    _rule_hit = st.rule_hit
    _why_col, _why_comb, _why_ring = {}, {}, {}
    _tw_col, _tw_comb, _tw_ring = {}, {}, {}
    from . import ringlayout as _ringlayout
    from . import columnlayout as _columnlayout
    from . import comblayout as _comblayout
    _ring_detect = _ringlayout.detect_ring(graph, why=_why_ring)
    # column is detected only when ring would not take the pure-cycle/ratio branch (cover-triggered graphs with a main ring <=4 go
    # to column; large rings with k>=5 still go to ring)
    if _ring_detect is None or _ring_detect["trigger"] == "cover":
        _col = _columnlayout.detect_column(graph, why=_why_col)
        if _col is not None:
            column_plan = _column_trial(_col, nodes, widths, card_h,
                                        cfg, edges, why=_tw_col)
        _rule_hit("column-chain", 3, _col is not None, column_plan,
                  _why_col, _tw_col)
    else:
        _mode_rules.append({
            "tier": 3, "rule": "column-chain", "triggered": False,
            "reason": ("not evaluated: ring detection would take the "
                       f"{_ring_detect['trigger']} branch "
                       "(pure-cycle/ratio graphs go to ring-cycle)"),
            "trial_gate": None})
    # v0.7.7 comb-bilateral (K_{m,2} bilateral hubs) sits between
    # column and ring (preempts ring: these graphs score a high
    # non-bridge ratio with a 4-cycle "main ring" and historically
    # misfired the ring ratio branch). Against column it applies a
    # salience rule: the bilateral reading wins only when the source
    # column is strictly longer than the best column spine (in the
    # established column-chain families the spine weaves
    # hub-source-hub-source and is at least as salient — zero drift).
    _comb = _comblayout.detect_comb(graph, why=_why_comb)
    if _comb is not None and _col is not None \
            and len(_comb["column"]) <= len(_col.get("spine") or ()):
        _mode_rules.append({
            "tier": 2, "rule": "comb-bilateral", "triggered": False,
            "reason": ("detected, but not adopted: the comb source "
                       "column is not strictly longer than the best "
                       "column spine (salience rule — the column "
                       "reading wins)"),
            "trial_gate": None})
        _comb = None
    if _comb is not None:
        comb_plan = _comb_trial(_comb, nodes, widths, card_h, cfg, edges,
                                why=_tw_comb)
        _rule_hit("comb-bilateral", 2, True, comb_plan,
                  _why_comb, _tw_comb)
    if column_plan is None and comb_plan is None and _ring_detect is not None:
        ring_plan = _ring_trial(_ring_detect, nodes, widths, card_h,
                                cfg, edges, why=_tw_ring)
        _rule_hit("ring-cycle", 4, True, ring_plan,
                  _why_ring, _tw_ring)
    elif _ring_detect is None:
        _mode_rules.append({"tier": 4, "rule": "ring-cycle",
                            "triggered": False,
                            "reason": _why_ring.get("reason"),
                            "trial_gate": None})
    elif column_plan is not None or comb_plan is not None:
        _mode_rules.append({"tier": 4, "rule": "ring-cycle",
                            "triggered": False,
                            "reason": ("detected, but a higher-tier "
                                       "plan was adopted — trial not "
                                       "run"),
                            "trial_gate": None})
    st.plans["column"] = column_plan
    st.plans["comb"] = comb_plan
    st.plans["ring"] = ring_plan


MODE_CHAIN = [
    {"rule": "symmetric (shared-edge bowtie)", "tier": 1, "plan_key": "sym",
     "detect": "stdraw.symlayout.detect_bowtie",
     "trial": "stdraw.layout_auto._sym_trial",
     "hit_policy": "always",
     "guard": lambda st: st.cap},
    {"rule": "bowtie-vertex", "tier": 1, "plan_key": "bw",
     "detect": "stdraw.bowtielayout.detect_bowtie_vertex",
     "trial": "stdraw.layout_auto._bowtie_trial",
     "hit_policy": "always",
     "guard": lambda st: st.plans["sym"] is None and st.cap},
    {"rule": "spine-wing", "tier": 2, "plan_key": "sw",
     "detect": "stdraw.spinewinglayout.detect_spine_wing",
     "trial": "stdraw.layout_auto._spine_trial",
     "hit_policy": "always",
     "guard": lambda st: st.plans["bw"] is None
                         and st.plans["sym"] is None and st.cap},
    {"rule": "column/comb/ring (coupled tier)", "run": _run_trio,
     "guard": lambda st: st.plans["bw"] is None
                         and st.plans["sym"] is None
                         and st.plans["sw"] is None and st.cap},
    {"rule": "radial", "tier": 5, "plan_key": "radial",
     "detect": "stdraw.radellayout.detect_radial",
     "trial": "stdraw.layout_auto._radial_trial",
     "dense_hub": True,
     "hit_policy": "on_detect",
     "guard": lambda st: not any(st.plans[k] is not None for k in M6)},
    {"rule": "lens-chain", "tier": 5, "plan_key": "lens",
     "detect": "stdraw.lenslayout.detect_lens_chain",
     "trial": "stdraw.layout_auto._lens_trial",
     "hit_policy": "on_activity",
     "guard": lambda st: not any(st.plans[k] is not None for k in M7)},
    {"rule": "layered (existing path)", "record": True,
     "guard": lambda st: not any(st.plans[k] is not None for k in M8)},
]


def run_mode_chain(st):
    """Drive the priority chain (first matching guard wins; order = data)."""
    if not st.cap:
        _record_cap_skip(st)
    for spec in MODE_CHAIN:
        if spec["guard"](st):
            if spec.get("record"):
                st.mode_rules.append(
                    {"tier": 5, "rule": "layered (existing path)",
                     "triggered": True,
                     "reason": ("fallback: no structural mode "
                                "triggered \u2014 layered layering + "
                                "placement (byte-stable default)"),
                     "trial_gate": None})
            else:
                if "run" in spec:
                    spec["run"](st)
                else:
                    _run_generic(spec, st)


# place dispatch: historical elif order over plans; layered = fallback
PLACE_CHAIN = [
    {"plan_key": "sym", "place": "stdraw.layout_auto._place_sym"},
    {"plan_key": "bw", "place": "stdraw.layout_auto._place_bw"},
    {"plan_key": "sw", "place": "stdraw.layout_auto._place_sw"},
    {"plan_key": "comb", "place": "stdraw.layout_auto._place_comb"},
    {"plan_key": "column", "place": "stdraw.layout_auto._place_column"},
    {"plan_key": "ring", "place": "stdraw.layout_auto._place_ring"},
    {"plan_key": "radial", "place": "stdraw.layout_auto._place_radial"},
    {"plan_key": "lens", "place": "stdraw.layout_auto._place_lens"},
    {"plan_key": None, "place": "stdraw.layout_auto._place_layered"},
]


def apply_place_chain(st):
    """Consume the first adopted plan (historical elif order); no plan ->
    layered fallback."""
    for spec in PLACE_CHAIN:
        key = spec["plan_key"]
        if key is None or st.plans[key] is not None:
            _resolve(spec["place"])(st)
            return
