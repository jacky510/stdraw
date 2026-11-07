# -*- coding: utf-8 -*-
"""Layout aesthetics v2 (ref-scrubbed): column/symmetric modes + R/B coloring + crossing soft-target tests."""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stdraw.dsl import parse
from stdraw.layout_auto import layout
from stdraw import columnlayout, symlayout

CORPUS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "benchmarks", "corpus", "classic")


def load(name):
    with open(os.path.join(CORPUS, name + ".cld"), encoding="utf-8") as f:
        return parse(f.read())


class TestModeTriggers(unittest.TestCase):
    """Trigger detection (deterministic graph-theoretic metrics): named graphs enter the new modes; ring-holding graphs are not misfired."""

    def test_named_graphs_get_column(self):
        # jacky named #17/#18 -> column (#19 wage-price-spiral moved to bowtie-vertex since v3)
        for name in ("tragedy-of-the-commons", "urban-migration"):
            v4 = layout(load(name))
            self.assertEqual(v4["meta"]["placement"], "column-chain", name)
            self.assertEqual(v4["meta"]["position_engine"],
                             "column-construct", name)

    def test_isomorphic_bowtie_vertex_family(self):
        # ref-scrubbed (aesthetics v3): {eroding-goals, shifting-the-burden,
        # wage-price-spiral} are digraph-isomorphic = two loops sharing one node -> bowtie-vertex symmetry
        for name in ("eroding-goals", "shifting-the-burden",
                     "wage-price-spiral"):
            v4 = layout(load(name))
            self.assertEqual(v4["meta"]["placement"], "bowtie-vertex", name)
            self.assertEqual(v4["meta"]["position_engine"],
                             "bowtie-construct", name)
            sym = v4["meta"]["symmetry"]
            self.assertIn("shared_node", sym)
            self.assertEqual(len(sym["loops"]), 2, name)

    def test_bowtie_symmetric(self):
        # #11 learning-flywheel and its digraph-isomorphic fixes-that-fail -> bowtie-pair symmetry
        for name in ("learning-flywheel", "fixes-that-fail"):
            v4 = layout(load(name))
            self.assertEqual(v4["meta"]["placement"], "symmetric", name)
            self.assertEqual(v4["meta"]["position_engine"], "sym-construct",
                             name)

    def test_ring_graphs_unchanged_mode(self):
        # loop-dominant graphs (k>=5 large ring / ratio trigger / pure ring) stay ring, unharmed
        # (classic-cld switched to spine-wing since v0.7.1 ref-scrubbed, moved out of this group)
        for name in ("debt-spiral", "induced-demand", "arms-race",
                     "brand-flywheel", "fishing-collapse", "soil-erosion"):
            v4 = layout(load(name))
            self.assertEqual(v4["meta"]["placement"], "ring-cycle", name)

    def test_layered_fallback_negatives(self):
        # acyclic graphs (chain/tree) trigger no new mode -> existing layered path
        chain = parse('graph "链"\nvar a "甲"\nvar b "乙"\nvar c "丙"\n'
                      'a -> + b\nb -> + c\n')
        v4 = layout(chain)
        self.assertEqual(v4["meta"].get("placement", "layered"), "layered")
        self.assertNotIn("column", v4["meta"])
        self.assertNotIn("symmetry", v4["meta"])


    def test_bowtie_vertex_not_misfired(self):
        # bowtie detection must not misfire: 08/10/17 also have just 2 simple loops but share 2 nodes (edge-sharing type);
        # classic-cld has 4 simple loops (incl. derived ones) -- none may enter bowtie-vertex mode
        for name in ("fishing-collapse", "induced-demand",
                     "tragedy-of-the-commons",
                     "classic-cld-growth-and-burden"):
            v4 = layout(load(name))
            self.assertNotEqual(v4["meta"].get("placement"),
                                "bowtie-vertex", name)
            self.assertNotIn("bowtie", str(v4["meta"].get("position_engine")),
                             name)


