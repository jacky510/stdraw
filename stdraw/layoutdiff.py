# -*- coding: utf-8 -*-
"""布局 diff（审美采集闭环，ref-scrubbed）：auto 布局 vs 手动布局的三层对比。

人拖 → 机器 diff → AI 归纳审美规律 → 反哺目标函数；本模块是「机器 diff」环节，
输出机器可读（JSON）+ 人可读（stdout 表）双格式：

  1) 节点级：每节点位移向量 (dx,dy,|d|) + 朝向归类（往环心收 / 往列对齐靠 /
     往对称位移；|d|<4px 记「未移动」）；
  2) 结构级：关键指标前后变化表——交叉数 / 穿卡数(1px 口径) / 行对齐率 /
     卡间最小净距 / 间距 CV / 平均边长 / 对称轴误差 / 回路聚拢度
     （auto vs manual 两列 + 差值）；
  3) 语义级（--cld/.json 带图时）：被移动节点参与的回路与角色（环上/支路），
     移动后是否更靠近其主环；逐回路聚拢度变化。

口径（全部可复算，定义同步写进输出 definitions 块）：
  - 边几何：折线取 route.points；弧线（arc+ctrl）按二次贝塞尔 24 段离散；
  - 交叉：不共享端点的边对，任一段相交记 1 对（与证书 crossings 同口径）；
  - 穿卡：边采样点（4px 步长）进入无关卡矩形（+1px 余量）按 边×卡 去重计数；
  - 行对齐率：y 差 ≤4px 成组，组内计数 / n（metrics.ROW_EPS 口径）；
  - 间距 CV：最近邻中心距 std/mean（证书同口径）；
  - 对称轴误差：竖直轴 x=mean(x_i)；节点 i 的镜像点 (2a-x_i, y_i) 到最近
    其他节点的距离记 err_i，对称轴误差 = mean(err_i)（越小越镜像对称）；
  - 回路聚拢度：环上节点平均两两距离 / 环直径（最大两两距离），越小越聚拢。
"""
import argparse
import json
import math
import os
import sys


# ── 几何基元（与 metrics.py/routing.py 同口径的独立复算）──
EPS = 1e-9
ROW_EPS = 4


def _seg_cross(p1, p2, p3, p4):
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < EPS else (1 if v > 0 else -1)
    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    if d1 != d2 and d3 != d4 and d1 != 0 and d3 != 0:
        return True
    if d1 == 0 and d2 == 0 and d3 == 0 and d4 == 0:
        def on(a, b, c):
            return (min(a[0], b[0]) - EPS <= c[0] <= max(a[0], b[0]) + EPS and
                    min(a[1], b[1]) - EPS <= c[1] <= max(a[1], b[1]) + EPS)
        if on(p3, p4, p1) or on(p3, p4, p2) or on(p1, p2, p3) or on(p1, p2, p4):
            near = [q for q in (p3, p4) for p in (p1, p2)
                    if abs(q[0] - p[0]) < EPS and abs(q[1] - p[1]) < EPS]
            return len(near) == 0
    return False


def _dist_point_rect(px, py, cx, cy, hw, hh):
    dx = max(abs(px - cx) - hw, 0.0)
    dy = max(abs(py - cy) - hh, 0.0)
    return math.hypot(dx, dy)


def _quad_points(p0, ctrl, p1, n=24):
    out = []
    for k in range(n + 1):
        t = k / n
        u = 1 - t
        out.append((u * u * p0[0] + 2 * u * t * ctrl[0] + t * t * p1[0],
                    u * u * p0[1] + 2 * u * t * ctrl[1] + t * t * p1[1]))
    return out


def _sample(pts, step=4.0):
    out = []
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        d = math.hypot(x2 - x1, y2 - y1)
        n = max(1, int(d / step))
        for k in range(n):
            t = k / n
            out.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
    out.append(tuple(pts[-1]))
    return out


# ── 布局装载与指标 ──
def _load_layout(path):
    with open(path, encoding="utf-8") as f:
        lay = json.load(f)
    if "nodes" not in lay or "edges" not in lay:
        raise SystemExit(f"{path}: 不是 layout.json（缺 nodes/edges）")
    return lay


def _edge_polys(lay):
    """边列表 [(a,b)] 与离散折线（弧线按贝塞尔 24 段）。"""
    edges, polys = [], []
    for e in lay["edges"]:
        r = e.get("route", {})
        pts = [tuple(p) for p in r.get("points", [])]
        if r.get("arc") and r.get("ctrl") and len(pts) >= 2:
            pts = _quad_points(pts[0], tuple(r["ctrl"]), pts[-1], 24)
        edges.append((e["a"], e["b"]))
        polys.append(pts)
    return edges, polys


