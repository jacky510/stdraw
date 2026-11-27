# -*- coding: utf-8 -*-
"""Unified delivery-gate caliber for the routing repair passes (T4, pure refactor).

Single source of truth for the "is this repaired route acceptable" checks the
post-route_all repair passes apply.  PURE REFACTOR DISCIPLINE (T4 card body
+ default's implementation comment): every pass keeps its existing caliber
verbatim -- the historical differences are EXPRESSED as GatePolicy fields,
never unified.  The pass x caliber inventory (which pass uses what / why) and
the registered inconsistency list live in docs/routing-gates.md; whether the
calibers *should* be unified is a separate decision, not this card's.

This module must not import .routing at module import time (routing.py
imports this module; constants are resolved lazily via _rt()).
"""
import math
from dataclasses import dataclass, field

_ROUTING = None


def _rt():
    """Lazy .routing resolver (circular-import-free constant access)."""
    global _ROUTING
    if _ROUTING is None:
        from . import routing as _mod
        _ROUTING = _mod
    return _ROUTING


@dataclass(frozen=True)
class GatePolicy:
    """Which caliber an acceptance check uses (docs/routing-gates.md section 1).

    clearance_margin  threshold = cl - margin - 1e-6; None -> routing.PRESS_MARGIN
                      (the two registered calibers: 0.0 vs PRESS_MARGIN).
    own_check         "box"   -> router._own_box_ok (absolute, no interior sample
                                 point inside the PRESS_MARGIN/ROUND_GUARD-inflated
                                 own box);
                      "press" -> router._own_press monotone (<= baseline own);
                      "none"  -> no own-box check at all (fan_spread's caliber).
    press_mode        "monotone" -> _edge_stats press <= baseline stats press;
                      "zero"     -> absolute _edge_stats press == 0
                      (mutual_straight_reroute's caliber).
    check_msep        False disables the mutual-pair separation check entirely
                      (lens passes gate separation via a standalone
                      min_pair_dist >= 12 instead).
    msep_floor        None-tolerant floor (4.0 fixed / call-site variable).
    sibling           monotone sibling-cross check (needs baseline.sib).
    cert_angle        router._cert_angle_ok required.
    anchors_in_band   router._anchors_in_band required (lens_joint_reassign only).
    coincide          router._coincide_no_worse (needs baseline.coi).

    edge_gate_check(min_deg=...) overrides the anchor-smoothness floor:
    None (default) keeps routing.ANCHOR_MIN_DEG — the dense-mode branches
    pass routing.DENSE_ANCHOR_MIN_DEG for hub-box edges only.
    """
    name: str
    clearance_margin: float = 0.0    # None -> routing.PRESS_MARGIN
    own_check: str = "box"           # "box" | "press" | "none"
    press_mode: str = "monotone"     # "monotone" | "zero"
    check_msep: bool = True
    msep_floor: float = 4.0
    sibling: bool = False
    cert_angle: bool = False
    anchors_in_band: bool = False
    coincide: bool = False


# Policy presets -- one per repair pass (docs/routing-gates.md section 1).
# PASS_THROUGH constants kept per pass even where fields coincide
# (PAIR_BAND == MIDBAND_CLAMP fields): the per-pass name keeps the inventory
# table greppable and future caliber edits per pass isolated.

# G-FAN fan_spread whole-group fallback (NO own-box check -- registered
# caliber gap, docs/routing-gates.md section 3 item 2).
FAN_SPREAD = GatePolicy(name="fan_spread", own_check="none")
# G-FAN-DENSE dense-mode fan_spread branch (owner authorization;
# docs/adr/ADR-0007): same shape as G-FAN; the mutual-pair separation floor
# relaxes 4.0 -> 3.0 (proposal gate table #5: adjacent 12px dense slots can
# put a mutual pair's diagonal mid-run under 4px without overlapping) and
# the anchor-smoothness floor is overridden per call to
# routing.DENSE_ANCHOR_MIN_DEG (gate table #1).  press / clearance /
# crossing criteria are NOT relaxed (gate table #6).
FAN_SPREAD_DENSE = GatePolicy(name="fan_spread_dense", own_check="none",
                              msep_floor=3.0)