class TestBowtieVertexGeometry(unittest.TestCase):
    """ref-scrubbed (aesthetics v3) bowtie-vertex geometry: relative geometry cross-checked against jacky's hand-drawn sample."""

    def _layout(self, name):
        from stdraw.metrics import certificate_auto, scene_from_auto
        g = load(name)
        v4 = layout(g)
        cert = certificate_auto(scene_from_auto(v4), graph_name=name, graph=g)
        return g, v4, cert

    def test_shared_centered_and_mirror_symmetric(self):
        g, v4, cert = self._layout("wage-price-spiral")
        sym = v4["meta"]["symmetry"]
        nodes = v4["nodes"]
        sh = nodes[sym["shared_node"]]
        self.assertEqual(sh["x"], sym["axis_x"])
        self.assertEqual(sh["y"], sym["axis_y"])
        for l, r in sym["mirror_pairs"]:
            self.assertEqual(nodes[l]["x"], nodes[r]["x"], "mirror pair x equal")
            self.assertEqual((nodes[l]["y"] + nodes[r]["y"]) / 2, sym["axis_y"])
        self.assertEqual(cert["metrics"]["symmetry_mirror_err"], 0)

    def test_two_half_planes_and_horizontal_outer_edge(self):
        # the two loops occupy the upper/lower half-planes; the outer triangle edge is horizontal (like the sample's "top edge near-horizontal")
        g, v4, _ = self._layout("wage-price-spiral")
        sym = v4["meta"]["symmetry"]
        nodes = v4["nodes"]
        sh_y = nodes[sym["shared_node"]]["y"]
        tops = [v for v in sym["loops"][0] if v != sym["shared_node"]]
        bots = [v for v in sym["loops"][1] if v != sym["shared_node"]]
        self.assertTrue(all(nodes[v]["y"] < sh_y for v in tops))
        self.assertTrue(all(nodes[v]["y"] > sh_y for v in bots))
        self.assertEqual(nodes[tops[0]]["y"], nodes[tops[1]]["y"])
        self.assertEqual(nodes[bots[0]]["y"], nodes[bots[1]]["y"])
        # sample left/right placement: wages left / cost right; real_income left / demand right
        self.assertLess(nodes["wages"]["x"], nodes["cost"]["x"])
        self.assertLess(nodes["real_income"]["x"], nodes["demand"]["x"])

    def test_all_lines_and_cert_optimal(self):
        # line-kind consistency hard rule: all straight; certificate optimal (regularity gate incl. mirror <=2px)
        g, v4, cert = self._layout("shifting-the-burden")
        kinds = {e["route"]["kind"] for e in v4["edges"]}
        self.assertEqual(kinds, {"line"}, kinds)
        self.assertEqual(cert["grade"], "best")
        self.assertIn("symmetry_mirror_le_2px", cert["gates"])


class TestColumnGeometry(unittest.TestCase):
    def test_spine_axis_aligned_and_pitch_uniform(self):
        v4 = layout(load("tragedy-of-the-commons"))
        spine = v4["meta"]["column"]["spine"]
        nodes = v4["nodes"]
        xs = [nodes[v]["x"] for v in spine]
        ys = [nodes[v]["y"] for v in spine]
        self.assertEqual(len(set(xs)), 1, "main chain aligned in one column")
        diffs = {b - a for a, b in zip(ys, ys[1:])}
        self.assertEqual(len(diffs), 1, "main chain row pitch uniform")

    def test_closing_edge_is_arc(self):
        # the spine closing edge is built as a large left-side arc (loop cohesion / ring feel)
        v4 = layout(load("tragedy-of-the-commons"))
        spine = v4["meta"]["column"]["spine"]
        closing = (spine[-1], spine[0])
        e = [x for x in v4["edges"]
             if (x["a"], x["b"]) == closing][0]
        self.assertEqual(e["route"]["kind"], "arc")
        self.assertIn("ctrl", e["route"])

    def test_pendant_near_anchor(self):
        # pendant hangs on the near side of the spine: population is on the same row as its anchor, horizontal clearance at the >=36 tier
        v4 = layout(load("tragedy-of-the-commons"))
        nodes = v4["nodes"]
        p, u = nodes["population"], nodes["usage"]
        self.assertEqual(p["y"], u["y"], "single-anchor branch on the same row as its anchor")
        gap = abs(p["x"] - u["x"]) - (p["w"] + u["w"]) / 2
        self.assertGreaterEqual(gap, 34)


