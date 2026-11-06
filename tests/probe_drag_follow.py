#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拖拽跟随扫掠探针（ref-scrubbed 验收）：无头 CDP 真拖逐图复现 jacky 实测场景。

数据源（优先级）：
  1. <user-home>/Downloads/stdraw-manual/ 的 19 张 jacky 手动布局
     （layout.json 节点坐标经 --from-layout 在 HEAD 重渲染，交互层=本卡新版）；
  2. 缺省回退 benchmarks/corpus/classic/ 19 张自动布局。

每图断言（真实 pointer 事件，非 JS 直调）：
  A. 逐节点拖动：每步对全部非弧折线边做「Python 独立复算预览布线」对拍
     （直线可见→直线；被挡→膨胀角点可见性图最短路+捷径，c=16/17.5 同口径），
     证明折点逐帧重算而非钉死（jacky 问题 2 的回归门）；
  B. 强制 vg 场景：拖第三节点压到某直线边中点 → 该边变折线（预览绕障）且
     与复算一致；继续拖走 → 仍一致（旧绕行不作废残留）；
  C. 全程 0 页面错误。

playwright 不可用 → SKIP exit 2。用法：
  python tests/probe_drag_follow.py [图名过滤子串]
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP  probe_drag_follow: playwright 不可用（可选层）")
    sys.exit(2)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
# jacky 手动布局导出目录（本机验收源）；缺省/不存在时回退 corpus 自动布局。
# 用环境变量注入，避免把机器特定路径写死进仓：STDRAW_MANUAL_SWEEP_DIR=...
MANUAL_DIR = os.environ.get("STDRAW_MANUAL_SWEEP_DIR", "")


def _expected_preview_route(nodes_px, a, b):
    from stdraw.routing import border_point
    from stdraw.visibility import seg_rect_distance, shortest_path, _shortcut
    A, B = nodes_px[a], nodes_px[b]
    pa = border_point(A[0], A[1], A[2], A[3], B[0] - A[0], B[1] - A[1])
    pb = border_point(B[0], B[1], B[2], B[3], A[0] - B[0], A[1] - B[1])
    rects = [tuple(nodes_px[v]) for v in nodes_px if v not in (a, b)]
    if not rects or all(seg_rect_distance(pa, pb, r) >= 16 - 1e-6 for r in rects):
        return [list(pa), list(pb)]
    path = shortest_path(tuple(pa), tuple(pb), rects, 17.5)
    if path is None:
        return None
    return [list(p) for p in _shortcut(path, rects, 17.5)]


def _match(js_pts, expect, tol=0.6):
    if expect is None or len(js_pts) != len(expect):
        return False
    return all(math.hypot(p[0] - q[0], p[1] - q[1]) <= tol
               for p, q in zip(js_pts, expect))


def _fallback_keeps_shape(js_pts, prev_pts, tol=0.6):
    """expected 不可达（None）时的诚实兜底口径：JS 保形重锚——折点与上一帧
    一致（端点重锚可动）。prev_pts=None（首帧/初始 CLI 几何）时不判。"""
    if not prev_pts or len(js_pts) != len(prev_pts):
        return False
    return all(math.hypot(p[0] - q[0], p[1] - q[1]) <= tol
               for p, q in zip(js_pts[1:-1], prev_pts[1:-1]))


def _nodes_px(pg, lay):
    pos = {r[0]: (r[1], r[2]) for r in pg.evaluate("window.__stdrawNodePos()")}
    ch = lay["meta"]["cardH"]
    return {v: (p[0], p[1], lay["nodes"][v]["w"] / 2.0, ch / 2.0)
            for v, p in pos.items()}


def _center(pg, vid):
    loc = pg.locator(f'[data-node="{vid}"]')
    loc.scroll_into_view_if_needed()
    bb = loc.bounding_box()
    return bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2


def _to_screen(pg, vx, vy):
    return pg.evaluate(
        "([vx,vy]) => { const s=document.getElementById('stdraw-svg');"
        " const r=s.getBoundingClientRect(); const VB=s.viewBox.baseVal;"
        " return [r.x+(vx-VB.x)/VB.width*r.width, r.y+(vy-VB.y)/VB.height*r.height]; }",
        [vx, vy])


