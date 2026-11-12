# -*- coding: utf-8 -*-
"""T1 regression: --from-layout reads back user-specified standard anchors
(edges[].anchors, the demo-2d endpoint drag / anchor click export).

Caliber (2026-11-11 task sheet, amended by the 2026-11-12 manual hard-gate
fallback): a user-designated endpoint lands EXACTLY on the corresponding
standard anchor coordinate (+/-0.1px delivered) -- UNLESS the injected route
breaches a hard gate (box press / clearance / mutual-pair separation), in
which case the edge falls back to the engine's own routing and the fallback
is recorded honestly (meta.from_layout.manual_fallback: edge, reason, and
the user designation preserved verbatim).  Gate-clean designations keep the
original verbatim-replay contract (endpoints on anchors, ctrl translated by
the mean endpoint delta, frozen from repair passes).

Probe history: written BEFORE the T1 fix with deliberately ROTATED
designations (the anchor AFTER the nearest one) so tests were red pre-fix;
post-fix the rotated designation on this graph's first edge produces a
self-pressing route, which since the 2026-11-12 amendment falls back -- the
tests therefore pin both sides: the rotated designation exercises the
fallback contract, a nearest-anchor designation exercises the verbatim
landing contract.
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

    def _fallback_edges(self, lay):
        fm = lay["meta"].get("from_layout") or {}
        return {e["edge"]: e for e in fm.get("manual_fallback") or []}

    def _benign(self):
        """Engine delivery for the same node placement without user edges."""
        return layout(self.g, manual=self._manual_with([]))

    # 1. both ends designated (rotated = gate-breaching on this graph)
    #    -> hard-gate fallback: engine route restored, designation recorded
    def test_both_ends_on_standard_anchors(self):
        a, b = self._first_edge()
        e0 = self.auto["edges"][0]
        src = _designated_aid(self.auto, a, e0["anchors"]["a"][0], e0["anchors"]["a"][1])
        dst = _designated_aid(self.auto, b, e0["anchors"]["b"][0], e0["anchors"]["b"][1])
        lay = layout(self.g, manual=self._manual_with(
            [{"a": a, "b": b, "anchors": {"src": src, "dst": dst}}]))
        fb = self._fallback_edges(lay)
        self.assertIn(f"{a}->{b}", fb, f"breaching designation must fall back: {fb}")
        self.assertEqual(fb[f"{a}->{b}"]["user_anchors"], {"src": src, "dst": dst})
        self.assertIn("reason", fb[f"{a}->{b}"])
        benign = self._benign()["edges"][0]["route"]
        got = lay["edges"][0]["route"]
        self.assertEqual(got["kind"], benign["kind"])
        self.assertEqual([list(p) for p in got["points"]],
                         [list(p) for p in benign["points"]])

    # 1b. gate-clean designation (nearest anchor) -> lands exactly on it
    def test_clean_designation_lands_on_anchor(self):
        a, b = self._first_edge()
        e0 = self.auto["edges"][0]
        p = self.auto["nodes"][a]
        ch = self.auto["meta"]["cardH"]
        src = nearest_anchor(p["x"], p["y"], p["w"] / 2.0, ch / 2.0,
                             e0["anchors"]["a"][0], e0["anchors"]["a"][1])[0]
        lay = layout(self.g, manual=self._manual_with(
            [{"a": a, "b": b, "anchors": {"src": src}}]))
        self.assertNotIn(f"{a}->{b}", self._fallback_edges(lay))
        got = lay["edges"][0]["route"]["points"]
        self.assertAlmostEqual(got[0][0], _anchor_pt(lay, a, src)[0], delta=TOL)
        self.assertAlmostEqual(got[0][1], _anchor_pt(lay, a, src)[1], delta=TOL)

    # 2. src-only designation (rotated = gate-breaching on this graph)
    #    -> hard-gate fallback; clean designation covered by 1b
    def test_src_only_designation(self):
        a, b = self._first_edge()
        e0 = self.auto["edges"][0]
        src = _designated_aid(self.auto, a, e0["anchors"]["a"][0], e0["anchors"]["a"][1])
        lay = layout(self.g, manual=self._manual_with(
            [{"a": a, "b": b, "anchors": {"src": src}}]))
        fb = self._fallback_edges(lay)
        self.assertIn(f"{a}->{b}", fb, f"breaching designation must fall back: {fb}")
        self.assertEqual(fb[f"{a}->{b}"]["user_anchors"], {"src": src})
        benign = self._benign()["edges"][0]["route"]
        got = lay["edges"][0]["route"]
        self.assertEqual([list(p) for p in got["points"]],
                         [list(p) for p in benign["points"]])

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

    # 4. arc edge + gate-clean designation (nearest anchors) -> endpoints on
    #    anchors, ctrl translated by the mean endpoint delta (arcEpPts
    #    caliber); the rotated designation breaches a hard gate on this graph
    #    and falls back (4b)
    def test_arc_edge_ctrl_translation(self):
        a, b = self._first_edge()
        e0 = self.auto["edges"][0]
        ch = self.auto["meta"]["cardH"]
        pa = e0["anchors"]["a"]
        pb = e0["anchors"]["b"]
        na = self.auto["nodes"][a]
        nb = self.auto["nodes"][b]
        src = nearest_anchor(na["x"], na["y"], na["w"] / 2.0, ch / 2.0,
                             pa[0], pa[1])[0]
        dst = nearest_anchor(nb["x"], nb["y"], nb["w"] / 2.0, ch / 2.0,
                             pb[0], pb[1])[0]
        base_lay = layout(self.g, manual=self._manual_with(
            [{"a": a, "b": b, "style": "arc"}]))
        base = base_lay["edges"][0]
        user_lay = layout(self.g, manual=self._manual_with(
            [{"a": a, "b": b, "style": "arc",
              "anchors": {"src": src, "dst": dst}}]))
        self.assertNotIn(f"{a}->{b}", self._fallback_edges(user_lay),
                         "nearest-anchor arc designation must be gate-clean")
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

    # 4b. arc edge + rotated (gate-breaching) designation -> fallback with
    #     the user style + ctrl preserved in the record
    def test_arc_edge_breaching_designation_falls_back(self):
        a, b = self._first_edge()
        e0 = self.auto["edges"][0]
        src = _designated_aid(self.auto, a, e0["anchors"]["a"][0], e0["anchors"]["a"][1])
        dst = _designated_aid(self.auto, b, e0["anchors"]["b"][0], e0["anchors"]["b"][1])
        user_lay = layout(self.g, manual=self._manual_with(
            [{"a": a, "b": b, "style": "arc", "ctrl": [123.4, 5.6],
              "anchors": {"src": src, "dst": dst}}]))
        fb = self._fallback_edges(user_lay)
        self.assertIn(f"{a}->{b}", fb)
        self.assertEqual(fb[f"{a}->{b}"]["user_style"], "arc")
        self.assertEqual(fb[f"{a}->{b}"]["user_ctrl"], [123.4, 5.6])
        # the engine's own delivery (no user edges) is what gets served
        benign = self._benign()["edges"][0]["route"]
        got = user_lay["edges"][0]["route"]
        self.assertEqual([list(p) for p in got["points"]],
                         [list(p) for p in benign["points"]])

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
    #    -> rotated (gate-breaching) designation falls back with the user
    #    designation recorded honestly; re-render works; deterministic.
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
                self.assertIn(r.returncode, (0, 1),
                              f"run{k} rc={r.returncode}: {r.stderr[-400:]}")
                outs.append(od)
            lay1 = json.load(open(os.path.join(outs[0], "layout.json"),
                                  encoding="utf-8"))
            lay2 = open(os.path.join(outs[0], "layout.json"), "rb").read()
            lay2b = open(os.path.join(outs[1], "layout.json"), "rb").read()
            # determinism: two runs byte-identical
            self.assertEqual(lay2, lay2b)
            # the gate-breaching rotated designation fell back, with the user
            # designation preserved verbatim in the record
            fm = lay1["meta"].get("from_layout") or {}
            fb = {e["edge"]: e for e in fm.get("manual_fallback") or []}
            self.assertIn(f"{a}->{b}", fb)
            self.assertEqual(fb[f"{a}->{b}"]["user_anchors"],
                             {"src": src, "dst": dst})
            self.assertIn("reason", fb[f"{a}->{b}"])
            # delivered geometry == the engine's own delivery (benign manual)
            benign_doc = json.loads(json.dumps(doc))
            benign_doc["edges"] = []
            ib = os.path.join(tmp, "benign.json")
            with open(ib, "w", encoding="utf-8") as f:
                json.dump(benign_doc, f, ensure_ascii=False)
            ob = os.path.join(tmp, "benign")
            rb = subprocess.run(
                [sys.executable, "-m", "stdraw", "layout", EXAMPLE,
                 "--outdir", ob, "--skip-3d", "--from-layout", ib],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=ROOT)
            self.assertIn(rb.returncode, (0, 1), rb.stderr[-400:])
            layb = json.load(open(os.path.join(ob, "layout.json"),
                                  encoding="utf-8"))
            ea = next(x for x in lay1["edges"]
                      if (x["a"], x["b"]) == (a, b))
            eb = next(x for x in layb["edges"]
                      if (x["a"], x["b"]) == (a, b))
            self.assertEqual(ea["route"], eb["route"])
            # certificate records the fallback honestly
            cert = json.load(open(os.path.join(outs[0], "certificate.json"),
                                  encoding="utf-8"))
            cfb = {e["edge"]: e
                   for e in (cert.get("from_layout") or {})
                   .get("manual_fallback") or []}
            self.assertIn(f"{a}->{b}", cfb)
            # re-render: demo-2d.html produced and non-trivial
            html = open(os.path.join(outs[0], "demo-2d.html"),
                        encoding="utf-8").read()
            self.assertIn("stdraw-svg", html)
            self.assertGreater(len(html), 10000)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
