# -*- coding: utf-8 -*-
"""Planarized L1 output-surface invariants (split-safety net).

The L1 assembly is a five-stage pipeline (exactness aggregation / core
bands / attachment trees / normalization / output assembly).  The
certificate test in ``test_planarized_layout`` pins the end-to-end grade
of one fixture; this module pins the delivered *structure* of every L1
target the corpus offers, so a refactor of any single stage that changes
geometry, accounting or the payload shape is caught without a byte-pinned
baseline (the exact solver is platform dependent; structure is not).

The build runs the production caliber: the L1 assembly is hash-seed
sensitive (networkx planar deposition), so it is computed in a pinned
worker process (PYTHONHASHSEED=0) exactly like
``planarized_layout._l1_deterministic`` does in production.

Assertion surface per fixture:
  * admission / exactness accounting agree with the witness payload
  * every witness point sits on BOTH named member routes
  * every non-selfloop endpoint lands on its card border
  * attachment-tree edges (non-core) are straight two-point escapes
  * deg0 cards are parked below the drawing (stage 4 parking lane)
  * viewBox is 8-aligned and contains every box and route point
  * cards never overlap (clearance kept)
  * the auto-schema meta block keeps the planarized caliber
"""
import json
import math
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "benchmarks", "corpus", "random")
FIXTURES = ("random-n10-i09", "random-n10-i10", "random-n10-i16",
            "random-n10-i19")

WORKER = (
    "import sys, os, json;"
    "sys.path.insert(0, os.environ['STDRAW_PKG_PARENT']);"
    "from stdraw.model import Graph;"
    "from stdraw.layout_auto import AutoConfig;"
    "from stdraw.crossing_exact import safe_reduce;"
    "from stdraw.planarized_layout import _planarized_l1;"
    "d = json.loads(sys.stdin.read());"
    "graph = Graph.from_dict(d['graph']);"
    "cfg = AutoConfig();"
    "[setattr(cfg, k, v) for k, v in d['cfg'].items()];"
    "cores, _red = safe_reduce(graph);"
    "mode, payload = _planarized_l1(graph, cfg, d['linestyle'], cores);"
    "print(json.dumps({'mode': mode, 'payload': payload,"
    "'cores': [[list(cn), [list(e) for e in ce]] for cn, ce in cores]}))"
)


def _build_pinned(name):
    """Production-caliber L1 build: pinned worker (PYTHONHASHSEED=0)."""
    from stdraw.dsl import parse
    with open(os.path.join(CORPUS, name + ".cld"), encoding="utf-8") as f:
        graph = parse(f.read())
    payload = {"graph": graph.to_dict(),
               "cfg": {"fs_title": 12.5, "fs_value": 14},
               "linestyle": "straight"}
    env = {**os.environ, "STDRAW_L1_PINNED": "1", "PYTHONHASHSEED": "0",
           "STDRAW_PKG_PARENT": ROOT}
    r = subprocess.run([sys.executable, "-c", WORKER],
                       input=json.dumps(payload), capture_output=True,
                       text=True, encoding="utf-8", env=env)
    if r.returncode != 0 or not r.stdout.strip():
        raise AssertionError("pinned L1 worker failed (rc=%s): %s"
                             % (r.returncode, r.stderr[-600:]))
    out = json.loads(r.stdout.strip())
    return graph, out["cores"], out["mode"], out["payload"]


def _dist_pt_seg(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    vx, vy = bx - ax, by - ay
    l2 = vx * vx + vy * vy
    if l2 < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / l2))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def _dist_poly(p, pts):
    return min(_dist_pt_seg(p, pts[i], pts[i + 1])
               for i in range(len(pts) - 1))


class _L1Case(unittest.TestCase):
    """Shared L1 build (pinned caliber) + surface helpers."""

    built = {}

    @classmethod
    def setUpClass(cls):
        missing = [n for n in FIXTURES
                   if not os.path.exists(os.path.join(CORPUS, n + ".cld"))]
        if missing:
            raise unittest.SkipTest("random corpus not present: %s"
                                    % ", ".join(missing))

    def _build(self, name):
        if name not in type(self).built:
            type(self).built[name] = _build_pinned(name)
        return type(self).built[name]

    @staticmethod
    def _routes_by_pair(v4):
        routes = {}
        for eo in v4["edges"]:
            routes.setdefault(tuple(sorted((eo["a"], eo["b"]))),
                              []).append(eo["route"]["points"])
        return routes

    def _attachment_edges(self, name):
        _g, cores, _m, v4 = self._build(name)
        core_edges = set()
        for _cn, cedges in cores:
            for (a, b) in cedges:
                core_edges.add(tuple(sorted((a, b))))
        return [(eo["a"], eo["b"]) for eo in v4["edges"]
                if eo["a"] != eo["b"]
                and tuple(sorted((eo["a"], eo["b"]))) not in core_edges]