class TestSymmetricGeometry(unittest.TestCase):
    def test_mirror_pairs_symmetric(self):
        v4 = layout(load("learning-flywheel"))
        sym = v4["meta"]["symmetry"]
        axis = sym["axis_x"]
        l, r = sym["mirror_pairs"][0]
        nodes = v4["nodes"]
        self.assertAlmostEqual((nodes[l]["x"] + nodes[r]["x"]) / 2, axis,
                               delta=0.51)
        self.assertEqual(nodes[l]["y"], nodes[r]["y"])

    def test_line_type_consistency(self):
        # symmetric structures keep line kinds consistent: axis edge straight + side edges all arcs (no vg/poly polylines)
        v4 = layout(load("learning-flywheel"))
        kinds = {e["route"]["kind"] for e in v4["edges"]}
        self.assertTrue(kinds <= {"line", "arc"}, kinds)

    def test_learning_flywheel_centered(self):
        # jacky #11 "could be symmetric but sits left" fix: content centered (node bbox
        # center vs full-content bbox center horizontal deviation <= 15% of card width)
        v4 = layout(load("learning-flywheel"))
        nodes = v4["nodes"]
        left = min(p["x"] - p["w"] / 2 for p in nodes.values())
        right = max(p["x"] + p["w"] / 2 for p in nodes.values())
        cx = (left + right) / 2
        W = v4["viewBox"][2]
        self.assertLessEqual(abs(cx - W / 2), 0.06 * W + 8,
                             f"content center {cx} vs canvas center {W / 2}")


class TestCrossingsSoftTarget(unittest.TestCase):
    def test_gates_exclude_crossings_and_rowalign(self):
        # crossings/row alignment demoted from hard gate to report item (no longer a one-vote veto)
        v4 = layout(load("tragedy-of-the-commons"))
        from stdraw.metrics import certificate_auto, scene_from_auto
        g = load("tragedy-of-the-commons")
        cert = certificate_auto(scene_from_auto(v4), graph_name="w",
                                graph=g)
        self.assertNotIn("crossings_zero", cert["gates"])
        self.assertNotIn("row_align_ge_060", cert["gates"])
        self.assertIn("crossings_zero", cert["reports"])
        self.assertIn("row_align_ge_060", cert["reports"])
        # placement-regularity checks remain hard gates
        self.assertIn("column_axis_aligned", cert["gates"])
        self.assertIn("spine_pitch_uniform", cert["gates"])

    def test_loop_cohesion_metric(self):
        v4 = layout(load("wage-price-spiral"))
        from stdraw.metrics import certificate_auto, scene_from_auto
        g = load("wage-price-spiral")
        cert = certificate_auto(scene_from_auto(v4), graph_name="w",
                                graph=g)
        spread = cert["metrics"]["loop_cohesion_spread"]
        self.assertIn("R1", spread)
        self.assertIn("B1", spread)
        # loop cohesion: on-loop node spread is markedly smaller than the whole-graph diagonal
        self.assertLess(spread["R1"], 0.6)
        self.assertLess(spread["B1"], 0.6)