def _check_all_edges(pg, lay, payload, tag, failures, prev=None, fallbacks=None,
                    drag_node=None):
    """prev: {edge_idx: 上一帧 pts}（兜底口径判定用）；fallbacks: 计数表。

    断言范围 = 拖拽承诺面：①被拖节点的关联边（每帧无条件重布线）；
    ②当前折线形边（障碍变化即重算，含 dense vg/poly 基线）。非关联的
    两点直线（CLI 锚变体/未触发）不在「实时跟随」承诺内，跳过。
    """
    npx = _nodes_px(pg, lay)
    allpts = pg.evaluate("window.__stdrawEdgePts()")
    for i, e in enumerate(payload["edges"]):
        if e.get("arc"):
            continue
        incident = drag_node is not None and drag_node in (e["a"], e["b"])
        poly = len(allpts[i]) > 2
        if not (incident or poly):
            continue
        ex = _expected_preview_route(npx, e["a"], e["b"])
        if ex is not None:
            ok = _match(allpts[i], ex)
        else:
            # 可见性图不可达：诚实兜底=保形重锚（或初始 CLI 几何）
            ok = (prev is None) or _fallback_keeps_shape(allpts[i], prev.get(i))
            if ok and fallbacks is not None:
                fallbacks[i] = fallbacks.get(i, 0) + 1
        if not ok:
            failures.append(f"{tag}: edge {e['a']}->{e['b']} 不随拖重算 "
                            f"(n={len(allpts[i])} expect_n="
                            f"{len(ex) if ex else 'unreachable'})")
            return False, allpts
    return True, allpts


def sweep_graph(browser, src_dir, tmp, filt):
    name = os.path.basename(src_dir.rstrip("/\\"))
    if filt and filt not in name:
        return None
    lay_src = os.path.join(src_dir, "layout.json")
    cld = os.path.join(src_dir, "graph.cld")
    with open(lay_src, encoding="utf-8") as f:
        lay0 = json.load(f)
    manual = {"viewBox": lay0["viewBox"],
              "nodes": {v: {"x": p["x"], "y": p["y"]}
                        for v, p in lay0["nodes"].items()}}
    mp = os.path.join(tmp, name + "-manual.json")
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(manual, f, ensure_ascii=False)
    out = os.path.join(tmp, name)
    r = subprocess.run([PY, "-m", "stdraw", "layout", cld, "--outdir", out,
                        "--skip-3d", "--from-layout", mp],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ROOT)
    if r.returncode not in (0, 1):
        return (name, False, f"CLI exit {r.returncode}: {r.stderr[-200:]}")
    with open(os.path.join(out, "layout.json"), encoding="utf-8") as f:
        lay = json.load(f)
    demo = os.path.join(out, "demo-2d.html")
    payload = json.loads(open(demo, encoding="utf-8").read()
                         .split('<script id="stdraw-data" type="application/json">')[1]
                         .split("</script>")[0].replace("<\\/", "</"))
    failures = []
    ctx = browser.new_context(viewport={"width": 1600, "height": 1500})
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("file://" + demo.replace("\\", "/"))
    pg.wait_for_timeout(300)

    # A. 逐节点拖动（每节点独立：拖完 reset）
    dragged = 0
    fallbacks = {}
    for v in [n["id"] for n in payload["nodes"]]:
        cx, cy = _center(pg, v)
        pg.mouse.move(cx, cy)
        pg.mouse.down()
        ok = True
        prev = None          # 首帧 prev=None：接受初始 CLI 几何/首算结果
        for k in range(1, 4):
            pg.mouse.move(cx + 14 * k, cy + 9 * k, steps=1)
            pg.wait_for_timeout(40)
            ok, prev = _check_all_edges(pg, lay, payload, f"drag {v} step{k}",
                                        failures, prev, fallbacks, drag_node=v)
            if not ok:
                break
        pg.mouse.up()
        pg.wait_for_timeout(80)
        if ok:
            dragged += 1
        pg.click("#stdraw-reset")
        pg.wait_for_timeout(80)
        if failures:
            break

    # B. 强制 vg：第三节点压直线边中点 → 折线出现且对拍 → 拖走仍对拍。
    # 先在 Python 侧预检（c 压中点后的预期路线为折线）选出可行组合，避免
    # 把「可见性图不可达→诚实保持直线」误判为失败。
    vg_forced = None
    if not failures:
        straight = [e for e in payload["edges"]
                    if not e.get("arc") and len(e["pts"]) == 2]
        picked = None
        for e in straight:
            a, b = e["a"], e["b"]
            na = next(n for n in payload["nodes"] if n["id"] == a)
            nb = next(n for n in payload["nodes"] if n["id"] == b)
            mx = (na["x"] + nb["x"]) / 2
            my = (na["y"] + nb["y"]) / 2
            for c in [n["id"] for n in payload["nodes"] if n["id"] not in (a, b)]:
                npx_try = {n["id"]: (n["x"], n["y"], lay["nodes"][n["id"]]["w"] / 2.0,
                                     lay["meta"]["cardH"] / 2.0)
                           for n in payload["nodes"]}
                npx_try[c] = (mx, my, npx_try[c][2], npx_try[c][3])
                ex_try = _expected_preview_route(npx_try, a, b)
                if ex_try and len(ex_try) > 2:
                    picked = (e, a, b, c, mx, my)
                    break
            if picked:
                break
        if picked:
            e, a, b, c, mx, my = picked
            sx, sy = _to_screen(pg, mx, my)
            if 0 < sx < 1600 and 0 < sy < 1500:
                ccx, ccy = _center(pg, c)
                pg.mouse.move(ccx, ccy)
                pg.mouse.down()
                pg.mouse.move(sx, sy, steps=3)
                pg.wait_for_timeout(60)
                ei = payload["edges"].index(e)
                pts = pg.evaluate(f"window.__stdrawEdgePts({ei})")
                npx = _nodes_px(pg, lay)
                ex = _expected_preview_route(npx, a, b)
                became_poly = len(pts) > 2 and _match(pts, ex)
                pg.mouse.move(sx + 30, sy - 22, steps=2)
                pg.wait_for_timeout(60)
                pts2 = pg.evaluate(f"window.__stdrawEdgePts({ei})")
                npx = _nodes_px(pg, lay)
                ex2 = _expected_preview_route(npx, a, b)
                # 不可达时接受诚实兜底（保形重锚：折点与压线帧一致）
                still = (_match(pts2, ex2) if ex2 is not None
                         else _fallback_keeps_shape(pts2, pts))
                pg.mouse.up()
                pg.wait_for_timeout(80)
                vg_forced = (a, b, c, became_poly, still,
                             len(pts), len(pts2))
                if not became_poly:
                    failures.append(f"force-vg: {a}->{b} 压线后未成折线 "
                                    f"(n={len(pts)} expect_n="
                                    f"{len(ex) if ex else '?'})")
                if not still:
                    failures.append(f"force-vg: {a}->{b} 拖走后未重算 (n2={len(pts2)})")
            else:
                vg_forced = ("屏幕坐标越界，跳过该组合",)
        else:
            vg_forced = ("无可行压线组合（全部不可达/无直线边）",)
        pg.click("#stdraw-reset")
        pg.wait_for_timeout(80)

    if errors:
        failures.append(f"page errors: {errors[:2]}")
    ctx.close()
    return (name, not failures,
            f"dragged {dragged}/{len(payload['nodes'])} nodes, "
            f"force-vg {vg_forced}" + ("; " + "; ".join(failures[:2])
                                       if failures else ""))