def _symmetry_err(pos):
    """对称轴误差：竖直轴 x=mean(x)；mean_i min_{j≠i} dist(mirror_i, p_j)。"""
    if len(pos) < 2:
        return 0.0
    axis = sum(p[0] for p in pos.values()) / len(pos)
    errs = []
    for v, (x, y) in pos.items():
        mx = 2 * axis - x
        best = min(math.hypot(mx - q[0], y - q[1])
                   for w, q in pos.items() if w != v)
        errs.append(best)
    return sum(errs) / len(errs)


def _node_sym_err(pos, v):
    axis = sum(p[0] for p in pos.values()) / len(pos)
    x, y = pos[v]
    mx = 2 * axis - x
    return min(math.hypot(mx - q[0], y - q[1]) for w, q in pos.items() if w != v)


def layout_metrics(lay, graph=None):
    """单布局的关键指标（证书同口径的独立复算 + 对称/聚拢扩展）。"""
    nodes = lay["nodes"]
    card_h = lay.get("meta", {}).get("cardH", 44)
    ids = list(nodes)
    pos = {v: (nodes[v]["x"], nodes[v]["y"]) for v in ids}
    boxes = {v: (nodes[v]["x"], nodes[v]["y"],
                 nodes[v].get("w", 140) / 2, card_h / 2) for v in ids}
    edges, polys = _edge_polys(lay)

    crossings = 0
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            a1, b1 = edges[i]
            a2, b2 = edges[j]
            if a1 in (a2, b2) or b1 in (a2, b2):
                continue
            hit = False
            for s1 in zip(polys[i][:-1], polys[i][1:]):
                for s2 in zip(polys[j][:-1], polys[j][1:]):
                    if _seg_cross(s1[0], s1[1], s2[0], s2[1]):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                crossings += 1

    occ = 0
    for i, (a, b) in enumerate(edges):
        pts = _sample(polys[i])
        for v in ids:
            if v in (a, b):
                continue
            cx, cy, hw, hh = boxes[v]
            if any(_dist_point_rect(px, py, cx, cy, hw + 1, hh + 1) <= 0
                   for (px, py) in pts):
                occ += 1

    total_len = 0.0
    for pts in polys:
        total_len += sum(math.dist(pts[k], pts[k + 1])
                         for k in range(len(pts) - 1))
    avg_len = total_len / len(polys) if polys else 0.0

    ysorted = sorted(p[1] for p in pos.values())
    aligned, i = 0, 0
    while i < len(ysorted):
        j = i
        while j + 1 < len(ysorted) and ysorted[j + 1] - ysorted[j] <= ROW_EPS:
            j += 1
        if j > i:
            aligned += j - i + 1
        i = j + 1
    row_rate = aligned / len(ids) if ids else 0.0

    gaps = []
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            va, vb = boxes[ids[a]], boxes[ids[b]]
            dx = abs(va[0] - vb[0]) - (va[2] + vb[2])
            dy = abs(va[1] - vb[1]) - (va[3] + vb[3])
            gaps.append(math.hypot(max(dx, 0.0), max(dy, 0.0)))
    min_gap = min(gaps) if gaps else 0.0

    nn = []
    for a in ids:
        nn.append(min(math.dist(pos[a], pos[b]) for b in ids if b != a))
    mean_nn = sum(nn) / len(nn) if nn else 0.0
    cv = (math.sqrt(sum((d - mean_nn) ** 2 for d in nn) / len(nn)) / mean_nn
          if nn and mean_nn else 0.0)

    m = {
        "crossings": crossings,
        "edge_card_press_1px": occ,
        "row_align_rate": round(row_rate, 3),
        "min_card_gap": round(min_gap, 1),
        "spacing_cv": round(cv, 3),
        "avg_edge_length": round(avg_len, 1),
        "symmetry_axis_err_px": round(_symmetry_err(pos), 1),
    }

    # 回路聚拢度（带图时）：环上节点平均两两距离 / 环直径
    if graph is not None:
        loops = {}
        for lp in graph.loops:
            members = [v for v in lp.nodes if v in pos]
            if len(members) < 2:
                continue
            ds = [math.dist(pos[a], pos[b])
                  for ii, a in enumerate(members) for b in members[ii + 1:]]
            dia = max(ds)
            loops[lp.id] = {
                "cohesion": round((sum(ds) / len(ds)) / dia, 3) if dia > EPS else None,
                "mean_pairwise_px": round(sum(ds) / len(ds), 1),
                "diameter_px": round(dia, 1),
            }
        m["loops"] = loops
    return m


