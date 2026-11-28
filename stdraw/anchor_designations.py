# -*- coding: utf-8 -*-
"""DSL ``@anchors`` designation accounting (certificate ``anchor_designations``).

A DSL designation (``a -> + b @anchors src=n-g4,dst=s-g6``) is a *request*,
not a guarantee: hard gates outrank user authority, so a designation whose
delivery would breach a gate falls back to the engine's own route (see
``layout_auto._manual_gate_fallback``).  Before this block existed the only
trace of that was a MISSING ``anchor_ids`` on the delivered edge -- a caller
could not tell "rejected by a gate (and why)" apart from "the engine never
consumed the hint at all".

Ownership (one source of truth per fact):

* record -- :func:`records` runs inside the layout stage that MAKES the
  decision (``layout_auto._route_stage_manual``): the status and the reason
  code are the engine's own verdict, never re-guessed from geometry.  The
  verdict rides ``layout.json`` under ``meta.anchor_designations``.
* verify -- :func:`designations_block` runs in the certificate: it copies
  the verdict and re-checks every ``applied`` claim against the DELIVERED
  artifact (endpoint on the designated anchor coordinate + the ids present
  in ``edges[].anchor_ids``).  A claim the delivery does not back is
  downgraded to ``fallback`` / ``delivered-mismatch``: the block may
  under-claim, never over-claim.

Reason codes (``reason`` appears only on ``fallback`` records):

    box-press          the designated delivery would press a box (own/foreign)
    clearance          ... would run closer than the clearance floor to a
                       foreign box
    pair-merged        ... and its reverse would read as one merged line
                       (mutual-pair separation below the floor)
    manual-override    a ``--from-layout`` ``edges[].anchors`` entry on the
                       same edge won (the more specific intent); the DSL
                       designation was not consumed
    planarized-l1      the delivery was drawn by the planarization ladder
                       (witness-marked L1 crossing layout), which does not
                       consume anchor designations at all
    not-consumed       dropped without a gate verdict (defensive: not
                       reachable through the CLI pipeline)
    other              the engine reported a fallback cause this module does
                       not classify yet -- the raw text stays in ``detail``
                       (never invent a code for it)
    delivered-mismatch engine reported ``applied`` but the delivered edge
                       does not carry the designation (certificate-side
                       downgrade)

Deliberately NOT emitted:

* ``unknown-id`` / ill-formed vocabulary -- that is an INPUT error: the DSL
  parser rejects it before layout (CLI: exit 2 + ``parse_error.json``, see
  docs/agent-interface.md「错误面契约」).  Unknown ids never reach the block.
* departure-angle / contested-slot rejections -- the fallback evaluator
  does not reject on those (a designated end is frozen by ``anchor_snap``;
  a slot contested by two designations is resolved by the give-way ladder
  on the *non*-designated sibling), so ``angle-below-floor`` /
  ``slot-conflict`` are not part of the delivered vocabulary.  A shallow
  departure is reported by the ``anchors_standard`` gate honestly instead
  of being silently re-attributed to a fallback.

Scope: DSL ``@anchors`` designations only.  ``--from-layout`` anchors keep
their own provenance (``certificate.from_layout.user_anchors`` /
``from_layout.manual_fallback``), and a graph without ``@anchors`` gets no
block at all -- zero byte impact on every anchor-free figure.
"""
import math

from .anchors import anchor_point

_SIDE_FRACS = ("src", "dst")

# Caliber: the same 0.75px endpoint tolerance the anchor-slot acceptance
# uses (layout coordinates are delivered at 0.1px resolution).
ANCHOR_MATCH_TOL = 0.75


def requested(spec):
    """The declared slots of one ``@anchors`` spec, in canonical order."""
    return {k: spec[k] for k in _SIDE_FRACS if spec.get(k)}


def classify_fallback(text):
    """Engine fallback text -> reason code (see the module docstring)."""
    t = str(text or "")
    if t.startswith("box press"):
        return "box-press"
    if t.startswith("clearance"):
        return "clearance"
    if t.startswith("mutual-pair"):
        return "pair-merged"
    return "other"


def records(graph, edges, pre_merger_keys, fallback, designated):
    """Engine-side verdict: one record per edge that declared ``@anchors``.

    ``edges`` is the layout's edge tuple sequence (same order as
    ``graph.edges``); ``pre_merger_keys`` holds the edges already claimed by
    ``--from-layout`` before the DSL merge (those win); ``fallback`` is the
    ``{edge_index: reason}`` map of the hard-gate fallback; ``designated``
    is the post-fallback designation map (an entry that survived kept its
    route and its ``ua_ends``).  Returns ``[]`` when the graph declares no
    ``@anchors`` (no call site may invent a record).
    """
    recs = []
    for i, ge in enumerate(getattr(graph, "edges", None) or []):
        ua = getattr(ge, "anchors", None)
        if not ua or i >= len(edges):
            continue
        req = requested(ua)
        if not req:
            continue
        key = edges[i]
        rec = {"edge": "%s->%s" % (key[0], key[1]), "requested": req}
        if key in pre_merger_keys:
            rec["status"] = "fallback"
            rec["reason"] = "manual-override"
            rec["detail"] = ("--from-layout edges[].anchors already "
                             "designated this edge; the DSL hint was not "
                             "consumed")
        elif i in (fallback or {}):
            text = (fallback or {})[i]
            rec["status"] = "fallback"
            rec["reason"] = classify_fallback(text)
            rec["detail"] = str(text)
        elif key not in designated:
            rec["status"] = "fallback"
            rec["reason"] = "not-consumed"
        else:
            rec["status"] = "applied"
        recs.append(rec)
    return recs