def main():
    filt = sys.argv[1] if len(sys.argv) > 1 else ""
    if os.path.isdir(MANUAL_DIR):
        srcs = sorted(os.path.join(MANUAL_DIR, d)
                      for d in os.listdir(MANUAL_DIR)
                      if os.path.isdir(os.path.join(MANUAL_DIR, d))
                      and os.path.exists(os.path.join(MANUAL_DIR, d, "layout.json")))
        src_label = f"jacky 手动布局 {MANUAL_DIR}"
    else:
        import glob
        srcs = sorted(glob.glob(os.path.join(ROOT, "benchmarks/corpus/classic/*.cld")))
        src_label = "corpus 自动布局"
    tmp = tempfile.mkdtemp(prefix="stdraw-sweep-")
    passed = failed = skipped = 0
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(channel="msedge", headless=True)
            except Exception:
                browser = p.chromium.launch(headless=True)
            print(f"== 拖拽跟随扫掠（{src_label}，共 {len(srcs)} 张）==")
            for src in srcs:
                if not src.endswith(".cld"):
                    res = sweep_graph(browser, src, tmp, filt)
                else:  # corpus 回退：包一层（用自动渲染目录）
                    out = os.path.join(tmp, "auto-" + os.path.basename(src)[:-4])
                    subprocess.run([PY, "-m", "stdraw", "layout", src,
                                    "--outdir", out, "--skip-3d"],
                                   capture_output=True, cwd=ROOT)
                    res = sweep_graph(browser, out, tmp, filt)
                if res is None:
                    skipped += 1
                    continue
                name, ok, detail = res
                print(("PASS " if ok else "FAIL ") + name + "  " + detail)
                if ok:
                    passed += 1
                else:
                    failed += 1
            browser.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n== {passed} PASS / {failed} FAIL / {skipped} skipped ==")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