# G-PAIR-BAND _reroute_pair_band.gates_ok
PAIR_BAND = GatePolicy(name="pair_band_reroute")
# G-MIDBAND-T0 midband_reanchor Tier 0 baseline-accounting clamp acceptance
# (v0.7.2 semantics byte-carrier: NO own-box check -- registered caliber
# gap, docs/routing-gates.md section 3 item 2; fields == FAN_SPREAD).
MIDBAND_TIER0 = GatePolicy(name="midband_tier0", own_check="none")
# G-MIDBAND-T1 midband_reanchor Tier 1 enhanced-ladder acceptance
# (own-box interior check added -- the measured arc-tangent dip).
MIDBAND_CLAMP = GatePolicy(name="midband_clamp")
# G-MUTUAL-STRAIGHT mutual_straight_reroute acceptance (absolute press==0,
# absolute own-box; per-edge crossing cap via GateBaseline.cross_cap).
MUTUAL_STRAIGHT = GatePolicy(name="mutual_straight", press_mode="zero")
# G-ARRIVAL legacy (pre-snap) leg of mutual_arrival_flip.
ARRIVAL_LEGACY = GatePolicy(name="arrival_flip_legacy")
# G-ARRIVAL enhanced (post-snap) leg: inflated clearance caliber + monotone
# _own_press; msep floor passed per call (enhanced fixes it to 12.0).
ARRIVAL_ENHANCED = GatePolicy(name="arrival_flip_enhanced",
                              clearance_margin=None, own_check="press")
# G-LENS-JOINT lens_joint_reassign (no msep check here; standalone sep>=12;
# the only pass requiring _anchors_in_band).
LENS_JOINT = GatePolicy(name="lens_joint_reassign", clearance_margin=None,
                        own_check="press", check_msep=False, sibling=True,
                        cert_angle=True, anchors_in_band=True)
# G-LENS-PAIR _lens_pair_joint_snap (same as LENS_JOINT minus the band check).
LENS_PAIR = GatePolicy(name="lens_pair_joint_snap", clearance_margin=None,
                       own_check="press", check_msep=False, sibling=True,
                       cert_angle=True)
# G-LENS-CONSTRUCT mutual_lens_construct acceptance (closed-ring rebuild of
# non-lens mutual pairs on every non-lens engine): constructed arcs carry no
# coincidence by design, the pair separation is a standalone >= 12px check
# (LENS_PAIR_MIN_SEP); press / clearance (CI raw accounting) / anchor angle
# / non-adjacent crossings / own-box press / fan-pair crossings monotone.
LENS_CONSTRUCT = GatePolicy(name="mutual_lens_construct", clearance_margin=None,
                            own_check="press", check_msep=False, sibling=True,
                            cert_angle=True)
# G-SNAP anchor_snap tier-1 + _snap_joint_detour tier-2 (coincide-no-worse).
# clearance_margin=None -> cl-PRESS_MARGIN-1e-6 = the CI/certificate raw-border
# accounting (_edge_stats measures the 1px-inflated rect, so the inflated
# threshold is CLEARANCE-1; the raw >= CLEARANCE certificate stays
# authoritative -- population-logistic n-g2: inflated 15.79 = raw 16.79).
SNAP = GatePolicy(name="anchor_snap", clearance_margin=None,
                  own_check="press", sibling=True, cert_angle=True,
                  coincide=True)
# G-SNAP-RETRY _snap_retry_conflicts give-way acceptance (NO coincide check
# -- registered caliber gap, docs/routing-gates.md section 3 item 5).
SNAP_RETRY = GatePolicy(name="snap_retry_conflicts", clearance_margin=None,
                        own_check="press", sibling=True, cert_angle=True)


@dataclass
class GateBaseline:
    """Pre-change state a repair pass compares its candidate against.

    stats     edge -> _edge_stats 5-tuple (press/min_clear/ang/cross/msep).
    own       edge -> router._own_press value (monotone own-check passes).
    sib       edge -> router._sibling_cross value.
    coi       edge -> router._coincide_max_span value (coincide-no-worse).
    cross_cap edge -> explicit crossing cap; overrides stats[..][3]
                 (mutual_straight_reroute caps edge i by the replaced
                 candidate's _evaluate cross, a different accounting).
    """
    stats: dict = field(default_factory=dict)
    own: dict = field(default_factory=dict)
    sib: dict = field(default_factory=dict)
    coi: dict = field(default_factory=dict)
    cross_cap: dict = field(default_factory=dict)


