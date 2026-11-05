# -*- coding: utf-8 -*-
"""CLI：python -m stdraw layout <input.cld|input.json> [选项]

产出（--outdir，默认 ./stdraw-out）：
  graph.json          图模型（DSL→JSON 正规化）
  layout.json         2D 平面布局（交付坐标，全部整数）
  geometry_report.json 11 项几何自检（CI 门禁形态）
  certificate.json    五指标+排布指标+诚实分级证书
  loops_audit.json    环路语义审计（lint）
  demo-2d.html        独立渲染页（证书内嵌）
  positions3d.json    3D 各形体指派坐标
  demo-3d.html        3D 交互页（需 ../assets/three.min.js 相对路径）
"""
import argparse
import json
import os
import sys

from . import __version__
from .model import Graph
from .dsl import parse, dumps
from .planar import PlanarLayout, NotPlanarError, LayoutConfig
from .check import geometry_report_to_file
from .metrics import certificate, scene_from_planar
from .loops import loops_audit
from .render import render_html
from .layout3d import SOLIDS, layout3d
from .render3d import render_3d_html


def load_graph(path: str) -> Graph:
    if path.endswith(".json"):
        with open(path, encoding="utf-8") as f:
            return Graph.from_dict(json.load(f))
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return parse(text)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="stdraw",
        description="stdraw — planarity-aware 系统思维图引擎"
                    "（文本 DSL 进，带质量证书的图出）",
        epilog=(
            "示例：\n"
            "  stdraw layout examples/limits-to-growth.cld --outdir out\n"
            "  python -m stdraw layout examples/limits-to-growth.cld --outdir out --pitch 62\n"
            "产出（--outdir，默认 ./stdraw-out）：graph.json / layout.json /\n"
            "geometry_report.json / certificate.json / loops_audit.json /\n"
            "demo-2d.html / positions3d.json / demo-3d.html"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["layout"], help="子命令")
    ap.add_argument("input", help="输入 .cld（DSL）或 .json（图模型）")
    ap.add_argument("--outdir", default="stdraw-out")
    ap.add_argument("--skip-3d", action="store_true", help="只跑 2D 层")
    ap.add_argument("--solids", default="sphere,cube,tetra,cone",
                    help="3D 形体列表（逗号分隔）")
    ap.add_argument("--pitch", type=int, default=None,
                    help="行距 px（缺省 56；小图可调大过净距门禁，参数透明）")
    ap.add_argument("--name", default="", help="图名（缺省取 DSL graph 名）")
    a = ap.parse_args(argv)

    g = load_graph(a.input)
    os.makedirs(a.outdir, exist_ok=True)
    name = a.name or g.name or os.path.splitext(os.path.basename(a.input))[0]
    problems = g.validate()
    if problems:
        print("结构校验失败:", *problems, sep="\n  ", file=sys.stderr)
        sys.exit(2)

    def w(fn, obj):
        p = os.path.join(a.outdir, fn)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        return p

    # 图模型 + DSL 正规化文本
    p = w("graph.json", g.to_dict())
    with open(os.path.join(a.outdir, "graph.cld"), "w", encoding="utf-8") as f:
        f.write(dumps(g))
    print(f"[1/6] 图模型 OK：{len(g.nodes)} 节点 / {len(g.edges)} 边 / "
          f"{len(g.loops)} 声明环 -> {p}")

    # 环路语义审计（lint）
    lr = loops_audit(g)
    p = w("loops_audit.json", lr)
    print(f"[2/6] 环路审计：声明 {lr['summary']['declared']}，闭合 "
          f"{lr['summary']['closed']}，独立枚举 {lr['summary']['enumerated']}，"
          f"问题 {lr['summary']['problems']} -> {p}")
    for pr in lr["problems"]:
        print("   lint:", pr)

    # 2D 平面布局
    cfg = LayoutConfig()
    if a.pitch:
        cfg.pitch = a.pitch
    eng = PlanarLayout(g, cfg)
    try:
        v4 = eng.run()
    except NotPlanarError as e:
        print(f"[3/6] 2D 平面层不适用：{e}")
        print("      诚实降级：跳过 2D 证书（布局层的可替换实现属 M1+）")
        v4 = None
    else:
        labels = {n.id: n.label for n in g.nodes}
        values = {n.id: n.value for n in g.nodes if n.value}
        p = w("layout.json", v4)
        print(f"[3/6] 2D 布局：{v4['viewBox'][2]}×{v4['viewBox'][3]}，"
              f"{v4['meta']['rows']} 行 -> {p}")
        # 11 项几何自检（跑在交付坐标上）
        rc = geometry_report_to_file(
            v4, os.path.join(a.outdir, "geometry_report.json"))
        # 五指标证书
        cert = certificate(scene_from_planar(v4), graph_name=name,
                           layer="2D",
                           notes=["无关线遮挡式穿卡为设计允许（卡片不透明）"])
        p = w("certificate.json", cert)
        m = cert["metrics"]
        print(f"[4/6] 证书：交叉 {m['crossings']} / 真穿卡 {m['occlusions_true_0px']} / "
              f"净距 {m['min_card_gap']} / 对齐 {m['row_align_rate']} / CV "
              f"{m['spacing_cv']} → 分级【{cert['grade']}】-> {p}")
        # 2D demo html
        hp = os.path.join(a.outdir, "demo-2d.html")
        with open(hp, "w", encoding="utf-8") as f:
            f.write(render_html(v4, name, cert, lr, labels, values))
        print(f"      demo -> {hp}")
        if rc:
            sys.exit(1)

    # 3D 各形体指派
    if not a.skip_3d:
        gd = {"nodes": [{"id": n.id, "label": n.label} for n in g.nodes],
              "edges": [{"a": e.a, "b": e.b, "p": e.polarity} for e in g.edges]}
        solids = [s.strip() for s in a.solids.split(",") if s.strip()]
        unknown = [s for s in solids if s not in SOLIDS]
        if unknown:
            print(f"未知形体 {unknown}，可选 {list(SOLIDS)}", file=sys.stderr)
            sys.exit(2)
        layouts = {s: layout3d(gd, s) for s in solids}
        p = w("positions3d.json",
              {s: layouts[s]["positions"] for s in solids})
        print(f"[5/6] 3D 指派：{solids} -> {p}")
        hp = os.path.join(a.outdir, "demo-3d.html")
        note = ("确定性排布：槽位+最短总边长指派；3D 无交叉承诺，"
                "投影交叉由相机解决")
        with open(hp, "w", encoding="utf-8") as f:
            f.write(render_3d_html(gd, layouts, name, note))
        print(f"      demo -> {hp}（需与 assets/three.min.js 相对路径同仓）")
    print("[6/6] 完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