class TestSpineWing(unittest.TestCase):
    """ref-scrubbed (v0.7.1) spine-wing: trigger detection + sample-geometry cross-check + certificate gates."""

    def _layout(self, name="classic-cld-growth-and-burden"):
        from stdraw.metrics import certificate_auto, scene_from_auto
        g = load(name)
        v4 = layout(g)
        cert = certificate_auto(scene_from_auto(v4), graph_name=name, graph=g)
        return g, v4, cert

    def test_trigger_hits_only_classic_cld(self):
        # 19-graph sweep: only classic-cld hits (hub pairs with >=3 common neighbors + rest secondary cluster);
        # limits-to-growth with isomorphic spine (rest=0) and the pure-ring family do not trigger
        for name in ("limits-to-growth", "arms-race", "bullwhip",
                     "tragedy-of-the-commons", "learning-flywheel"):
            v4 = layout(load(name))
            self.assertNotEqual(v4["meta"]["placement"], "spine-wing", name)
        g, v4, _ = self._layout()
        self.assertEqual(v4["meta"]["placement"], "spine-wing")
        self.assertEqual(v4["meta"]["position_engine"], "spine-construct")

    def test_sample_relative_geometry(self):
        # cross-check against jacky's hand-drawn sample: spine vertical on axis, wings pressed onto the midline,
        # mirror pairs symmetric up/down, the single one banded with the spine bottom
        g, v4, _ = self._layout()
        nodes = v4["nodes"]
        sw = v4["meta"]["spine_wing"]
        top, bot = sw["spine"]
        self.assertEqual(nodes[top]["x"], nodes[bot]["x"], "spine x equal (idealizing the sample's 1px x difference)")
        self.assertLess(nodes[top]["y"], nodes[bot]["y"], "head top / tail bottom")
        for w in sw["wings"]:
            self.assertEqual(nodes[w]["y"], sw["axis_y"], "wing slots pressed onto the midline (sample y exactly equal)")
        for up, down in sw["mirror_pairs"]:
            self.assertEqual(nodes[up]["x"], nodes[down]["x"], "mirror pair x equal (idealizing the sample's 6px x difference)")
            self.assertEqual((nodes[up]["y"] + nodes[down]["y"]) / 2, sw["axis_y"])
        # sample left/right placement: word/potential left, crowding right, quickfix up / sideeffect down
        axis_x = sw["axis_x"]
        self.assertLess(nodes["word"]["x"], axis_x)
        self.assertLess(nodes["potential"]["x"], axis_x)
        self.assertGreater(nodes["crowding"]["x"], axis_x)
        self.assertLess(nodes["quickfix"]["y"], sw["axis_y"])
        self.assertGreater(nodes["sideeffect"]["y"], sw["axis_y"])

    def test_cert_optimal_and_equivalent_gates(self):
        # certificate optimal + spine-wing equivalent gates (spine x alignment / midline adherence / mirror <=2px)
        g, v4, cert = self._layout()
        self.assertEqual(cert["grade"], "best")
        self.assertEqual(cert["metrics"]["crossings"], 0)
        for k in ("spine_axis_le_2px", "midline_adherence_le_2px",
                  "symmetry_mirror_le_2px"):
            self.assertTrue(cert["gates"][k], k)
        self.assertEqual(cert["metrics"]["spine_axis_deviation"], 0)
        self.assertEqual(cert["metrics"]["midline_deviation"], 0)
        self.assertEqual(cert["metrics"]["symmetry_mirror_err"], 0)


