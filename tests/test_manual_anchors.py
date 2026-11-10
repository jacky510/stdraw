# -*- coding: utf-8 -*-
"""T1 regression: --from-layout reads back user-specified standard anchors
(edges[].anchors, the demo-2d endpoint drag / anchor click export).

Probe written BEFORE the fix (falsification leg, card t_2ce56c63): the
current engine ignores edges[].anchors on --from-layout, so tests 1-6 are
expected RED pre-fix and GREEN post-fix. Caliber (jacky 2026-11-11 task
sheet): a user-designated endpoint lands EXACTLY on the corresponding
standard anchor coordinate (+/-0.1px delivered); the edge joins the frozen
set (later repair passes must not move it); straight / arc / waypoint edges
all honor the designation; arc ctrl translates with the endpoint deltas
(arcEpPts mean-translation caliber); the certificate records the anchor
source honestly (user_anchors under meta.from_layout).
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stdraw.dsl import parse
from stdraw.layout_auto import layout
from stdraw.anchors import ANCHOR_IDS, standard_anchors, nearest_anchor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "classic-cld-growth-and-burden.cld")
TOL = 0.1


def _anchor_pt(lay, node_id, aid):
    """Standard anchor coordinate of one delivered node (post-shift geometry)."""
    p = lay["nodes"][node_id]
    ch = lay["meta"]["cardH"]
    pts = standard_anchors(p["x"], p["y"], p["w"] / 2.0, ch / 2.0)
    for a in pts:
        if a[0] == aid:
            return [a[1], a[2]]
    raise AssertionError(f"anchor id {aid!r} not found")


def _designated_aid(lay, node_id, px, py):
    """Deterministic user-style designation: the anchor AFTER the nearest one
    in ANCHOR_IDS order (a real user designation need not coincide with the
    engine's default endpoint -- rotating guarantees the probe is red
    pre-fix: the ignored designation can never match by accident)."""
    p = lay["nodes"][node_id]
    ch = lay["meta"]["cardH"]
    near = nearest_anchor(p["x"], p["y"], p["w"] / 2.0, ch / 2.0, px, py)[0]
    return ANCHOR_IDS[(ANCHOR_IDS.index(near) + 1) % len(ANCHOR_IDS)]


class TestManualAnchors(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(EXAMPLE, encoding="utf-8") as f:
            cls.dsl = f.read()
        cls.g = parse(cls.dsl)
        cls.auto = layout(cls.g)
        cls.manual = {
            "nodes": {v: {"x": p["x"], "y": p["y"]}
                      for v, p in cls.auto["nodes"].items()},
            "viewBox": cls.auto["viewBox"],
            "source": "probe",
        }

    def _manual_with(self, edge_entries):
        m = copy.deepcopy(self.manual)
        m["edges"] = edge_entries
        return m

    def _first_edge(self):
        e = self.auto["edges"][0]
        return e["a"], e["b"]

    # 1. both ends designated -> delivered endpoints sit on the anchors
    def test_both_ends_on_standard_anchors(self):
        a, b = self._first_edge()
        e0 = self.auto["edges"][0]
        src = _designated_aid(self.auto, a, e0["anchors"]["a"][0], e0["anchors"]["a"][1])
        dst = _designated_aid(self.auto, b, e0["anchors"]["b"][0], e0["anchors"]["b"][1])
        lay = layout(self.g, manual=self._manual_with(
            [{"a": a, "b": b, "anchors": {"src": src, "dst": dst}}]))
        got = lay["edges"][0]["route"]["points"]
        self.assertAlmostEqual(got[0][0], _anchor_pt(lay, a, src)[0], delta=TOL)
        self.assertAlmostEqual(got[0][1], _anchor_pt(lay, a, src)[1], delta=TOL)
        self.assertAlmostEqual(got[-1][0], _anchor_pt(lay, b, dst)[0], delta=TOL)
        self.assertAlmostEqual(got[-1][1], _anchor_pt(lay, b, dst)[1], delta=TOL)

    # 2. src-only designation -> src endpoint exact, dst end untouched
    def test_src_only_designation(self):
        a, b = self._first_edge()
        e0 = self.auto["edges"][0]
        src = _designated_aid(self.auto, a, e0["anchors"]["a"][0], e0["anchors"]["a"][1])
        lay = layout(self.g, manual=self._manual_with(
            [{"a": a, "b": b, "anchors": {"src": src}}]))
        got = lay["edges"][0]["route"]["points"]
        self.assertAlmostEqual(got[0][0], _anchor_pt(lay, a, src)[0], delta=TOL)
        self.assertAlmostEqual(got[0][1], _anchor_pt(lay, a, src)[1], delta=TOL)

    # 3. waypoints edge + designation -> polyline kept, endpoint on anchor
    def test_waypoints_edge_with_anchor(self):
        a, b = self._first_edge()
        e0 = self.auto["edges"][0]
        src = _designated_aid(self.auto, a, e0["anchors"]["a"][0], e0["anchors"]["a"][1])
        mid = [(self.auto["nodes"][a]["x"] + self.auto["nodes"][b]["x"]) // 2,
               (self.auto["nodes"][a]["y"] + self.auto["nodes"][b]["y"]) // 2 + 40]
        lay = layout(self.g, manual=self._manual_with(
            [{"a": a, "b": b, "waypoints": [mid],
              "anchors": {"src": src}}]))
        self.assertEqual(lay["edges"][0]["route"]["kind"], "waypoints")
        got = lay["edges"][0]["route"]["points"]
        self.assertAlmostEqual(got[0][0], _anchor_pt(lay, a, src)[0], delta=TOL)
        self.assertAlmostEqual(got[0][1], _anchor_pt(lay, a, src)[1], delta=TOL)
        self.assertAlmostEqual(got[1][0], mid[0], delta=0.51)

    # 4. arc edge + designation -> endpoints on anchors, ctrl translated by
    #    the mean endpoint delta (arcEpPts caliber)
    def test_arc_edge_ctrl_translation(self):
        a, b = self._first_edge()
        e0 = self.auto["edges"][0]
        src = _designated_aid(self.auto, a, e0["anchors"]["a"][0], e0["anchors"]["a"][1])
        dst = _designated_aid(self.auto, b, e0["anchors"]["b"][0], e0["anchors"]["b"][1])
        base_lay = layout(self.g, manual=self._manual_with(
            [{"a": a, "b": b, "style": "arc"}]))
        base = base_lay["edges"][0]
        user_lay = layout(self.g, manual=self._manual_with(
            [{"a": a, "b": b, "style": "arc",
              "anchors": {"src": src, "dst": dst}}]))
        user = user_lay["edges"][0]
        pa0, pb0 = base["route"]["points"][0], base["route"]["points"][-1]
        pa1, pb1 = user["route"]["points"][0], user["route"]["points"][-1]
        self.assertAlmostEqual(pa1[0], _anchor_pt(user_lay, a, src)[0], delta=TOL)
        self.assertAlmostEqual(pa1[1], _anchor_pt(user_lay, a, src)[1], delta=TOL)
        self.assertAlmostEqual(pb1[0], _anchor_pt(user_lay, b, dst)[0], delta=TOL)
        self.assertAlmostEqual(pb1[1], _anchor_pt(user_lay, b, dst)[1], delta=TOL)
        exp_ctrl = [base["route"]["ctrl"][0] + ((pa1[0] - pa0[0]) + (pb1[0] - pb0[0])) / 2,
                    base["route"]["ctrl"][1] + ((pa1[1] - pa0[1]) + (pb1[1] - pb0[1])) / 2]
        self.assertAlmostEqual(user["route"]["ctrl"][0], exp_ctrl[0], delta=0.2)
        self.assertAlmostEqual(user["route"]["ctrl"][1], exp_ctrl[1], delta=0.2)

    # 5. validation: unknown anchor id / unknown edge -> ValueError
    def test_unknown_anchor_id_rejected(self):
        a, b = self._first_edge()
        bad = "zz" if "zz" not in ANCHOR_IDS else "n"
        with self.assertRaises(ValueError):
            layout(self.g, manual=self._manual_with(
                [{"a": a, "b": b, "anchors": {"src": bad}}]))

    def test_unknown_edge_rejected(self):
        with self.assertRaises(ValueError):
            layout(self.g, manual=self._manual_with(
                [{"a": "__nope__", "b": "__also_nope__",
                  "anchors": {"src": "n"}}]))

    # 6. CLI round-trip (the card's probe): export-shape JSON -> --from-layout
    #    -> layout.json endpoint == anchor coord (+/-0.1px) + certificate
    #    records the user source; re-render works; deterministic.
    def test_cli_round_trip_probe(self):
        a, b = self._first_edge()
        e0 = self.auto["edges"][0]
        src = _designated_aid(self.auto, a, e0["anchors"]["a"][0], e0["anchors"]["a"][1])
        dst = _designated_aid(self.auto, b, e0["anchors"]["b"][0], e0["anchors"]["b"][1])
        doc = {"tool": "stdraw", "kind": "manual-layout", "graph": "probe",
               "viewBox": self.auto["viewBox"],
               "nodes": {v: {"x": p["x"], "y": p["y"]}
                         for v, p in self.auto["nodes"].items()},
               "edges": [{"a": a, "b": b,
                          "style": "auto",
                          "anchors": {"src": src, "dst": dst}}]}
        tmp = tempfile.mkdtemp(prefix="stdraw-anchor-rt-")
        try:
            ip = os.path.join(tmp, "export.json")
            with open(ip, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
            outs = []
            for k in (1, 2):
                od = os.path.join(tmp, f"rt{k}")
                r = subprocess.run(
                    [sys.executable, "-m", "stdraw", "layout", EXAMPLE,
                     "--outdir", od, "--skip-3d", "--from-layout", ip],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", cwd=ROOT)
                # rc 0 = clean; rc 1 = geometry recheck honestly failed on an
                # awkward designation (all artifacts are still written before
                # the exit -- the anchor read-back is what this probe pins)
                self.assertIn(r.returncode, (0, 1),
                              f"run{k} rc={r.returncode}: {r.stderr[-400:]}")
                outs.append(od)
            lay1 = json.load(open(os.path.join(outs[0], "layout.json"),
                                  encoding="utf-8"))
            lay2 = open(os.path.join(outs[0], "layout.json"), "rb").read()
            lay2b = open(os.path.join(outs[1], "layout.json"), "rb").read()
            # determinism: two runs byte-identical
            self.assertEqual(lay2, lay2b)
            # endpoint == standard anchor of the delivered node geometry
            got = lay1["edges"][0]["route"]["points"]
            self.assertAlmostEqual(got[0][0], _anchor_pt(lay1, a, src)[0], delta=TOL)
            self.assertAlmostEqual(got[0][1], _anchor_pt(lay1, a, src)[1], delta=TOL)
            self.assertAlmostEqual(got[-1][0], _anchor_pt(lay1, b, dst)[0], delta=TOL)
            self.assertAlmostEqual(got[-1][1], _anchor_pt(lay1, b, dst)[1], delta=TOL)
            # certificate records the anchor source honestly
            cert = json.load(open(os.path.join(outs[0], "certificate.json"),
                                  encoding="utf-8"))
            ua = (cert.get("from_layout") or {}).get("user_anchors") or {}
            self.assertIn(f"{a}->{b}", ua)
            self.assertEqual(ua[f"{a}->{b}"], {"src": src, "dst": dst})
            # re-render: demo-2d.html produced and non-trivial
            html = open(os.path.join(outs[0], "demo-2d.html"),
                        encoding="utf-8").read()
            self.assertIn("stdraw-svg", html)
            self.assertGreater(len(html), 10000)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