class TestL1AdmissionAccounting(_L1Case):
    def test_every_fixture_reaches_l1(self):
        for name in FIXTURES:
            with self.subTest(fixture=name):
                _g, cores, mode, _payload = self._build(name)
                self.assertTrue(cores)
                self.assertEqual(mode, "L1",
                                 "fixture %s left the L1 ladder" % name)

    def test_exactness_agrees_with_witnesses(self):
        for name in FIXTURES:
            with self.subTest(fixture=name):
                _g, _c, _m, v4 = self._build(name)
                pl = v4["meta"]["planarization"]
                ex = pl["exactness"]
                self.assertEqual(ex["crossing_number"], pl["ub"])
                self.assertEqual(ex["gap"], ex["crossing_number"] - ex["lb"])
                self.assertGreaterEqual(ex["lb"], 0)
                self.assertIsInstance(ex["proven_optimal"], bool)
                self.assertIn(ex["coverage"], ("full", "partial", "trivial"))
                self.assertEqual(pl["witness_count"], len(pl["markers"]))
                self.assertEqual(pl["ub"], len(pl["markers"]))
                self.assertEqual(pl["gap"], pl["ub"] - pl["lb"])
                self.assertEqual(v4["meta"]["router_cross_pairs"], pl["ub"])

    def test_every_witness_sits_on_both_member_routes(self):
        for name in FIXTURES:
            with self.subTest(fixture=name):
                _g, _c, _m, v4 = self._build(name)
                routes = self._routes_by_pair(v4)
                for marker in v4["meta"]["planarization"]["markers"]:
                    self.assertEqual(len(marker["edges"]), 2)
                    for (a, b) in marker["edges"]:
                        pair = tuple(sorted((a, b)))
                        self.assertIn(pair, routes)
                        best = min(_dist_poly(marker["point"], pts)
                                   for pts in routes[pair])
                        self.assertLessEqual(
                            best, 0.2,
                            "witness %s off its member route %s by %.3f"
                            % (marker["witness_id"], pair, best))


class TestL1GeometrySurface(_L1Case):
    def test_card_and_route_extent(self):
        for name in FIXTURES:
            with self.subTest(fixture=name):
                _g, _c, _m, v4 = self._build(name)
                W, H = v4["viewBox"][2], v4["viewBox"][3]
                self.assertEqual((W % 8, H % 8), (0, 0))
                card_h = v4["meta"]["cardH"]
                for _nid, nd in v4["nodes"].items():
                    self.assertGreater(nd["x"] - nd["w"] / 2.0, 0.0)
                    self.assertGreater(nd["y"] - card_h / 2.0, 0.0)
                    self.assertLess(nd["x"] + nd["w"] / 2.0, W)
                    self.assertLess(nd["y"] + card_h / 2.0, H)
                for eo in v4["edges"]:
                    for p in eo["route"]["points"]:
                        self.assertGreaterEqual(p[0], 0.0)
                        self.assertGreaterEqual(p[1], 0.0)
                        self.assertLessEqual(p[0], W)
                        self.assertLessEqual(p[1], H)

    def test_cards_keep_the_clearance(self):
        for name in FIXTURES:
            with self.subTest(fixture=name):
                _g, _c, _m, v4 = self._build(name)
                card_h = v4["meta"]["cardH"]
                ids = list(v4["nodes"])
                for i, u in enumerate(ids):
                    for v in ids[i + 1:]:
                        a, b = v4["nodes"][u], v4["nodes"][v]
                        gap_x = abs(a["x"] - b["x"]) - (a["w"] + b["w"]) / 2.0
                        gap_y = abs(a["y"] - b["y"]) - card_h
                        self.assertGreaterEqual(
                            max(gap_x, gap_y), 16.0,
                            "cards %s/%s closer than clearance" % (u, v))

    def test_endpoints_land_on_card_borders(self):
        for name in FIXTURES:
            with self.subTest(fixture=name):
                _g, _c, _m, v4 = self._build(name)
                card_h = v4["meta"]["cardH"]
                for eo in v4["edges"]:
                    if eo["a"] == eo["b"]:
                        continue
                    pts = eo["route"]["points"]
                    for nid, p in ((eo["a"], pts[0]), (eo["b"], pts[-1])):
                        nd = v4["nodes"][nid]
                        off_x = abs(abs(p[0] - nd["x"]) - nd["w"] / 2.0)
                        off_y = abs(abs(p[1] - nd["y"]) - card_h / 2.0)
                        self.assertLessEqual(
                            min(off_x, off_y), 0.6,
                            "endpoint %s of %s->%s off the border"
                            % (p, eo["a"], eo["b"]))


