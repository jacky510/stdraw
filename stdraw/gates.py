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


def edge_gate_check(router, i, routes, baseline, policy, msep_floor=None):
    """Acceptance check for edge i against its pre-change baseline.

    Returns True iff every criterion of ``policy`` passes for the CURRENT
    ``routes[i]``.  Purely read-only (no mutation, no caching side effects);
    deterministic; the boolean is bit-equivalent to the historical inline
    expression this call replaced (byte-identical sweep proves it).

    msep_floor overrides policy.msep_floor when given (arrival_flip passes
    its derived sep_floor; enhanced leg fixes 12.0).
    """
    _r = _rt()
    st = router._edge_stats(i, routes)
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
    # -- anchor departure smoothness --
    if st[2] < _r.ANCHOR_MIN_DEG:
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
