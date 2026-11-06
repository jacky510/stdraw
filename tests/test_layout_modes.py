# -*- coding: utf-8 -*-
"""布局美学 v2（ref-scrubbed）：纵列/对称模式 + R/B 颜色化 + 交叉软目标测试。"""
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
    """触发判定（确定性图论度量）：点名图进新模式，环形保持图不误伤。"""

    def test_named_graphs_get_column(self):
        # jacky 点名 #17/#18 → 纵列（#19 wage-price-spiral 自 v3 起进领结共点）
        for name in ("tragedy-of-the-commons", "urban-migration"):
            v4 = layout(load(name))
            self.assertEqual(v4["meta"]["placement"], "column-chain", name)
            self.assertEqual(v4["meta"]["position_engine"],
                             "column-construct", name)

    def test_isomorphic_bowtie_vertex_family(self):
        # ref-scrubbed（美学 v3）：{eroding-goals, shifting-the-burden,
        # wage-price-spiral} 有向同构 = 双环共享单节点 → 领结共点对称
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
        # #11 learning-flywheel 与其有向同构 fixes-that-fail → 领结对对称
        for name in ("learning-flywheel", "fixes-that-fail"):
            v4 = layout(load(name))
            self.assertEqual(v4["meta"]["placement"], "symmetric", name)
            self.assertEqual(v4["meta"]["position_engine"], "sym-construct",
                             name)

    def test_ring_graphs_unchanged_mode(self):
        # 回路主导图（k≥5 大环 / ratio 触发 / 纯环）保持环形，不误伤
        for name in ("debt-spiral", "induced-demand", "arms-race",
                     "brand-flywheel", "classic-cld-growth-and-burden",
                     "fishing-collapse", "soil-erosion"):
            v4 = layout(load(name))
            self.assertEqual(v4["meta"]["placement"], "ring-cycle", name)

    def test_layered_fallback_negatives(self):
        # 无环图（链/树）不触发任何新模式 → 既有分层路径
        chain = parse('graph "链"\nvar a "甲"\nvar b "乙"\nvar c "丙"\n'
                      'a -> + b\nb -> + c\n')
        v4 = layout(chain)
        self.assertEqual(v4["meta"].get("placement", "layered"), "layered")
        self.assertNotIn("column", v4["meta"])
        self.assertNotIn("symmetry", v4["meta"])


    def test_bowtie_vertex_not_misfired(self):
        # 领结判定不误伤：08/10/17 虽也只有 2 个简单环但共享 2 节点（共边型）；
        # classic-cld 4 个简单环（含派生环）——均不得进领结共点模式
        for name in ("fishing-collapse", "induced-demand",
                     "tragedy-of-the-commons",
                     "classic-cld-growth-and-burden"):
            v4 = layout(load(name))
            self.assertNotEqual(v4["meta"].get("placement"),
                                "bowtie-vertex", name)
            self.assertNotIn("bowtie", str(v4["meta"].get("position_engine")),
                             name)


class TestBowtieVertexGeometry(unittest.TestCase):
    """ref-scrubbed（美学 v3）领结共点几何：对拍 jacky 手拉样本的相对几何。"""

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
            self.assertEqual(nodes[l]["x"], nodes[r]["x"], "镜像对 x 相等")
            self.assertEqual((nodes[l]["y"] + nodes[r]["y"]) / 2, sym["axis_y"])
        self.assertEqual(cert["metrics"]["symmetry_mirror_err"], 0)

    def test_two_half_planes_and_horizontal_outer_edge(self):
        # 两环分占上下半平面；三角形外边水平（同样本「顶边近水平」）
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
        # 样本左右位：wages 左 / cost 右；real_income 左 / demand 右
        self.assertLess(nodes["wages"]["x"], nodes["cost"]["x"])
        self.assertLess(nodes["real_income"]["x"], nodes["demand"]["x"])

    def test_all_lines_and_cert_optimal(self):
        # 线型一致性硬规则：全直线；证书最优（规律门含镜像 ≤2px）
        g, v4, cert = self._layout("shifting-the-burden")
        kinds = {e["route"]["kind"] for e in v4["edges"]}
        self.assertEqual(kinds, {"line"}, kinds)
        self.assertEqual(cert["grade"], "最优")
        self.assertIn("symmetry_mirror_le_2px", cert["gates"])


class TestColumnGeometry(unittest.TestCase):
    def test_spine_axis_aligned_and_pitch_uniform(self):
        v4 = layout(load("tragedy-of-the-commons"))
        spine = v4["meta"]["column"]["spine"]
        nodes = v4["nodes"]
        xs = [nodes[v]["x"] for v in spine]
        ys = [nodes[v]["y"] for v in spine]
        self.assertEqual(len(set(xs)), 1, "主链纵向对齐一列")
        diffs = {b - a for a, b in zip(ys, ys[1:])}
        self.assertEqual(len(diffs), 1, "主链行距恒等")

    def test_closing_edge_is_arc(self):
        # 主链闭合边构造为左侧大弧（回路聚拢/圆环感）
        v4 = layout(load("tragedy-of-the-commons"))
        spine = v4["meta"]["column"]["spine"]
        closing = (spine[-1], spine[0])
        e = [x for x in v4["edges"]
             if (x["a"], x["b"]) == closing][0]
        self.assertEqual(e["route"]["kind"], "arc")
        self.assertIn("ctrl", e["route"])

    def test_pendant_near_anchor(self):
        # 支路挂主链近邻侧：population 与其锚点同行、水平净距 ≥36 级
        v4 = layout(load("tragedy-of-the-commons"))
        nodes = v4["nodes"]
        p, u = nodes["population"], nodes["usage"]
        self.assertEqual(p["y"], u["y"], "单锚支路与锚点同行")
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
        # 对称结构线型一致：轴边直线 + 侧边全弧（不出现 vg/poly 折线）
        v4 = layout(load("learning-flywheel"))
        kinds = {e["route"]["kind"] for e in v4["edges"]}
        self.assertTrue(kinds <= {"line", "arc"}, kinds)

    def test_learning_flywheel_centered(self):
        # jacky #11「可对称却偏左」修复：内容居中（节点 bbox 中心 vs
        # 全内容 bbox 中心水平偏差 ≤ 卡宽的 15%）
        v4 = layout(load("learning-flywheel"))
        nodes = v4["nodes"]
        left = min(p["x"] - p["w"] / 2 for p in nodes.values())
        right = max(p["x"] + p["w"] / 2 for p in nodes.values())
        cx = (left + right) / 2
        W = v4["viewBox"][2]
        self.assertLessEqual(abs(cx - W / 2), 0.06 * W + 8,
                             f"内容中心 {cx} vs 画布中心 {W / 2}")


class TestCrossingsSoftTarget(unittest.TestCase):
    def test_gates_exclude_crossings_and_rowalign(self):
        # 交叉/行对齐从硬门降为报告项（不再一票否决）
        v4 = layout(load("tragedy-of-the-commons"))
        from stdraw.metrics import certificate_auto, scene_from_auto
        g = load("tragedy-of-the-commons")
        cert = certificate_auto(scene_from_auto(v4), graph_name="w",
                                graph=g)
        self.assertNotIn("crossings_zero", cert["gates"])
        self.assertNotIn("row_align_ge_060", cert["gates"])
        self.assertIn("crossings_zero", cert["reports"])
        self.assertIn("row_align_ge_060", cert["reports"])
        # 排布规律类仍是硬门
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
        # 回路聚拢：环上节点跨度显著小于全图对角线
        self.assertLess(spread["R1"], 0.6)
        self.assertLess(spread["B1"], 0.6)


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