class TestL1StageSurface(_L1Case):
    def test_attachment_edges_are_straight_escapes(self):
        """Stage 3 (attachment trees): every non-core edge is delivered as
        the two-point border escape of its placed tree card."""
        exercised = []
        for name in FIXTURES:
            with self.subTest(fixture=name):
                _g, _c, _m, v4 = self._build(name)
                attach = set(self._attachment_edges(name))
                if attach:
                    exercised.append(name)
                for eo in v4["edges"]:
                    if (eo["a"], eo["b"]) not in attach:
                        continue
                    self.assertEqual(len(eo["route"]["points"]), 2,
                                     "attachment edge %s->%s is not a straight "
                                     "escape" % (eo["a"], eo["b"]))
                    self.assertIn(eo["a"], v4["nodes"])
                    self.assertIn(eo["b"], v4["nodes"])
        self.assertTrue(exercised, "no fixture exercises attachment trees")

    def test_deg0_cards_park_below_the_drawing(self):
        """Stage 4 (parking lane): isolated cards sit under the plot."""
        parked_any = False
        for name in FIXTURES:
            with self.subTest(fixture=name):
                _g, _c, _m, v4 = self._build(name)
                deg0 = [v for v in v4["meta"]["deg0"] if v in v4["nodes"]]
                if not deg0:
                    continue
                parked_any = True
                core_ys = [nd["y"] for nid, nd in v4["nodes"].items()
                           if nid not in deg0]
                self.assertTrue(core_ys)
                for v in deg0:
                    self.assertGreater(v4["nodes"][v]["y"], max(core_ys),
                                       "deg0 card %s not parked below" % v)
        self.assertTrue(parked_any, "no fixture exercises the parking lane")

    def test_output_assembly_meta_block(self):
        for name in FIXTURES:
            with self.subTest(fixture=name):
                g, _c, _m, v4 = self._build(name)
                meta = v4["meta"]
                self.assertEqual(v4["bars"], {})
                self.assertEqual(meta["rows"], 0)
                self.assertEqual(meta["rowY"], [])
                self.assertIsNone(meta["pitch"])
                self.assertEqual(meta["clearance"], 16)
                self.assertIsNone(meta["anchor_snap_deferred"])
                self.assertIsNone(meta["edge_rules"])
                self.assertTrue(meta["solver_available"])
                self.assertEqual(meta["position_engine"], "planarized")
                self.assertEqual(meta["placement"], "planarized")
                self.assertEqual(meta["recipe"], "auto-v2")
                self.assertEqual(meta["line_style"], "straight")
                self.assertEqual(meta["fs"], [12.5, 14])
                pl = meta["planarization"]
                self.assertEqual(pl["mode"], "L1")
                self.assertEqual(pl["budget"],
                                 {"insert_steps": 2000, "h_vertices": 600})
                self.assertEqual(pl["marker_style"]["size_px"], 9)
                self.assertEqual(set(pl["marker_style"]["color_by_theme"]),
                                 {"light", "dark"})
                # one edges_out entry per graph edge, order preserved
                self.assertEqual(len(v4["edges"]), len(g.edges))
                for eo, e in zip(v4["edges"], g.edges):
                    self.assertEqual((eo["a"], eo["b"]), (e.a, e.b))
                    self.assertEqual(eo["route"]["kind"], "polyline")
                    self.assertEqual(eo["polarity"],
                                     getattr(e, "polarity", "+"))
                    if getattr(e, "delay", False):
                        self.assertTrue(eo["delay"])
                    else:
                        self.assertNotIn("delay", eo)


if __name__ == "__main__":
    unittest.main()