class TestSpineWingManualEquivalence(unittest.TestCase):
    """ref-scrubbed rework: auto placement vs jacky's hand-drawn sample are
    **structurally equivalent** (identical role grouping).

    Sample = benchmarks/manual/classic-cld-manual-layout.json (jacky's
    hand-drawn ground truth, archived as the ref-scrubbed attachment, see
    benchmarks/manual/README.md). The role grouping (who sits on the spine /
    midline row / right-wing column / single slot) is **derived
    automatically** from the sample coordinates via structural regularities
    (no coordinate copy is written into the test), then the engine output is
    required to group identically and to meet the quantitative regularities:
    spine |dx|<=2, midline row |dy|<=2, wing column |dx|<=2 (idealizing the
    sample's own 6px), single one banded with the spine bottom |dy|<=2, and
    relative sides (left/right, up/down) matching the sample node by node.
    """

    MANUAL = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "benchmarks", "manual",
        "classic-cld-manual-layout.json")

    @classmethod
    def _roles(cls, nodes):
        """Derive the role grouping from coordinates (deterministic; the sample
        and the engine output share the same deriver).

        (1) midline row: the largest group with equal y +/-2 (>=2 members);
        (2) endpoint spine column: the same-column pair straddling the midline
           (|dx|<=2), ties broken toward the larger y span (wing mirror pairs
           are also same-column midline-straddling in the engine; the spine
           must be the pair with the largest span);
        (3) right-wing same column: among the remaining nodes, the pair with
           |dx|<=8 (the sample's own 6px);
        (4) the rest = single (exactly 1, mirror constructibility).
        """
        ids = sorted(nodes)
        xs = {i: nodes[i]["x"] for i in ids}
        ys = {i: nodes[i]["y"] for i in ids}
        mid = []
        for i in ids:
            row = sorted(j for j in ids if abs(ys[j] - ys[i]) <= 2)
            if len(row) > len(mid):
                mid = row
        self2 = len(mid) >= 2
        assert self2, "no midline row group"
        mid_y = sum(ys[i] for i in mid) / len(mid)
        rest = [i for i in ids if i not in mid]
        cands = [(a, b) for a in rest for b in rest
                 if a < b and abs(xs[a] - xs[b]) <= 2
                 and (ys[a] - mid_y) * (ys[b] - mid_y) < 0]
        assert cands, "no same-column endpoint pair straddling the midline"
        spine = min(cands, key=lambda p: (-abs(ys[p[0]] - ys[p[1]]),
                                          tuple(sorted(p))))
        left = [i for i in rest if i not in spine]
        wcands = [(a, b) for a in left for b in left
                  if a < b and abs(xs[a] - xs[b]) <= 8]
        assert wcands, "no same-column wing pair"
        wing = max(wcands, key=lambda p: (abs(ys[p[0]] - ys[p[1]]), p))
        single = set(left) - set(wing)
        assert len(single) == 1, f"single count {len(single)} != 1"
        return {"spine": set(spine), "midline": set(mid),
                "wing_col": set(wing), "single": single,
                "mid_y": mid_y,
                "top": max(spine, key=lambda i: -ys[i]),
                "bottom": max(spine, key=lambda i: ys[i])}

    def test_engine_roles_and_geometry_match_sample(self):
        with open(self.MANUAL, encoding="utf-8") as f:
            sample = json.load(f)["nodes"]
        s = self._roles(sample)
        v4 = layout(load("classic-cld-growth-and-burden"))
        self.assertEqual(v4["meta"]["placement"], "spine-wing")
        nodes = v4["nodes"]
        e = self._roles(nodes)
        # (1) role grouping identical group by group
        self.assertEqual(e["spine"], s["spine"], "spine grouping")
        self.assertEqual(e["midline"], s["midline"], "midline row grouping")
        self.assertEqual(e["wing_col"], s["wing_col"], "right-wing column grouping")
        self.assertEqual(e["single"], s["single"], "single grouping")
        # (2) quantitative regularities (engine construction constraints meet this bar)
        top, bot = e["top"], e["bottom"]
        self.assertLessEqual(abs(nodes[top]["x"] - nodes[bot]["x"]), 2,
                             "spine endpoints same column <=2px")
        mid_y = e["mid_y"]
        for w in e["midline"]:
            self.assertLessEqual(abs(nodes[w]["y"] - mid_y), 2, f"midline row {w}")
        up, down = sorted(e["wing_col"], key=lambda i: nodes[i]["y"])
        wx = [nodes[i]["x"] for i in e["wing_col"]]
        self.assertLessEqual(max(wx) - min(wx), 2, "right wing same column <=2px")
        self.assertLess(nodes[up]["y"], mid_y, "upper wing slot above the midline")
        self.assertGreater(nodes[down]["y"], mid_y, "lower wing slot below the midline")
        sg = next(iter(e["single"]))
        self.assertLessEqual(abs(nodes[sg]["y"] - nodes[bot]["y"]), 2,
                             "single banded with the spine bottom <=2px")
        # (3) relative sides match the sample node by node (left/right, up/down)
        sx = (nodes[top]["x"] + nodes[bot]["x"]) / 2
        ssx = (sample[s["top"]]["x"] + sample[s["bottom"]]["x"]) / 2
        for w in e["midline"]:
            self.assertEqual(nodes[w]["x"] < sx, sample[w]["x"] < ssx,
                             f"midline row {w} left/right side")
        self.assertEqual(nodes[sg]["x"] > sx, sample[sg]["x"] > ssx,
                         "single on the right of the spine")
        self.assertLess(nodes[sg]["x"], min(wx), "single inside the wing column")
        s_wing = sorted(s["wing_col"], key=lambda i: sample[i]["y"])
        self.assertEqual(up == min(e["wing_col"], key=lambda i: nodes[i]["y"]),
                         s_wing[0] == min(s["wing_col"], key=lambda i: sample[i]["y"]),
                         "wing up/down order matches the sample")