# ── 三层 diff ──
def diff_layouts(auto, manual, graph=None, auto_path="", manual_path=""):
    an, mn = auto["nodes"], manual["nodes"]
    missing = [v for v in an if v not in mn]
    extra = [v for v in mn if v not in an]
    if missing or extra:
        raise SystemExit(f"两布局节点集不一致：缺 {missing}，多 {extra}")
    apos = {v: (an[v]["x"], an[v]["y"]) for v in an}
    mpos = {v: (mn[v]["x"], mn[v]["y"]) for v in mn}

    loops_of = {}
    if graph is not None:
        for lp in graph.loops:
            for v in lp.nodes:
                loops_of.setdefault(v, []).append(lp.id)

    # 列对齐参照：manual 里 ≥3 节点共享（±2px）的 x 视为列
    def _columns(pos):
        xs = sorted(p[0] for p in pos.values())
        cols, cur = [], [xs[0]]
        for x in xs[1:]:
            if x - cur[-1] <= 2:
                cur.append(x)
            else:
                cols.append(cur)
                cur = [x]
        cols.append(cur)
        return [sum(c) / len(c) for c in cols if len(c) >= 3]

    mcols = _columns(mpos)

    node_level = []
    for v in sorted(an):
        dx = mpos[v][0] - apos[v][0]
        dy = mpos[v][1] - apos[v][1]
        d = math.hypot(dx, dy)
        item = {"node": v, "dx": dx, "dy": dy, "|d|": round(d, 1),
                "tags": []}
        if d < 4:
            item["tags"] = ["未移动(<4px)"]
            node_level.append(item)
            continue
        # 往环心收：位移与「环心(auto) - 原位置」夹角小（投影占比 ≥0.6）
        for lid in loops_of.get(v, []):
            members = [w for w in
                       next(l for l in graph.loops if l.id == lid).nodes
                       if w in apos]
            c = (sum(apos[w][0] for w in members) / len(members),
                 sum(apos[w][1] for w in members) / len(members))
            vec = (c[0] - apos[v][0], c[1] - apos[v][1])
            proj = (dx * vec[0] + dy * vec[1]) / (d * math.hypot(*vec)) \
                if math.hypot(*vec) > EPS else 0.0
            if proj >= 0.6:
                item["tags"].append(f"往环心收({lid})")
            elif proj <= -0.6:
                item["tags"].append(f"背离环心({lid})")
        # 往列对齐靠：manual x 落进某列（±2px），auto x 不在
        if any(abs(mpos[v][0] - col) <= 2 for col in mcols) and \
           not any(abs(apos[v][0] - col) <= 2 for col in mcols):
            item["tags"].append("往列对齐靠")
        # 往对称位移：该节点对称误差显著下降（<70%）
        if _node_sym_err(mpos, v) < 0.7 * _node_sym_err(apos, v):
            item["tags"].append("往对称位移")
        if not item["tags"]:
            item["tags"] = ["自由位移"]
        node_level.append(item)

    ma, mm = layout_metrics(auto, graph), layout_metrics(manual, graph)
    structural = {}
    for k in ("crossings", "edge_card_press_1px", "row_align_rate",
              "min_card_gap", "spacing_cv", "avg_edge_length",
              "symmetry_axis_err_px"):
        structural[k] = {"auto": ma[k], "manual": mm[k],
                         "delta": round(mm[k] - ma[k], 3)}

    semantic = None
    if graph is not None:
        sem_nodes = []
        for it in node_level:
            v = it["node"]
            if it["tags"] == ["未移动(<4px)"] or not loops_of.get(v):
                if it["tags"] != ["未移动(<4px)"] and not loops_of.get(v):
                    sem_nodes.append({"node": v, "role": "支路",
                                      "loops": []})
                continue
            entries = []
            for lid in loops_of[v]:
                members = [w for w in
                           next(l for l in graph.loops if l.id == lid).nodes
                           if w in apos]
                peers_a = [w for w in members if w != v]
                peers_m = peers_a
                da = (sum(math.dist(apos[v], apos[w]) for w in peers_a)
                      / len(peers_a)) if peers_a else 0.0
                dm = (sum(math.dist(mpos[v], mpos[w]) for w in peers_m)
                      / len(peers_m)) if peers_m else 0.0
                entries.append({"loop": lid,
                                "closer_to_loop_center_after": dm < da,
                                "dist_auto_px": round(da, 1),
                                "dist_manual_px": round(dm, 1)})
            sem_nodes.append({"node": v, "role": "环上",
                              "loops": loops_of[v], "loop_moves": entries})
        semantic = {
            "nodes": sem_nodes,
            "loops": {
                lid: {"cohesion_auto": ma["loops"].get(lid, {}).get("cohesion"),
                      "cohesion_manual": mm["loops"].get(lid, {}).get("cohesion"),
                      "mean_pairwise_delta_px": round(
                          (mm["loops"].get(lid, {}).get("mean_pairwise_px", 0) -
                           ma["loops"].get(lid, {}).get("mean_pairwise_px", 0)), 1)}
                for lid in ma.get("loops", {})}

        }

    return {
        "tool": "stdraw layout-diff",
        "auto": auto_path,
        "manual": manual_path,
        "node_level": node_level,
        "structural": structural,
        "semantic": semantic,
        "definitions": {
            "moved": "|d| >= 4px；其余记「未移动」",
            "crossings": "不共享端点的边对任一段相交记 1 对（证书同口径）；"
                         "弧线按二次贝塞尔 24 段离散",
            "edge_card_press_1px": "边采样点(4px)进入无关卡矩形(+1px)按 边×卡 去重",
            "row_align_rate": "y 差 ≤4px 成组计数 / n",
            "symmetry_axis_err_px": "轴 x=mean(x_i)；mean_i min_{j≠i} dist(mirror_i, p_j)，"
                                    "越小越镜像对称",
            "loop_cohesion": "环上节点平均两两距离 / 环直径（越小越聚拢）",
            "delta": "manual - auto",
        },
    }


