# -*- coding: utf-8 -*-
"""Planarized 2D layer for non-planar cores (degrade ladder L1/L2).

Implementation basis (sole authority): docs/planarization-degrade-contract.md
(@ d71263a, approved jacky 2026-11-14 D1-D4).  Oracle math is consumed
READ-ONLY from crossing_exact.py (safe_reduce / heuristic planarization /
embedding / oil insertion / _planarized_graph / _faces_from_rotation); the
drawing kernel lives HERE so the ortho frozen files stay byte-untouched.

Structure: the oracle runs PER SAFE-REDUCED CORE (oil's Euler face check
and the witness machinery are per-core calibers); every core gets a Tutte
straight-line drawing (planar cores: no witnesses; non-planar cores:
planarized H with witness markers); pruned attachment trees hang off
their parent cards deterministically; degree-0 nodes go to a parking lane.

Ladder (contract section 1):
  L0  core planar            -> this module never runs; the auto-v2 chain
                                is byte-stable by construction.
  L1  core non-planar AND planarization + witness drawing within
      CAP/BUDGET AND drawing self-verification green
                              -> planarized straight-line drawing with
                                 witness-marked crossings (grade
                                 crossed-certified when the three accounts
                                 agree on delivered coordinates).
  L2  any L1 admission failure -> generic auto-v2 path + honest
      planarization_deferred record (the caller attaches it).  Never a
      silent degradation: every fallback carries a measured reason.

Determinism (contract section 5): no wall-clock, no randomness, no
threads.  CP-SAT consumers inside crossing_exact run num_workers=1 /
random_seed=42 (existing rule).  The Tutte solve is fixed-order Gauss
elimination; every downstream quantity is derived from delivered
(rounded) coordinates only.
"""
from .delivery import stamp_coordinates_only
import math

# ── D2 visual constants ────────────────────────────────────────────────
# Contract section 3: symbol/size/color/hover style belong to
# UIDesignerBot (spec card queued; it runs after this implementation card
# and its constants become the single source then).  Until the spec
# lands, the contract-suggested defaults are pinned here as the single
# source; render.py imports from this block (no copies).
MARKER_SIZE_PX = 9          # x-symbol bounding size (contract: 8-10px)
MARKER_STROKE_PX = 1.2
MARKER_COLOR = "#64748b"    # slate: clearly lower visual weight than cards
MARKER_HOVER_BG = "rgba(100,116,139,0.14)"
MARKER_HOVER_FONT_PX = 11

# ── D1 locked numbers (jacky 2026-11-14) ──────────────────────────────
BUDGET_INSERT_STEPS = 2000  # insertion steps (one per witness crossing)
BUDGET_H_VERTICES = 600     # planarized-graph vertex cap


def cap_for(n: int) -> int:
    """L1 admission crossing cap: min(3n, 80) (contract D1)."""
    return min(3 * n, 80)

# ── drawing / verification knobs (deterministic constants) ────────────
WITNESS_EPS_PX = 1.2        # straight-through double-point half cut
WITNESS_MATCH_PX = 3.5      # geometric crossing <-> witness matching radius
                            # (the counted crossing may sit within the
                            # double-point cut zone around the marker)
WITNESS_CLUSTER_PX = 4.0    # hits within this radius of one witness count
                            # as ONE visual crossing (double-point cut zone
                            # + int-rounding noise, scale-ladder proof)
TUTTE_OUTER_R = 1000.0      # outer-face circle radius (pre-scale)
SCALE_SAFETY = 1.06         # scaling headroom before int rounding
BAND_GAP_PX = 90            # vertical gap between core bands
PARK_GAP_PX = 14            # parking lane gap for degree-0 nodes
ATTACH_DIST_PX = 60.0       # tree-node placement distance from parent
PARA_OFFSET_PX = 6.0        # parallel/reciprocal duplicate polyline offset
MIN_TRANSVERSE_DEG = 3.0    # witness legs must be at least this transversal


# ═══════════════════════════ entry ═══════════════════════════════════

def core_planarity(graph):
    """Cheap L0 gate: True when every safe-reduced core is planar.

    Zero-drift contract: this is a pure read-only probe; on True the
    caller proceeds down the untouched auto-v2 path.
    """
    import networkx as nx
    from .crossing_exact import safe_reduce
    cores, red = safe_reduce(graph)
    for cnodes, cedges in cores:
        g = nx.Graph()
        g.add_nodes_from(cnodes)
        for a, b in cedges:
            g.add_edge(a, b)
        if not nx.is_planar(g):
            return False, cores, red
    return True, cores, red


def planarized_entry(graph, cfg, linestyle):
    """auto-layout entry hook.  Returns one of:
      ("L0", None)                core planar -> caller runs the normal path
      ("L1", v4)                  planarized drawing (auto-schema v4)
      ("L2", defer_record)        caller runs the normal path and attaches
                                  the record as meta["planarization"]
    """
    planar, _cores, _red = core_planarity(graph)
    if planar:
        return ("L0", None)
    return _l1_deterministic(graph, cfg, linestyle)


def _l1_deterministic(graph, cfg, linestyle):
    """Determinism hard rule (contract section 5): networkx's planar
    deposition (and any Python-side dict/set iteration over node-id
    strings) is PYTHONHASHSEED-sensitive, so the whole L1 computation
    re-enters this module in a pinned worker process (PYTHONHASHSEED=0).
    Same input, same interpreter -> byte-identical v4.  On worker
    failure the honest fallback is the in-process computation (correct,
    flagged on stderr)."""
    import json
    import os
    import subprocess
    import sys

    if os.environ.get("STDRAW_L1_PINNED") == "1":
        from .crossing_exact import safe_reduce
        cores, _red = safe_reduce(graph)
        return _planarized_l1(graph, cfg, linestyle, cores)

    payload = {
        "graph": graph.to_dict(),
        "cfg": {"fs_title": cfg.fs_title, "fs_value": cfg.fs_value,
                "card_min_w": cfg.card_min_w,
                "value_pad_extra": cfg.value_pad_extra},
        "linestyle": linestyle,
    }
    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = (
        "import sys, json;"
        f"sys.path.insert(0, r'{pkg_parent}');"
        "from stdraw.planarized_layout import _l1_worker_main;"
        "print(_l1_worker_main(sys.stdin.read()))"
    )
    env = {**os.environ, "STDRAW_L1_PINNED": "1", "PYTHONHASHSEED": "0"}
    try:
        r = subprocess.run([sys.executable, "-c", code],
                           input=json.dumps(payload),
                           capture_output=True, text=True, env=env)
    except Exception as _exc:
        print(f"[stdraw] planarized L1 pinned worker failed ({_exc}) -- "
              "in-process fallback (determinism degraded)", file=sys.stderr)
        return _planarized_l1(graph, cfg, linestyle)
    if r.returncode != 0 or not r.stdout.strip():
        print(f"[stdraw] planarized L1 pinned worker failed "
              f"(rc={r.returncode}: {r.stderr.strip()[-200:]}) -- "
              "in-process fallback (determinism degraded)", file=sys.stderr)
        return _planarized_l1(graph, cfg, linestyle)
    out = json.loads(r.stdout.strip())
    return out["mode"], out["payload"]