class TestAnchorBand(unittest.TestCase):
    """ref-scrubbed second-review rework: delivered-anchor in-band caliber
    (edge-midpoint +/-1/4 band, corner hits = 0).

    spine-wing (classic-cld) = 100% in-band hard gate; the other 19 corpus
    graphs are locked to v0.7.2 baseline ratios (same-source caliber as the
    CI gate tests/ci_checks.py BASELINE_BAND).
    """

    def _band_stats(self, v4):
        ch = float(v4["meta"].get("cardH", 44.0))
        total = band = corner = 0
        worst = []
        for e in v4["edges"]:
            rt = e["route"]
            for side, idx in (("a", 0), ("b", len(rt["points"]) - 1)):
                nd = v4["nodes"][e[side]]
                cx, cy, hw, hh = nd["x"], nd["y"], nd["w"] / 2.0, ch / 2.0
                p = rt["points"][idx]
                dxo, dyo = p[0] - cx, p[1] - cy
                on_x = abs(abs(dxo) - hw) <= abs(abs(dyo) - hh)
                total += 1
                if abs(abs(dxo) - hw) < 0.75 and abs(abs(dyo) - hh) < 0.75:
                    corner += 1
                ok = (abs(dyo) <= hh / 2 + 1e-6) if on_x \
                    else (abs(dxo) <= hw / 2 + 1e-6)
                if ok:
                    band += 1
                elif len(worst) < 3:
                    worst.append(f"{e['a']}->{e['b']}:{side}")
        return total, band, corner, worst

    def test_spine_wing_anchors_all_in_band(self):
        # jacky's second-review rejection: classic-cld delivered anchors must all be in-band with zero corner hits
        # (the symptom-fix dashed departure (602,174) 3px-from-corner out-of-band violation was fixed by locally
        # rerouting the inter-loop pair in-band -- straight line + right-edge poly detour, all edge-midpoint anchors)
        v4 = layout(load("classic-cld-growth-and-burden"))
        self.assertEqual(v4["meta"]["placement"], "spine-wing")
        total, band, corner, worst = self._band_stats(v4)
        self.assertEqual(corner, 0, "corner hits must = 0")
        self.assertEqual(band, total, f"spine-wing anchors must be 100% in-band {worst}")

    def test_corpus_baseline_band_ratios_hold(self):
        # remaining engines locked to the v0.7.2 baseline (zero-drift constraint: leftover out-of-band stays unfixed, prevents regression)
        baseline = {"brand-flywheel": 14 / 16, "fishing-collapse": 15 / 18,
                    "eroding-goals": 8 / 12, "shifting-the-burden": 10 / 16,
                    "wage-price-spiral": 8 / 12}
        for name, floor in baseline.items():
            v4 = layout(load(name))
            total, band, corner, _ = self._band_stats(v4)
            self.assertEqual(corner, 0, f"{name} corner hits must = 0")
            self.assertGreaterEqual(band / total, floor - 1e-9,
                                    f"{name} in-band ratio fell below the v0.7.2 baseline")


class TestDeterminism(unittest.TestCase):
    def test_two_runs_byte_identical(self):
        py = sys.executable
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out1 = os.path.join(os.environ.get("TMPDIR", "."), "t_col_r1")
        out2 = os.path.join(os.environ.get("TMPDIR", "."), "t_col_r2")
        src = os.path.join(CORPUS, "urban-migration.cld")
        for out in (out1, out2):
            subprocess.run([py, "-m", "stdraw", "layout", src,
                            "--outdir", out, "--skip-3d"],
                           cwd=root, check=True, capture_output=True)
        for fn in ("layout.json", "certificate.json", "geometry_report.json"):
            with open(os.path.join(out1, fn), "rb") as f:
                b1 = f.read()
            with open(os.path.join(out2, fn), "rb") as f:
                b2 = f.read()
            self.assertEqual(b1, b2, fn)


if __name__ == "__main__":
    unittest.main()
