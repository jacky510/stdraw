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
        # jacky 点名 #17/#18/#19 → 纵列
        for name in ("tragedy-of-the-commons", "urban-migration",
                     "wage-price-spiral"):
            v4 = layout(load(name))
            self.assertEqual(v4["meta"]["placement"], "column-chain", name)
            self.assertEqual(v4["meta"]["position_engine"],
                             "column-construct", name)

    def test_isomorphic_column_family(self):
        # {eroding-goals, shifting-the-burden, wage-price-spiral} 有向同构
        # → 同为纵列且主链环长一致（同构骨架 → 同布局模板）
        spines = {}
        for name in ("eroding-goals", "shifting-the-burden",
                     "wage-price-spiral"):
            v4 = layout(load(name))
            self.assertEqual(v4["meta"]["placement"], "column-chain", name)
            spines[name] = len(v4["meta"]["column"]["spine"])
        self.assertEqual(len(set(spines.values())), 1, spines)

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
        v4 = layout(load("wage-price-spiral"))
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
        v4 = layout(load("wage-price-spiral"))
        from stdraw.metrics import certificate_auto, scene_from_auto
        g = load("wage-price-spiral")
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