def edge_gate_check(router, i, routes, baseline, policy, msep_floor=None,
                    min_deg=None, stats=None):
    """Acceptance check for edge i against its pre-change baseline.

    Returns True iff every criterion of ``policy`` passes for the CURRENT
    ``routes[i]``.  Purely read-only (no mutation, no caching side effects);
    deterministic; the boolean is bit-equivalent to the historical inline
    expression this call replaced (byte-identical sweep proves it).

    msep_floor overrides policy.msep_floor when given (arrival_flip passes
    its derived sep_floor; enhanced leg fixes 12.0).
    min_deg overrides the anchor-smoothness floor when given (None keeps
    routing.ANCHOR_MIN_DEG; dense branches pass the relaxed dense floor).
    stats overrides the internal _edge_stats(i, routes) recomputation when
    the caller already computed the identical 5-tuple on the same current
    geometry (pure dedup -- same values, one computation).
    """
    _r = _rt()
    st = stats if stats is not None else router._edge_stats(i, routes)
    st0 = baseline.stats.get(i)
    # -- box press: monotone vs before, or absolute zero --
    if policy.press_mode == "zero":
        if st[0] > 0:
            return False
    else:
        if st[0] > st0[0]:
            return False
    # -- crossing count must not increase --
    cross0 = baseline.cross_cap.get(i)
    if cross0 is None:
        cross0 = st0[3]
    if st[3] > cross0:
        return False
    # -- edge-box clearance (None tolerated; two registered margins) --
    margin = policy.clearance_margin
    if margin is None:
        margin = _r.PRESS_MARGIN
    if st[1] is not None and st[1] < router.cl - margin - 1e-6:
        return False
    # -- anchor departure smoothness (floor overridable; dense branches
    #     pass the relaxed dense floor for hub-box edges only) --
    if st[2] < (min_deg if min_deg is not None else _r.ANCHOR_MIN_DEG):
        return False
    # -- mutual-pair separation (None tolerated) --
    if policy.check_msep:
        floor = msep_floor if msep_floor is not None else policy.msep_floor
        if st[4] is not None and st[4] < floor:
            return False
    # -- own box: absolute interior check, or monotone press --
    if policy.own_check == "box":
        if not router._own_box_ok(i, routes):
            return False
    elif policy.own_check == "press":
        if router._own_press(i, routes) > baseline.own[i]:
            return False
    # -- sibling-edge crossing monotone --
    if policy.sibling and router._sibling_cross(i, routes) > baseline.sib[i]:
        return False
    # -- certificate departure-angle caliber --
    if policy.cert_angle and not router._cert_angle_ok(i, routes):
        return False
    # -- connection-point band membership --
    if policy.anchors_in_band and not router._anchors_in_band(i, routes):
        return False
    # -- line-line coincidence must not worsen --
    if policy.coincide and not router._coincide_no_worse(
            i, routes, baseline.coi[i]):
        return False
    return True


# ---- lens-chain closed-ring caliber (metrics.lens_pairs_closed, check.py
# gate 9): a lens pair is a closed ring only if BOTH arcs visibly bow.  The
# sampled arc's apex offset from its chord as a fraction of the chord length
# must reach LENS_BULGE_MIN on each arc (constructed lenses sit at 0.16 =
# LENS_K 0.32 / 2; a flattened pair reads ~0.01 = two near-straight lines)
# AND the two arcs bow to opposite sides of the chord.  Pure function on
# delivered coordinates -- one source for the certificate and the geometry
# report.
LENS_BULGE_MIN = 0.15


def arc_bulge(pts, ctrl=None, flip=False):
    """(ratio, side) of one arc against its own chord.

    ratio = |apex offset| / chord length (None on a degenerate chord);
    side = sign of the apex's cross-product offset from the chord direction
    (screen coordinates, y down), negated when ``flip`` (the reverse arc of
    a pair is measured along the pair direction).

    ``ctrl`` given = quadratic Bezier (p0, ctrl, p1): the apex sits at
    t = 0.5, apex offset = 0.5 * (ctrl - chord midpoint), exact.  Without
    ``ctrl`` the polyline's largest perpendicular offset is used (sampled
    or waypoint routes).
    """
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    chord = math.hypot(x1 - x0, y1 - y0)
    if chord < 1e-9:
        return None, 0
    ux, uy = (x1 - x0) / chord, (y1 - y0) / chord
    apex = 0.0
    if ctrl is not None:
        apex = 0.5 * ((ctrl[0] - x0) * uy - (ctrl[1] - y0) * ux)
    else:
        for p in pts:
            d = (p[0] - x0) * uy - (p[1] - y0) * ux
            if abs(d) > abs(apex):
                apex = d
    side = 1 if apex > 1e-9 else (-1 if apex < -1e-9 else 0)
    if flip:
        side = -side
    return abs(apex) / chord, side