def _l1_worker_main(payload_json):
    """Pinned worker entry (PYTHONHASHSEED=0): recompute the L1 drawing
    from the serialized graph.  Cores are recomputed here so the whole
    computation lives under one hash seed."""
    import json
    from .model import Graph
    from .crossing_exact import safe_reduce
    from .layout_auto import AutoConfig

    d = json.loads(payload_json)
    graph = Graph.from_dict(d["graph"])
    cfg = AutoConfig()
    for k, v in d["cfg"].items():
        setattr(cfg, k, v)
    cores, _red = safe_reduce(graph)
    mode, payload = _planarized_l1(graph, cfg, d["linestyle"], cores)
    return json.dumps({"mode": mode, "payload": payload})


# ═══════════════════════ per-core oracle ═════════════════════════════

def _core_planarize(cnodes, cedges, r=None):
    """Drawing witness for ONE core.  ``r`` is the authoritative per-core
    oracle result (same dispatch as crossing_exact: _core_exact B&B for
    n<=30 with solver, _core_heuristic otherwise) -- the drawing MUST
    achieve r["ub"] or the three-account check fails honestly.

    Priority: (a) the oracle witness (routes; exactness-proven when the
    B&B improved on oil), (b) an own oil run's events.  Planar cores
    return an empty witness set."""
    import networkx as nx
    from .crossing_exact import (_heuristic_planarization, _embed_U,
                                 oil_insertion, _has_solver)
    g = nx.Graph()
    g.add_nodes_from(cnodes)
    for a, b in cedges:
        g.add_edge(a, b)
    if nx.is_planar(g):
        return {"planar": True, "H": g, "u_chains": {}, "f_chains": {},
                "markers": [], "ub": 0}

    # (a) authoritative routes-based witness (frozen events are not
    # carried by the oracle witness; mutual-crossing witnesses cannot be
    # reconstructed from routes alone -> fall through honestly)
    w = (r or {}).get("witness")
    if w and not w.get("mutual"):
        built = _build_H_routes(cnodes, cedges, w)
        if built is not None:
            H, u_chains, f_chains, markers = built
            return {"planar": False, "H": H, "u_chains": u_chains,
                    "f_chains": f_chains, "markers": markers,
                    "ub": (r or {}).get("ub", len(markers)),
                    "h_vertices": H.number_of_nodes()}

    # (b) own oil run on the heuristic U (events carry mutual semantics)
    U, F = _heuristic_planarization(cnodes, cedges)
    rot = _embed_U(cnodes, cedges, U)
    if rot is None:
        return {"planar": False, "why": "no-U-embedding"}
    if not _has_solver():
        return {"planar": False, "why": "no-solver"}
    oil = oil_insertion(cnodes, cedges, U, F, rot, minimize=True, lex=True)
    if not (oil.get("ok") and oil.get("cost") is not None):
        return {"planar": False, "why": f"oil:{oil.get('why')}"}
    events = oil.get("events") or {}
    mutual = oil.get("mutual") or []
    from .crossing_exact import _planarized_graph
    F_tuples = [cedges[i] for i in F]
    # _planarized_graph enumerates F locally and looks events up by LOCAL
    # index; oil returns events keyed by original F indices.
    local_events = {lk: events.get(f_idx, []) for lk, f_idx in enumerate(F)}
    H = _planarized_graph(cnodes, cedges, U, F_tuples, F, local_events,
                          mutual)
    if H is None:
        return {"planar": False, "why": "oil:broken-route"}

    u_chains = {i: [] for i in U}
    f_chains = {}
    markers = []
    split = {i: (cedges[i][0], cedges[i][1]) for i in U}
    mutual_vid = {}
    xc = 0
    for f_idx in F:
        a, b = cedges[f_idx]
        prev = a
        vids = []
        for item in events.get(f_idx, []):
            if item[0] == "x":
                gg = item[1]
                # NOTE: vid naming MUST match crossing_exact._planarized_graph
                # (f"X{xc}", minted in the same walk order) so chains and H
                # reference the same virtual vertices.
                vid = f"X{xc}"
                xc += 1
                markers.append({"vid": vid, "kind": "witness",
                                "members": [(a, b), cedges[gg]]})
                ga, gb = split[gg]
                split[gg] = (ga, vid)
                u_chains[gg].append(vid)
            elif item[0] == "m":
                pk = item[1]
                if pk not in mutual_vid:
                    k1, k2 = sorted(pk)
                    vid = f"X{xc}"
                    xc += 1
                    mutual_vid[pk] = vid
                    markers.append({
                        "vid": vid, "kind": "witness",
                        "members": [(cedges[F[k1]][0], cedges[F[k1]][1]),
                                    (cedges[F[k2]][0], cedges[F[k2]][1])]})
                vid = mutual_vid[pk]
            else:
                return {"planar": False, "why": "oil:bad-event"}
            vids.append(vid)
            prev = vid
        f_chains[f_idx] = vids
    return {"planar": False, "H": H, "u_chains": u_chains,
            "f_chains": f_chains, "markers": markers, "ub": oil["cost"],
            "h_vertices": H.number_of_nodes()}


def _quick_planar(cnodes, cedges):
    import networkx as nx
    g = nx.Graph()
    g.add_nodes_from(cnodes)
    for a, b in cedges:
        g.add_edge(a, b)
    return nx.is_planar(g), None


def _build_H_routes(cnodes, cedges, w):
    """Reconstruct H + markers from an oracle routes-only witness (the
    shape crossing_exact puts in exactness["witness"]: {"F", "routes",
    "mutual"}).  Returns (H, u_chains, f_chains, markers) or None when
    the witness is not routes-reconstructable (F-segment crossings or
    mutual crossings)."""
    import networkx as nx
    F_idx = list(w["F"])
    routes = w.get("routes") or {}
    U_idx = [i for i in range(len(cedges)) if i not in set(F_idx)]
    H = nx.Graph()
    H.add_nodes_from(cnodes)
    for i in U_idx:
        H.add_edge(*cedges[i])
    split = {i: (cedges[i][0], cedges[i][1]) for i in U_idx}
    u_chains = {i: [] for i in U_idx}
    f_chains = {}
    markers = []
    xc = 0
    for f_idx in F_idx:
        route = routes.get(f_idx)
        if route is None:
            return None
        a, b = cedges[f_idx]
        prev = a
        vids = []
        for cid in route.get("crossings", []):
            if not isinstance(cid, int):
                return None
            vid = f"X{xc}"
            xc += 1
            markers.append({"vid": vid, "kind": "witness",
                            "members": [(a, b), cedges[cid]]})
            # subdivide the crossed edge in path order + connect the F
            # path (mirror of crossing_exact._planarized_graph semantics)
            ga, gb = split[cid]
            H.remove_edge(ga, gb)
            H.add_edge(ga, vid)
            H.add_edge(vid, gb)
            split[cid] = (ga, vid)
            u_chains[cid].append(vid)
            H.add_edge(prev, vid)
            vids.append(vid)
            prev = vid
        H.add_edge(prev, b)
        f_chains[f_idx] = vids
    return H, u_chains, f_chains, markers