def _human(diff):
    out = []
    out.append(f"布局 diff：{diff['auto']} (auto) vs {diff['manual']} (manual)")
    out.append("")
    out.append("── 节点级（位移向量 + 朝向）──")
    for it in diff["node_level"]:
        out.append(f"  {it['node']:<24} dx={it['dx']:>5} dy={it['dy']:>5} "
                   f"|d|={it['|d|']:>6}  {'; '.join(it['tags'])}")
    out.append("")
    out.append("── 结构级（auto → manual，Δ=manual−auto）──")
    for k, v in diff["structural"].items():
        out.append(f"  {k:<22} {v['auto']:>10} → {v['manual']:>10}  Δ={v['delta']}")
    if diff.get("semantic"):
        out.append("")
        out.append("── 语义级（回路归属与聚拢）──")
        for n in diff["semantic"]["nodes"]:
            if not n.get("loops") and n["role"] != "支路":
                continue
            moves = "; ".join(
                f"{m['loop']}:{m['dist_auto_px']}→{m['dist_manual_px']}px"
                f"({'更近' if m['closer_to_loop_center_after'] else '更远'})"
                for m in n.get("loop_moves", [])) or "-"
            out.append(f"  {n['node']:<24} [{n['role']}] {moves}")
        for lid, lp in diff["semantic"]["loops"].items():
            out.append(f"  回路 {lid}: 聚拢度 {lp['cohesion_auto']} → "
                       f"{lp['cohesion_manual']}，平均两两距离 Δ="
                       f"{lp['mean_pairwise_delta_px']}px")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="stdraw layout-diff",
        description="auto 布局 vs 手动布局三层 diff（审美采集闭环的数据源）")
    ap.add_argument("auto", help="自动布局 layout.json")
    ap.add_argument("manual", help="手动布局 layout.json（或导出的子集）")
    ap.add_argument("--cld", default=None,
                    help="图源（.cld/.json），启用语义级（回路归属/聚拢）")
    ap.add_argument("--out", default="layout-diff.json",
                    help="机器可读 JSON 输出路径（默认 ./layout-diff.json；"
                         "空串跳过写盘）")
    a = ap.parse_args(argv)

    graph = None
    if a.cld:
        from .__main__ import load_graph
        graph = load_graph(a.cld)

    auto = _load_layout(a.auto)
    manual = _load_layout(a.manual)
    d = diff_layouts(auto, manual, graph, a.auto, a.manual)
    print(_human(d))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        print(f"\n机器可读 JSON -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
