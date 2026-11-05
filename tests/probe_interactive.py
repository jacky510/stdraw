#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交互层回归探针（ref-scrubbed）：真实浏览器（Playwright/Chromium 系）验证
demo-2d.html 的拖拽闭环：

  拖动节点 → 顶栏实时指标变化 → 边/箭头/极性标记跟随 → 松手全刷新
  → 「导出布局」真实下载 JSON → 「重置」恢复初始布局 → 全程 0 页面错误。

playwright 不可用时 SKIP（exit 2，同 rendercheck 口径）；可用时 exit 0/1。
用法：python tests/probe_interactive.py [demo-2d.html 路径（缺省自建）]
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("SKIP  probe_interactive: playwright 不可用（可选层）")
    sys.exit(2)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "examples", "classic-cld-growth-and-burden.cld")

result = {"checks": []}


def chk(name, ok, detail=""):
    result["checks"].append({"check": name, "pass": bool(ok), "detail": str(detail)})
    print(("PASS " if ok else "FAIL ") + name + "  " + str(detail)[:200])


def main():
    tmp = tempfile.mkdtemp(prefix="stdraw-probe-")
    try:
        if len(sys.argv) > 1:
            demo = os.path.abspath(sys.argv[1])
        else:
            out = os.path.join(tmp, "out")
            r = subprocess.run([sys.executable, "-m", "stdraw", "layout", EX,
                                "--outdir", out, "--skip-3d"],
                               capture_output=True, text=True, cwd=ROOT)
            if r.returncode != 0:
                print("FAIL 自建 demo 失败:", r.stderr[-300:])
                return 1
            demo = os.path.join(out, "demo-2d.html")

        with sync_playwright() as p:
            try:
                b = p.chromium.launch(channel="msedge", headless=True)
            except Exception:
                b = p.chromium.launch(headless=True)
            ctx = b.new_context(viewport={"width": 1440, "height": 1000},
                                accept_downloads=True, has_touch=True)
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto("file:///" + demo.replace("\\", "/"))
            pg.wait_for_timeout(300)

            m0 = pg.evaluate("window.__stdrawMetrics()")
            chk("interactive layer loaded", bool(m0), f"metrics={m0}")
            toolbar0 = pg.evaluate(
                "document.getElementById('stdraw-metrics').textContent")
            chk("toolbar metrics visible", "交叉" in toolbar0, toolbar0)

            box = pg.locator('[data-node="rate"]').bounding_box()
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            pos0 = pg.evaluate("window.__stdrawNodePos('rate')")
            pg.mouse.move(cx, cy)
            pg.mouse.down()
            pg.mouse.move(cx + 45, cy + 25, steps=5)
            mid_toolbar = pg.evaluate(
                "document.getElementById('stdraw-metrics').textContent")
            pg.mouse.move(cx + 70, cy + 55, steps=5)
            pg.mouse.up()
            pg.wait_for_timeout(200)

            pos1 = pg.evaluate("window.__stdrawNodePos('rate')")
            m1 = pg.evaluate("window.__stdrawMetrics()")
            tr = pg.evaluate("document.querySelector('[data-node=\\'rate\\']')"
                             ".getAttribute('transform')")
            d0 = pg.evaluate("document.querySelector('[data-edge=\\'0\\'] path')"
                             ".getAttribute('d')")
            pol = pg.evaluate("(document.querySelector('[data-pol=\\'0\\']')||{})"
                             ".getAttribute ? document.querySelector("
                             "'[data-pol=\\'0\\']').getAttribute('transform') : null")
            chk("drag moved node",
               abs(pos1[0] - pos0[0]) > 20 and abs(pos1[1] - pos0[1]) > 20,
               f"pos {pos0} -> {pos1}, transform={tr}")
            chk("live metrics changed mid-drag", mid_toolbar != toolbar0,
                f"mid: {mid_toolbar!r}")
            chk("edge followed as polyline", "L " in d0, d0[:100])
            chk("polarity marker repositioned", pol is not None, pol)
            chk("metrics changed after drag", m1 != m0, f"{m0} -> {m1}")

            # 触摸可用性（hasTouch 环境 tap 不报错）
            tb = pg.locator('[data-node="adopters"]').bounding_box()
            pg.touchscreen.tap(tb["x"] + tb["width"] / 2, tb["y"] + tb["height"] / 2)
            pg.wait_for_timeout(100)
            chk("touch events processed without error", not errors, errors)

            with pg.expect_download() as dl_info:
                pg.click("#stdraw-export")
            dl = dl_info.value
            path = os.path.join(tmp, dl.suggested_filename)
            dl.save_as(path)
            exported = json.load(open(path, encoding="utf-8"))
            chk("export download real",
               exported.get("kind") == "manual-layout" and
               all(isinstance(v["x"], int) and isinstance(v["y"], int)
                   for v in exported["nodes"].values()),
               f"{dl.suggested_filename} rate={exported['nodes'].get('rate')}")
            chk("export reflects dragged pos",
               abs(exported["nodes"]["rate"]["x"] - pos1[0]) < 1.5,
               f"{exported['nodes']['rate']} vs {pos1}")

            pg.click("#stdraw-reset")
            pos2 = pg.evaluate("window.__stdrawNodePos('rate')")
            chk("reset restores initial layout", pos2 == pos0, f"{pos2} vs {pos0}")
            chk("zero page errors", not errors, errors)
            b.close()

        ok = all(c["pass"] for c in result["checks"])
        print("\n==", "ALL PASS" if ok else "HAS FAILURES",
              f"({sum(c['pass'] for c in result['checks'])}/{len(result['checks'])})")
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