def records_not_consumed(graph, edges, reason, detail):
    """Every declared ``@anchors`` edge recorded as ``fallback/<reason>``.

    For delivery paths that do not consume designations at all (the
    planarized L1 drawing is built by the planarization ladder, not by the
    routing stage): without this the caller would see ``unrecorded`` where
    the honest answer is "this path never looked at your designations".
    """
    recs = []
    for i, ge in enumerate(getattr(graph, "edges", None) or []):
        ua = getattr(ge, "anchors", None)
        if not ua or i >= len(edges):
            continue
        req = requested(ua)
        if not req:
            continue
        key = edges[i]
        recs.append({"edge": "%s->%s" % (key[0], key[1]), "requested": req,
                     "status": "fallback", "reason": reason,
                     "detail": detail})
    return recs


def designations_block(graph, scene):
    """Certificate block; ``{}`` when the graph declares no ``@anchors``.

    Copies the engine verdict from ``scene["anchor_designations"]`` and
    verifies every ``applied`` claim against the delivered geometry.  An
    edge the engine did not report is surfaced as ``status: "unrecorded"``
    (never silently dropped).
    """
    declared = []
    for i, ge in enumerate(getattr(graph, "edges", None) or []):
        ua = getattr(ge, "anchors", None)
        if ua:
            declared.append((i, ua))
    if not declared:
        return {}
    edges = scene.get("edges") or []
    polys = scene.get("polylines") or {}
    nodes = scene.get("nodes") or {}
    anchor_ids = scene.get("anchor_ids") or []
    # the scene's edge order is the DELIVERY's order (a delivery path may
    # reorder), so look the delivered edge up by its (a, b) pair, never by
    # the declaration's index
    by_key = {}
    for k, e in enumerate(edges):
        by_key.setdefault((e["a"], e["b"]), []).append(k)
    verdicts = {}
    for rec in scene.get("anchor_designations") or []:
        if isinstance(rec, dict) and rec.get("edge"):
            verdicts[rec["edge"]] = rec
    out = []
    for _i, ua in declared:
        ge = graph.edges[_i]
        a, b = ge.a, ge.b
        slots = by_key.get((a, b))
        if not slots:
            continue
        ei = slots.pop(0)
        key = "%s->%s" % (a, b)
        req = requested(ua)
        rec = verdicts.get(key)
        if rec is None:
            rec = {"edge": key, "requested": req, "status": "unrecorded"}
        else:
            rec = dict(rec)
            rec.setdefault("requested", req)
        if rec.get("status") == "applied":
            why = _delivered_mismatch(
                nodes.get(a), nodes.get(b), req, polys.get(ei),
                anchor_ids[ei] if ei < len(anchor_ids) else None)
            if why:
                rec = {"edge": key, "requested": req, "status": "fallback",
                       "reason": "delivered-mismatch", "detail": why}
        out.append(rec)
    applied = sum(1 for r in out if r["status"] == "applied")
    fallback = sum(1 for r in out if r["status"] == "fallback")
    blk = {"edges": out, "declared": len(out),
           "applied": applied, "fallback": fallback}
    rest = len(out) - applied - fallback
    if rest:
        blk["unrecorded"] = rest
    return blk


def _delivered_mismatch(node_a, node_b, req, pts, ids):
    """First reason an ``applied`` claim is not backed by the delivery."""
    if not pts:
        return "no delivered polyline"
    ids = ids or {}
    for end, node in (("src", node_a), ("dst", node_b)):
        aid = req.get(end)
        if not aid:
            continue
        if node is None:
            return "designated end node missing from the scene"
        pt = anchor_point(node["x"], node["y"], node["w"] / 2.0,
                          node["h"] / 2.0, aid)
        if pt is None:
            return "unknown anchor id %r" % (aid,)
        ex, ey = pt
        p = pts[0] if end == "src" else pts[-1]
        d = math.hypot(float(p[0]) - ex, float(p[1]) - ey)
        if d > ANCHOR_MATCH_TOL:
            return ("%s endpoint %.2fpx off the designated %s"
                    % (end, d, aid))
        if ids.get(end) != aid:
            return "layout.json edges[].anchor_ids carries no %s=%s" % (end, aid)
    return None