# ═══════════════════════ drawing kernel ══════════════════════════════

def _tutte_positions(H):
    """Deterministic straight-line planar drawing of one connected
    planar H via networkx's Chrobak-Payne canonical-ordering deposition
    (nx.combinatorial_embedding_to_pos: guaranteed crossing-free output
    on the embedding's integer grid).  Re-verification of the oracle
    (contract section 1): returns None when H fails nx.check_planarity
    or the deposition rejects the shape.  Returns {v: (x, y)}."""
    import networkx as nx
    planar, emb = nx.check_planarity(H)
    if not planar:
        return None
    try:
        raw = nx.combinatorial_embedding_to_pos(emb)
    except Exception:
        return None
    return {v: (float(raw[v][0]), float(raw[v][1])) for v in H.nodes}


def _pair_scale_factor(pos, cards, mids, half_w, half_h, m_sep, sep):
    """Minimum uniform scale so every card pair (and marker-vs-card /
    marker-vs-marker pair) keeps >= sep px separation in at least one
    axis (box-gap OR semantics, certificate min_card_gap caliber)."""
    need = 1.0

    def _pair(u, v, nu, nv):
        dx = abs(pos[u][0] - pos[v][0])
        dy = abs(pos[u][1] - pos[v][1])
        fx = nu / dx if dx > 1e-9 else float("inf")
        fy = nv / dy if dy > 1e-9 else float("inf")
        return min(fx, fy)

    for i, u in enumerate(cards):
        for v in cards[i + 1:]:
            need = max(need, _pair(u, v, half_w[u] + half_w[v] + sep,
                                   half_h[u] + half_h[v] + sep))
    for m in mids:
        for v in cards:
            need = max(need, _pair(m, v, m_sep + half_w[v],
                                   m_sep + half_h[v]))
    for i, m in enumerate(mids):
        for v in mids[i + 1:]:
            need = max(need, _pair(m, v, 2 * m_sep, 2 * m_sep))
    return need


def _ray_border(cx, cy, tx, ty, hw, hh):
    """Point where the segment from a card center toward (tx, ty) crosses
    the box border (deterministic parametric clip)."""
    dx, dy = tx - cx, ty - cy
    ts = []
    if abs(dx) > 1e-12:
        ts.append(hw / abs(dx))
    if abs(dy) > 1e-12:
        ts.append(hh / abs(dy))
    t = min(ts) if ts else 0.0
    return (cx + dx * t, cy + dy * t)


