# Exact-memo eval-cache regression: Router with an EvalCache must produce
# bitwise-identical routes/scores to the legacy uncached path, across
# candidate worlds (node shifts / adjacent swaps) and memo-hit repeats.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stdraw.routing import Router, EvalCache


def _world(pos_overrides):
    nodes = {
        "a": (120, 100, 120, 44),
        "b": (320, 100, 130, 44),
        "c": (200, 180, 110, 44),
        "d": (400, 180, 120, 44),
        "e": (240, 260, 140, 44),
        "f": (480, 100, 100, 44),
    }
    for v, (x, yy) in pos_overrides.items():
        cx, cy, w, h = nodes[v]
        nodes[v] = (x, yy, w, h)
    return nodes


EDGES = [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("c", "e"),
         ("d", "e"), ("b", "f"), ("d", "f"), ("a", "e"), ("e", "f"),
         ("b", "e"), ("c", "f")]


def _routes_equal(ra, rb):
    assert ra.keys() == rb.keys()
    for i in ra:
        ia, ib = ra[i], rb[i]
        assert set(ia.keys()) == set(ib.keys()), (i, sorted(ia), sorted(ib))
        for k in ia:
            assert ia[k] == ib[k], (i, k, ia[k], ib[k])


def test_router_eval_cache_bitwise_identical():
    ec = EvalCache()
    base = {}
    worlds = [base]
    # single-node horizontal shifts (the polish neighborhood)
    for v in ("b", "c", "e"):
        for dx in (24, -24, 48, -48, 72, -72):
            cx, cy, w, h = _world({})[v]
            worlds.append({v: (cx + dx, cy)})
    # adjacent in-row swaps
    worlds.append({"b": (200, 100), "a": (320, 100)})
    worlds.append({"c": (400, 180), "d": (200, 180)})
    for wi, ov in enumerate(worlds):
        nodes = _world(ov)
        r_legacy = Router(dict(nodes), EDGES, 16, 80)
        r_cached = Router(dict(nodes), EDGES, 16, 80, eval_cache=ec)
        out_l = r_legacy.route_all()
        out_c = r_cached.route_all()
        _routes_equal(out_l, out_c)
        assert r_legacy.final_crossing_pairs(out_l) == \
            r_cached.final_crossing_pairs(out_c)
        # memo-hit path: same world again through the SAME cache
        r_again = Router(dict(nodes), EDGES, 16, 80, eval_cache=ec)
        _routes_equal(out_l, r_again.route_all())


def test_evaluate_cached_matches_base_per_candidate():
    ec = EvalCache()
    nodes = _world({})
    r_legacy = Router(dict(nodes), EDGES, 16, 80)
    r_cached = Router(dict(nodes), EDGES, 16, 80, eval_cache=ec)
    base_segs = {}
    for i in range(len(EDGES)):
        a, b = EDGES[i]
        cands_l = r_legacy._candidates(a, b, i)
        cands_c = r_cached._candidates(a, b, i)
        assert len(cands_l) == len(cands_c)
        for c1, c2 in zip(cands_l, cands_c):
            s1, i1 = r_legacy._evaluate(c1, a, b, base_segs, None)
            s2, i2 = r_cached._evaluate(c2, a, b, base_segs, None)
            assert s1 == s2 and i1 == i2, (a, b, c1[0], s1, s2)
            # memo-hit repeat must be stable
            s3, i3 = r_cached._evaluate(c2, a, b, base_segs, None)
            assert s2 == s3 and i2 == i3


def test_router_without_cache_is_untouched_legacy_path():
    # no eval_cache argument -> legacy behavior flag off
    r = Router(_world({}), EDGES, 16, 80)
    assert r._ecache is None
    out = r.route_all()
    assert out and all("points" in info for info in out.values())