def _seg_point(p1, p2, p3, p4):
    """Intersection point of two (properly crossing) segments —
    deterministic line-line solve (caller guarantees seg_cross fired)."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-12:
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


# ═══════════════════════ L1 assembly ═════════════════════════════════

def _planarized_l1(graph, cfg, linestyle, cores):
    """Build the L1 planarized v4, or return the L2 defer record."""
    import math
    import networkx as nx
    from .routing import (sample_polyline, dist_point_rect, seg_cross,
                          CLEARANCE)
    from .textmetrics import card_size
    from .crossing_exact import undirected_edges

    n = len(graph.nodes)
    cap = cap_for(n)

    def _defer(reasons, measured):
        return {"mode": "L2",
                "deferred": {"reason": reasons, "measured": measured},
                "caliber": ("planarization degrade ladder L2 (docs/"
                            "planarization-degrade-contract.md): L1 "
                            "admission failed; generic auto-v2 path kept, "
                            "grade stays honestly uncertified")}

    edges, selfloops = undirected_edges(graph)
    edge_gidx = [i for i, e in enumerate(graph.edges) if e.a != e.b]

    # ── per-core oracle.  Dispatch threshold: the B&B exact layer is
    # cost-prohibitive beyond ~10-node cores (measured: n10 core ~1min,
    # n20 core hours), so cores >10 nodes use the heuristic UB
    # (witness-verified real drawing, proven_optimal stays False —
    # honest).  Deviation from crossing_exact's own n<=30 dispatch is a
    # D4 cost call (jacky's contract clause: solve-time over budget is
    # reported, never silently downgraded) -- see the implementation
    # card's measured numbers.
    from .crossing_exact import _core_heuristic, _core_exact, _has_solver
    _EXACT_MAX_CORE_NODES = 10
    core_results = []
    exactness = {"crossing_number": 0, "proven_optimal": True, "lb": 0,
                 "gap": 0, "coverage": "full", "method": "",
                 "witness": [], "reduced": None}
    total_ub = total_lb = 0
    proven, coverage = True, "full"
    witnesses, methods = [], []
    c_ub = 0
    h_vertices = 0
    for ci, (cnodes, cedges) in enumerate(cores):
        planar, _emb = _quick_planar(cnodes, cedges)
        if len(cnodes) > _EXACT_MAX_CORE_NODES or not _has_solver():
            r = _core_heuristic(cnodes, cedges)
        else:
            r = _core_exact(cnodes, cedges, 4000, 200000, 400)
        methods.append(r["method"])
        total_ub += r["ub"]
        total_lb += r["lb"]
        proven = proven and r["proven"]
        if r["coverage"] == "partial":
            coverage = "partial"
        if not planar:
            dr = _core_planarize(cnodes, cedges, r)
            if not dr.get("planar") and "why" in dr:
                return ("L2", _defer(
                    [f"no-witness-drawing: core {ci} planarization failed "
                     f"({dr['why']})"], r["ub"]))
            core_results.append((ci, cnodes, cedges, dr))
            c_ub += dr.get("ub", 0)
            h_vertices += dr["H"].number_of_nodes()
            if r.get("witness"):
                witnesses.append(r["witness"])
        else:
            # planar core: nothing to draw beyond the core itself, but it
            # still needs a band -- feed the core graph as its own H
            import networkx as _nx
            g = _nx.Graph()
            g.add_nodes_from(cnodes)
            for a, b in cedges:
                g.add_edge(a, b)
            core_results.append((ci, cnodes, cedges,
                                 {"planar": False, "H": g, "u_chains": {},
                                  "f_chains": {}, "markers": [], "ub": 0}))
    if not cores:
        coverage = "trivial"
        methods = ["trivial (0 crossings by reduction)"]
    exactness = {
        "crossing_number": total_ub,
        "proven_optimal": proven,
        "lb": total_lb,
        "gap": total_ub - total_lb,
        "coverage": coverage,
        "method": "; ".join(dict.fromkeys(methods)),
        "witness": witnesses,
        "reduced": None,
    }
    c_ub = exactness["crossing_number"]
    if c_ub > cap:
        return ("L2", _defer(
            [f"cap-exceeded: crossings UB {c_ub} > CAP min(3n,80)={cap}"],
            c_ub))
    if c_ub > BUDGET_INSERT_STEPS:
        return ("L2", _defer(
            [f"budget-exceeded: insertion steps {c_ub} > "
             f"{BUDGET_INSERT_STEPS}"], "budget-exceeded"))
    if h_vertices > BUDGET_H_VERTICES:
        return ("L2", _defer(
            [f"budget-exceeded: planarized H vertices {h_vertices} > "
             f"{BUDGET_H_VERTICES}"], "budget-exceeded"))

    # ── card geometry ──
    ids = graph.id2node()
    sizes = {}
    card_h = 0
    for v in graph.node_ids():
        nd = ids[v]
        w, h = card_size(nd.label, nd.value, cfg.fs_title, cfg.fs_value,
                         min_w=cfg.card_min_w, value_pad=cfg.value_pad_extra)
        sizes[v] = (w, h)
        card_h = max(card_h, h)
    half_w = {v: sizes[v][0] / 2 for v in sizes}
    half_h = {v: card_h / 2 for v in sizes}

    # ── draw each core band (Tutte + uniform scale) ──
    scaled = {}
    marker_xy = {}
    node_xy = {}
    core_of_edge = {}       # (a, b) tuple -> (core band idx, edge idx in core)
    off_y = 0.0
    markers_all = []
    for ci, cnodes, cedges, r in core_results:
        comp_pos = []
        for comp in sorted(nx.connected_components(r["H"]), key=min):
            sub = r["H"].subgraph(comp).copy()
            pos = _tutte_positions(sub)
            if pos is None:
                return ("L2", _defer(
                    ["drawing-solve-degenerate: Tutte system singular or "
                     "H failed re-planarity (contract section 1: "
                     "impossible -- bug)"], c_ub))
            comp_pos.append((sub, pos))
        for sub, pos in comp_pos:
            vid_set = {m["vid"] for m in r["markers"]}
            cards = sorted(v for v in sub.nodes if v not in vid_set)
            mids = sorted(v for v in sub.nodes if v in vid_set)
            m_sep = MARKER_SIZE_PX / 2 + 8.0
            factor = _pair_scale_factor(pos, cards, mids, half_w, half_h,
                                        m_sep, 16.0) * SCALE_SAFETY
            sp = {v: (pos[v][0] * factor, pos[v][1] * factor) for v in pos}
            xs = min(p[0] for p in sp.values())
            ys = min(p[1] for p in sp.values())
            sp = {v: (p[0] - xs, p[1] - ys + off_y) for v, p in sp.items()}
            for v, p in sp.items():
                x, y = round(p[0]), round(p[1])
                x += x % 2
                y += y % 2
                if v in vid_set:
                    marker_xy[v] = (x, y)
                    markers_all.append(next(m for m in r["markers"]
                                            if m["vid"] == v))
                else:
                    node_xy[v] = [x, y]
            off_y += max(p[1] for p in sp.values()) + BAND_GAP_PX
        for ei, (a, b) in enumerate(cedges):
            core_of_edge[(a, b)] = (ci, ei)

    # ── attachment trees (safe-reduction leftovers) ──
    core_node_set = set()
    for ci, cnodes, cedges, r in core_results:
        core_node_set.update(cnodes)
    attach_edges = []       # (idx in edges, a, b)
    for i, (a, b) in enumerate(edges):
        if (a, b) not in core_of_edge:
            attach_edges.append((i, a, b))
    tree_nodes = sorted(v for v in graph.node_ids()
                        if v not in core_node_set and any(v in (x, y)
                                                          for _i, x, y
                                                          in attach_edges))
    chain_of = {}
    for ci, cnodes, cedges, r in core_results:
        for i in r.get("u_chains", {}):
            chain_of[(ci, i)] = r["u_chains"][i]
        for f in r.get("f_chains", {}):
            chain_of[(ci, f)] = r["f_chains"][f]

    # core edge -> edges index mapping (single deterministic pass)
    core_edge_map = []
    used = {}
    for ci, cnodes, cedges, r in core_results:
        for ei, (a, b) in enumerate(cedges):
            core_edge_map.append((_match_edge(edges, used, a, b),
                                  ci, ei, a, b))

    def _core_polys(node_xy, marker_xy):
        """Delivered polylines for CORE edges only (attachment escape
        rays are tested against these)."""
        polys = {}
        for (idx, ci, ei, a, b) in core_edge_map:
            vids = chain_of.get((ci, ei), [])
            raw = [(node_xy[a][0], node_xy[a][1])]
            raw += [marker_xy[v] for v in vids]
            raw.append((node_xy[b][0], node_xy[b][1]))
            pts = _straight_through(raw)
            s0 = (_ray_border(node_xy[a][0], node_xy[a][1], pts[1][0],
                              pts[1][1], half_w[a], half_h[a])
                  if len(pts) > 1 else (node_xy[a][0], node_xy[a][1]))
            s1 = (_ray_border(node_xy[b][0], node_xy[b][1], pts[-2][0],
                              pts[-2][1], half_w[b], half_h[b])
                  if len(pts) > 1 else (node_xy[b][0], node_xy[b][1]))
            polys[idx] = [s0] + pts[1:-1] + [s1]
        return polys

    core_polys = _core_polys(node_xy, marker_xy)
    obstacle_segs = [seg for pts in core_polys.values()
                     for seg in zip(pts[:-1], pts[1:])]

    def _seg_clear(s0, s1, a, b):
        """Escape-ray test: crossing-free vs obstacles + clearance >= 16
        to non-endpoint cards (endpoint attachment zones are exempt via
        the anchor trim)."""
        segvec = (s1[0] - s0[0], s1[1] - s0[1])
        L = math.hypot(*segvec)
        steps = max(int(L // 6.0), 1)
        for t in range(steps + 1):
            tt = t / steps
            px_, py_ = s0[0] + segvec[0] * tt, s0[1] + segvec[1] * tt
            for q in node_xy:
                if q in (a, b):
                    continue
                if dist_point_rect(px_, py_, node_xy[q][0], node_xy[q][1],
                                   half_w[q], half_h[q]) < CLEARANCE:
                    return False
        for seg in obstacle_segs:
            if seg_cross(seg[0], seg[1], tuple(s0), tuple(s1)):
                return False
        return True

    # ── attachment trees (safe-reduction leftovers) ──
    # deterministic BFS placement around already-placed parents; leaves
    # prefer OUTWARD directions (away from the drawing centroid) and the
    # adopted direction must pass the escape-ray test (no crossing with
    # core polylines / already-placed attachment edges, clearance ok)
    tree_nodes = sorted(v for v in graph.node_ids()
                        if v not in core_node_set and any(v in (x, y)
                                                          for _i, x, y
                                                          in attach_edges))
    placed = {v: (node_xy[v][0], node_xy[v][1]) for v in node_xy}
    centroid = ((sum(p[0] for p in placed.values()) / len(placed)),
                (sum(p[1] for p in placed.values()) / len(placed)))
    directions = [(math.cos(math.pi / 4 * k), math.sin(math.pi / 4 * k))
                  for k in range(8)]
    outward = {}
    for v in tree_nodes:
        parents = [x for _i, x, y in attach_edges if v in (x, y)
                   for x in ([x] if x != v else [])] + \
                  [y for _i, x, y in attach_edges if v in (x, y)
                   for y in ([y] if y != v else [])]
        ready = [p for p in parents if p in placed]
        if ready:
            p0 = placed[sorted(ready)[0]]
            vx, vy = p0[0] - centroid[0], p0[1] - centroid[1]
            nrm = math.hypot(vx, vy) or 1.0
            outward[v] = (vx / nrm, vy / nrm)
    pending = list(tree_nodes)
    guard = 0
    unplaceable = []
    while pending and guard < 1000:
        guard += 1
        progressed = False
        for v in list(pending):
            parents = [x for _i, x, y in attach_edges if v in (x, y)
                       for x in ([x] if x != v else [])] + \
                      [y for _i, x, y in attach_edges if v in (x, y)
                       for y in ([y] if y != v else [])]
            ready = [p for p in parents if p in placed]
            if not ready:
                continue
            parent = sorted(ready)[0]
            ov = outward.get(v)
            scored = []
            for d in directions:
                dpx = placed[parent][0] + d[0] * (half_w[parent]
                                                  + half_w[v] / 2
                                                  + ATTACH_DIST_PX)
                dpy = placed[parent][1] + d[1] * (half_h[parent] + card_h / 2
                                                  + ATTACH_DIST_PX)
                score = min((max(abs(dpx - placed[q][0])
                                 - half_w[parent] - half_w[q],
                                 abs(dpy - placed[q][1])
                                 - half_h[parent] - half_h[q])
                             for q in placed), default=1e9)
                if ov is not None:
                    score += 1000.0 * (d[0] * ov[0] + d[1] * ov[1])
                scored.append((score, d))
            scored.sort(key=lambda t: -t[0])
            adopted = None
            dist_mul = 1.0
            for _round in range(3):
                for _score, d in scored:
                    dpx = (placed[parent][0]
                           + d[0] * (half_w[parent] + half_w[v] / 2
                                     + ATTACH_DIST_PX * dist_mul))
                    dpy = (placed[parent][1]
                           + d[1] * (half_h[parent] + card_h / 2
                                     + ATTACH_DIST_PX * dist_mul))
                    cand = (round(dpx), round(dpy))
                    if any(abs(cand[0] - q[0]) < 2 and abs(cand[1] - q[1]) < 2
                           for q in placed.values()):
                        continue
                    s0 = _ray_border(placed[parent][0], placed[parent][1],
                                     cand[0], cand[1], half_w[parent],
                                     half_h[parent])
                    s1 = _ray_border(cand[0], cand[1], placed[parent][0],
                                     placed[parent][1], half_w[v],
                                     half_h[v])
                    if _seg_clear(s0, s1, parent, v):
                        adopted = cand
                        break
                if adopted is not None:
                    break
                dist_mul *= 1.6
            if adopted is None:
                unplaceable.append(v)
                pending.remove(v)
                progressed = True
                continue
            placed[v] = adopted
            node_xy[v] = [adopted[0] + adopted[0] % 2,
                          adopted[1] + adopted[1] % 2]
            s0 = _ray_border(placed[parent][0], placed[parent][1],
                             adopted[0], adopted[1], half_w[parent],
                             half_h[parent])
            s1 = _ray_border(adopted[0], adopted[1], placed[parent][0],
                             placed[parent][1], half_w[v], half_h[v])
            obstacle_segs.append((s0, s1))
            pending.remove(v)
            progressed = True
        if not progressed:
            break
    if unplaceable:
        return ("L2", _defer(
            ["attachment-placement: no escape-ray direction for tree "
             f"node(s) {sorted(unplaceable)[:3]}"], c_ub))
    if pending:
        return ("L2", _defer(
            ["attachment-placement: unreachable tree node(s) "
             f"{pending[:3]}"], c_ub))

    def _build_polys(node_xy, marker_xy):
        """Delivered polylines from current integer positions (pure
        function of coordinates + chains — reusable for the clearance
        scale-up retry)."""
        polys, wit_by_idx = {}, {}
        for (idx, ci, ei, a, b) in core_edge_map:
            vids = chain_of.get((ci, ei), [])
            wit_by_idx[idx] = vids
            raw = [(node_xy[a][0], node_xy[a][1])]
            raw += [marker_xy[v] for v in vids]
            raw.append((node_xy[b][0], node_xy[b][1]))
            pts = _straight_through(raw)
            s0 = (_ray_border(node_xy[a][0], node_xy[a][1], pts[1][0],
                              pts[1][1], half_w[a], half_h[a])
                  if len(pts) > 1 else (node_xy[a][0], node_xy[a][1]))
            s1 = (_ray_border(node_xy[b][0], node_xy[b][1], pts[-2][0],
                              pts[-2][1], half_w[b], half_h[b])
                  if len(pts) > 1 else (node_xy[b][0], node_xy[b][1]))
            pts = [s0] + pts[1:-1] + [s1]
            polys[idx] = [[float(p[0]), float(p[1])] for p in pts]
        for (i, a, b) in attach_edges:
            wit_by_idx[i] = []
            s0 = _ray_border(node_xy[a][0], node_xy[a][1], node_xy[b][0],
                             node_xy[b][1], half_w[a], half_h[a])
            s1 = _ray_border(node_xy[b][0], node_xy[b][1], node_xy[a][0],
                             node_xy[a][1], half_w[b], half_h[b])
            polys[i] = [[float(s0[0]), float(s0[1])],
                        [float(s1[0]), float(s1[1])]]
        seen_pair = {}
        for i, (a, b) in enumerate(edges):
            if i not in polys:
                continue
            key = tuple(sorted((a, b)))
            k = seen_pair.get(key, 0)
            seen_pair[key] = k + 1
            if k:
                polys[i] = _offset_poly(polys[i], k)
        return polys, wit_by_idx

    wit_by_idx = {}
    failures = []
    node_xy0 = {v: list(p) for v, p in node_xy.items()}
    marker_xy0 = dict(marker_xy)
    # multiplicative scale ladder: straight chords pass near other cards'
    # fixed-size rects, and int rounding at small scales can tip
    # near-tangent chord pairs into spurious crossings — both are scale
    # defects; uniform scaling clears them (deterministic ladder, report
    # the last attempt honestly if none passes)
    for mul in (1.0, 2.2, 4.8, 10.5):
        if mul == 1.0:
            node_xy = {v: list(p) for v, p in node_xy0.items()}
            marker_xy = dict(marker_xy0)
        else:
            node_xy = {v: _even_scale(p, mul) for v, p in node_xy0.items()}
            marker_xy = {v: _even_scale(p, mul) for v, p in marker_xy0.items()}
        polys, wit_by_idx = _build_polys(node_xy, marker_xy)
        failures, diag = _verify(edges, polys, node_xy, half_w, half_h,
                                 marker_xy, sample_polyline,
                                 dist_point_rect, seg_cross, CLEARANCE)
        if not failures:
            break
    if failures:
        return ("L2", _defer(
            [f"drawing-verification: {'; '.join(failures[:3])}"], c_ub))

    # ── deg0 parking lane (deterministic) ──
    deg0 = [v for v in graph.node_ids() if v not in node_xy]
    park_y = (max((node_xy[v][1] + half_h[v] for v in node_xy), default=0)
              + 60)
    px = 30.0
    for v in deg0:
        w = sizes[v][0]
        node_xy[v] = [round(px + w / 2), round(park_y)]
        node_xy[v][0] += node_xy[v][0] % 2
        node_xy[v][1] += node_xy[v][1] % 2
        px += w + PARK_GAP_PX

    # ── global shift into the positive quadrant ──
    all_pts = [tuple(p) for pl_ in polys.values() for p in pl_]
    xs0 = min([node_xy[v][0] - half_w[v] for v in node_xy]
              + [p[0] - 8 for p in all_pts])
    ys0 = min([node_xy[v][1] - half_h[v] for v in node_xy]
              + [p[1] - 8 for p in all_pts])
    dx, dy = -xs0 + 4, -ys0 + 4   # check7 wants boxes strictly inside (>0)
    for v in node_xy:
        node_xy[v][0] += dx
        node_xy[v][1] += dy
    marker_xy = {k: (p[0] + dx, p[1] + dy) for k, p in marker_xy.items()}
    polys = {i: [[p[0] + dx, p[1] + dy] for p in pl_]
             for i, pl_ in polys.items()}

    # ── edges_out ──
    edges_out = []
    for gi, e in enumerate(graph.edges):
        if e.a == e.b:
            pts = _selfloop_poly(node_xy[e.a], half_w[e.a], half_h[e.a], gi)
            vids = []
        else:
            ei = edge_gidx.index(gi)
            pts = polys[ei]
            vids = wit_by_idx.get(ei, [])
        a_pt, b_pt = pts[0], pts[-1]
        edges_out.append({
            "a": e.a, "b": e.b,
            "polarity": getattr(e, "polarity", "+"),
            "loop_kinds": [], "loop_color": None,
            "route": {"kind": "polyline",
                      "points": [[round(p[0], 1), round(p[1], 1)]
                                 for p in pts]},
            "anchors": {"a": [round(a_pt[0], 1), round(a_pt[1], 1)],
                        "b": [round(b_pt[0], 1), round(b_pt[1], 1)]},
            "arrow": [round(b_pt[0], 1), round(b_pt[1], 1)],
            "route_cross_edges": len(vids),
        })

    # ── markers payload (contract section 3) ──
    lbv = exactness["lb"]
    markers_payload = []
    for k, m in enumerate(markers_all, start=1):
        pt = marker_xy[m["vid"]]
        markers_payload.append({
            "witness_id": k,
            "point": [round(pt[0], 1), round(pt[1], 1)],
            "edges": [list(m["members"][0]), list(m["members"][1])],
        })

    all_pts = [p for pl_ in polys.values() for p in pl_]
    W = max([node_xy[v][0] + half_w[v] for v in node_xy]
            + [p[0] for p in all_pts]) + 24
    Ht = max([node_xy[v][1] + half_h[v] for v in node_xy]
             + [p[1] for p in all_pts]) + 24
    W = ((int(W) + 7) // 8) * 8
    Ht = ((int(Ht) + 7) // 8) * 8

    plan_meta = {
        "mode": "L1",
        "cap": cap,
        "budget": {"insert_steps": BUDGET_INSERT_STEPS,
                   "h_vertices": BUDGET_H_VERTICES},
        "ub": c_ub, "lb": lbv, "gap": c_ub - lbv,
        "witness_count": len(markers_payload),
        "markers": markers_payload,
        "exactness": exactness,
        "caliber": ("planarized L1 (docs/planarization-degrade-contract.md): "
                    "every crossing sits on a planarization witness; the "
                    "three accounts (geometric recount == witness count == "
                    "oracle UB) must agree for crossed-certified"),
        "marker_style": {"size_px": MARKER_SIZE_PX,
                         "stroke_px": MARKER_STROKE_PX,
                         "color": MARKER_COLOR},
    }

    v4 = {
        "viewBox": [0, 0, W, Ht],
        "nodes": {v: {"x": node_xy[v][0], "y": node_xy[v][1],
                      "w": sizes[v][0]} for v in node_xy},
        "edges": edges_out,
        "bars": {},
        "meta": {
            "rows": 0, "rowY": [], "pitch": None,
            "deg0": deg0,
            "cardH": card_h,
            "fs": [cfg.fs_title, cfg.fs_value],
            "recipe": "auto-v2",
            "line_style": linestyle,
            "position_engine": "planarized",
            "mode_decision_trace": {
                "engine": "planarized", "placement": "planarized",
                "manual": False, "rules": [],
                "fallback": {"used": False, "reason": None},
                "planarization": {"mode": "L1", "cap": cap, "ub": c_ub,
                                  "h_vertices": h_vertices,
                                  "cores": len(core_results)},
            },
            "clearance": 16,
            "router_cross_pairs": c_ub,
            "anchor_snap_deferred": None,
            "edge_rules": None,
            "solver_available": True,
            "placement": "planarized",
            "method": ("per-core planarization (greedy U + oil-optimal "
                       "insertion) + Tutte straight-line drawing on H; "
                       "crossings are witness-marked planarization points"),
            "planarization": plan_meta,
        },
    }
    return ("L1", stamp_coordinates_only(v4))


def _match_edge(edges, used, a, b):
    """Map a core edge (a, b) to its index in edges with multiplicity
    (deterministic: lowest unused matching index)."""
    for i, (x, y) in enumerate(edges):
        if (x, y) == (a, b) and used.get(i) is None:
            used[i] = True
            return i
    # fall back to reversed orientation (undirected caliber)
    for i, (x, y) in enumerate(edges):
        if (y, x) == (a, b) and used.get(i) is None:
            used[i] = True
            return i
    raise KeyError(f"core edge {(a, b)} not found in graph edges")


def _kuratowski_lb_safe(graph):
    try:
        from .crossing_exact import undirected_edges, _kuratowski_lb
        edges, _ = undirected_edges(graph)
        lb, _ks = _kuratowski_lb(graph.node_ids(), edges)
        return lb
    except Exception:
        return 0


# ═══════════════ geometry helpers ════════════════════════════════════

def _straight_through(raw):
    """Overshoot construction: at each interior witness Xi the polyline
    overshoots along its incoming direction (Xi + e*u_in) and resumes
    from the back-cut (Xi - e*u_out).  Both neighbouring delivered
    segments then contain Xi in their INTERIOR, so for two edges
    crossing at Xi every outer-segment pair intersects exactly AT Xi
    (strict seg_cross counts it; marker-point matching is exact up to
    rounding).  The connecting middle segment stays within ~2e of Xi so
    any extra hits cluster into ONE visual crossing."""
    if len(raw) <= 2:
        return [[float(x), float(y)] for x, y in raw]
    out = [raw[0]]
    for i in range(1, len(raw) - 1):
        px, py = raw[i - 1]
        qx, qy = raw[i]
        nx_, ny = raw[i + 1]
        dinx, diny = qx - px, qy - py
        lin = math.hypot(dinx, diny)
        dox, doy = nx_ - qx, ny - qy
        lox = math.hypot(dox, doy)
        if lin < 1e-9 or lox < 1e-9:
            out.append(raw[i])
            continue
        e = WITNESS_EPS_PX
        out.append((qx + dinx / lin * e, qy + diny / lin * e))
        out.append((qx - dox / lox * e, qy - doy / lox * e))
    out.append(raw[-1])
    return [[float(x), float(y)] for x, y in out]


def _offset_poly(pts, k):
    """Shift interior points perpendicular to the overall direction by
    k * PARA_OFFSET_PX (parallel duplicate line)."""
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    norm = math.hypot(dx, dy) or 1.0
    nx_, ny = -dy / norm, dx / norm
    off = k * PARA_OFFSET_PX
    out = [pts[0]]
    for p in pts[1:-1]:
        out.append((p[0] + nx_ * off, p[1] + ny * off))
    out.append(pts[-1])
    return [[float(p[0]), float(p[1])] for p in out]


def _selfloop_poly(center, hw, hh, gi):
    cx, cy = center
    x0 = cx + hw + 6 + (gi % 2) * 4
    return [[float(x0), cy - 10], [float(x0 + 18), cy - 10],
            [float(x0 + 18), cy + 10], [float(x0), cy + 10]]


# ═══════════════ verification (delivered coordinates) ════════════════

def _coincide_pairs(plist, thr=1.0, span=8.0):
    """Delivered-polyline parallel-adherence count (<thr px over >span
    px counts as coincident; same caliber as routing's coincidence
    gate).  Local helper: no shared-state coupling with the Router."""
    def _resample(pts, step=4.0):
        out = []
        for s1, s2 in zip(pts[:-1], pts[1:]):
            dx, dy = s2[0] - s1[0], s2[1] - s1[1]
            seg = math.hypot(dx, dy)
            n = max(int(seg // step), 1)
            for t in range(n + 1):
                out.append((s1[0] + dx * t / n, s1[1] + dy * t / n))
        return out

    count = 0
    for i in range(len(plist)):
        for j in range(i + 1, len(plist)):
            ri = _resample(plist[i])
            rj = _resample(plist[j])
            run, best = 0, 0
            for p in ri:
                dmin = min((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                           for q in rj) ** 0.5 if rj else 1e9
                if dmin < thr:
                    run += 1
                    best = max(best, run)
                else:
                    run = 0
            # 5+ consecutive samples (~20px) within 1px = real adherence;
            # a transversal crossing only grazes 1-2 samples
            if best >= 5:
                count += 1
    return count


def _verify(edges, polys, node_xy, half_w, half_h, marker_xy,
            sample_polyline, dist_point_rect, seg_cross, clearance):
    """Contract hard checks on delivered coordinates.  Returns a list of
    human-readable failures (empty = L1 drawing accepted)."""
    failures = []
    dense = {i: list(sample_polyline([tuple(p) for p in polys[i]]))
             for i in polys}

    # 1. geometric recount (metrics caliber: shared-endpoint pairs exempt,
    #    first crossing per pair)
    xings = []          # (i, j, point)
    for i in polys:
        for j in polys:
            if j <= i:
                continue
            a, b = edges[i], edges[j]
            if a[0] in (b[0], b[1]) or a[1] in (b[0], b[1]):
                continue
            hit = False
            for s1 in zip(polys[i][:-1], polys[i][1:]):
                for s2 in zip(polys[j][:-1], polys[j][1:]):
                    if seg_cross(s1[0], s1[1], s2[0], s2[1]):
                        xings.append((i, j, _seg_point(s1[0], s1[1],
                                                       s2[0], s2[1])))
                        hit = True
                        break
                if hit:
                    break

    # 2. full enumeration with hit clustering: hits within
    # WITNESS_CLUSTER_PX of each other are ONE visual crossing (the
    # double-point cut zone bends several segment pairs around the same
    # witness); clusters > 1 per pair fail the H caliber
    pair_full = {}
    fan = 0
    for i in polys:
        for j in polys:
            if j <= i:
                continue
            a, b = edges[i], edges[j]
            adjacent = a[0] in (b[0], b[1]) or a[1] in (b[0], b[1])
            hits = []
            for s1 in zip(polys[i][:-1], polys[i][1:]):
                for s2 in zip(polys[j][:-1], polys[j][1:]):
                    if seg_cross(s1[0], s1[1], s2[0], s2[1]):
                        hits.append(_seg_point(s1[0], s1[1], s2[0], s2[1]))
            clusters = []
            for pt in hits:
                for c in clusters:
                    if ((pt[0] - c[0]) ** 2
                            + (pt[1] - c[1]) ** 2) <= WITNESS_CLUSTER_PX ** 2:
                        break
                else:
                    clusters.append(pt)
            if adjacent:
                fan += len(clusters)
            else:
                pair_full[(i, j)] = len(clusters)
    if fan:
        failures.append(f"fan-pair crossing: {fan} adjacent-pair "
                        "intersection(s) (good-drawing caliber)")
    multi = {k: v for k, v in pair_full.items() if v > 1}
    if multi:
        failures.append(f"pair-multi-crossing: {len(multi)} edge pairs "
                        "cross more than once (H caliber)")

    # 3. three-account shape: geometric == witness count, bijective match
    vids = sorted(marker_xy)
    wpts = [marker_xy[v] for v in vids]
    if len(xings) != len(wpts):
        failures.append(f"account-mismatch: geometric crossings "
                        f"{len(xings)} != witness count {len(wpts)}")
    else:
        remaining = list(range(len(wpts)))
        for (_i, _j, pt) in xings:
            best, bi = None, None
            for ri in remaining:
                d = ((pt[0] - wpts[ri][0]) ** 2
                     + (pt[1] - wpts[ri][1]) ** 2) ** 0.5
                if best is None or d < best:
                    best, bi = d, ri
            if best is None or best > WITNESS_MATCH_PX:
                failures.append(
                    f"witness-unmatched: geometric crossing at "
                    f"({pt[0]:.1f},{pt[1]:.1f}) has no witness within "
                    f"{WITNESS_MATCH_PX}px")
                break
            remaining.remove(bi)

    # 4. box press = 0 (1px margin; 6px endpoint-attachment exemption)
    press = 0
    for i in polys:
        a = edges[i]
        pts = dense[i]
        q0, q1 = pts[0], pts[-1]
        for v in node_xy:
            own = v in (a[0], a[1])
            for (px_, py_) in (pts[1:-1] if own else pts):
                if own and (((px_ - q0[0]) ** 2 + (py_ - q0[1]) ** 2) <= 36.0
                            or ((px_ - q1[0]) ** 2
                                + (py_ - q1[1]) ** 2) <= 36.0):
                    continue
                if dist_point_rect(px_, py_, node_xy[v][0], node_xy[v][1],
                                   half_w[v] + 1, half_h[v] + 1) <= 0:
                    press += 1
                    break
    if press:
        failures.append(f"box-press: {press} edge/card press pair(s)")

    # 5. edge-box clearance >= 16 (non-endpoint boxes)
    worst = None
    for i in polys:
        a = edges[i]
        for v in node_xy:
            if v in (a[0], a[1]):
                continue
            for (px_, py_) in dense[i]:
                d = dist_point_rect(px_, py_, node_xy[v][0], node_xy[v][1],
                                    half_w[v], half_h[v])
                if worst is None or d < worst[0]:
                    worst = (d, i, v)
    diag = {"clearance_worst": worst[0] if worst is not None else None}
    if worst is not None and worst[0] < clearance:
        failures.append(f"clearance: min edge-box clearance "
                        f"{worst[0]:.1f}px < {clearance}px "
                        f"(edge {worst[1]} vs card {worst[2]})")

    # 6. card-card gap >= 16 in one axis (min_card_gap caliber)
    cards = sorted(node_xy)
    bad_gap = 0
    for i in range(len(cards)):
        for j in range(i + 1, len(cards)):
            u, v = cards[i], cards[j]
            gx = (abs(node_xy[u][0] - node_xy[v][0])
                  - half_w[u] - half_w[v])
            gy = (abs(node_xy[u][1] - node_xy[v][1])
                  - half_h[u] - half_h[v])
            if gx < 16.0 and gy < 16.0:
                bad_gap += 1
    if bad_gap:
        failures.append(f"card-gap: {bad_gap} card pair(s) closer than 16px")

    # 7. witnesses transversal: take the MAX angle among a cluster's hits
    # (the overshoot zone contains several segment pairs; the visual
    # crossing angle is the largest one)
    thin = 0
    for (i, j, pt) in xings:
        best_ang = None
        for s1 in zip(polys[i][:-1], polys[i][1:]):
            for s2 in zip(polys[j][:-1], polys[j][1:]):
                if not seg_cross(s1[0], s1[1], s2[0], s2[1]):
                    continue
                p = _seg_point(s1[0], s1[1], s2[0], s2[1])
                if math.hypot(p[0] - pt[0], p[1] - pt[1]) > WITNESS_CLUSTER_PX:
                    continue
                d1, d2 = (s1[1][0] - s1[0][0], s1[1][1] - s1[0][1]), \
                         (s2[1][0] - s2[0][0], s2[1][1] - s2[0][1])
                l1 = math.hypot(*d1) or 1.0
                l2 = math.hypot(*d2) or 1.0
                cosang = abs((d1[0] * d2[0] + d1[1] * d2[1]) / (l1 * l2))
                ang = math.degrees(math.acos(max(0.0, min(1.0, cosang))))
                ang = min(ang, 180.0 - ang)
                best_ang = ang if best_ang is None else max(best_ang, ang)
        if best_ang is None or best_ang < MIN_TRANSVERSE_DEG:
            thin += 1
    if thin:
        failures.append(f"transversality: {thin} witness crossing(s) "
                        f"thinner than {MIN_TRANSVERSE_DEG} deg")

    # 8. witnesses clear of cards (marker not under a card footprint)
    buried = 0
    for v in vids:
        for c in node_xy:
            if dist_point_rect(marker_xy[v][0], marker_xy[v][1],
                               node_xy[c][0], node_xy[c][1],
                               half_w[c] + 2, half_h[c] + 2) <= 0:
                buried += 1
                break
    if buried:
        failures.append(f"marker-buried: {buried} witness marker(s) "
                        "inside a card footprint")

    # 9. coincidence guard (parallel <1px over >8px would fail the
    # certificate's line-coincidence gate); pairs with a witnessed
    # crossing are exempt — a thin crossing approaches within 1px over a
    # long stretch by geometry, that is the crossing, not adherence
    wit_pairs = {(i, j) for (i, j, _pt) in xings}
    plist = [polys[i] for i in sorted(polys)]
    idx_list = sorted(polys)
    coincide = 0
    for a in range(len(plist)):
        for b in range(a + 1, len(plist)):
            if (idx_list[a], idx_list[b]) in wit_pairs:
                continue
            if _coincide_pairs([plist[a], plist[b]]):
                coincide += 1
    if coincide:
        failures.append(f"line-coincidence: {coincide} coincident "
                        "polyline pair(s)")
    return failures, diag


def _even_scale(p, k):
    """Uniform integer scale of an even-grid point (deterministic)."""
    x, y = round(p[0] * k), round(p[1] * k)
    return [x + x % 2, y + y % 2]


def _seg_dir_at(pts, pt):
    """Unit direction of the segment of polyline pts containing pt."""
    best, bestd = None, None
    for s1, s2 in zip(pts[:-1], pts[1:]):
        dx, dy = s2[0] - s1[0], s2[1] - s1[1]
        seglen = (dx * dx + dy * dy) ** 0.5
        if seglen < 1e-12:
            continue
        t = ((pt[0] - s1[0]) * dx + (pt[1] - s1[1]) * dy) / (seglen ** 2)
        if 0.0 <= t <= 1.0:
            proj = (s1[0] + t * dx, s1[1] + t * dy)
            d = ((proj[0] - pt[0]) ** 2 + (proj[1] - pt[1]) ** 2) ** 0.5
            if bestd is None or d < bestd:
                bestd, best = d, (dx / seglen, dy / seglen)
    return best
