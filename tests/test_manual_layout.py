#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手动布局闭环回归（ref-scrubbed）：

A. 恒等手动布局：auto 坐标原样喂回 --from-layout → 几何 fail=0、
   layout.json 的 viewBox/nodes 与 auto 逐键一致（同管线不变量）；
B. 扰动手动布局：engine=manual + from_layout 元数据 + 坐标 snap 到 2px +
   退出码语义（rc==1 ⇔ geometry fail>0，--compare-auto 时先出对照再退）；
C. 浏览器导出子集格式（{x,y} 与 [x,y] 两种）与 id 集不一致 → exit 2；
D. layout-diff（debt-spiral 假想手动布局）：三层齐备 + 数字可复核
   （|d| 与回路聚拢度在测试内独立重算对拍）；
E. 确定性：--from-layout 两跑逐字节一致；demo-2d.html 含交互层。

Stdlib only。
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "examples", "classic-cld-growth-and-burden.cld")
DEBT = os.path.join(ROOT, "benchmarks", "corpus", "classic", "debt-spiral.cld")

failures = []


def ok(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("  " + str(detail)[:180] if detail else ""))
    if not cond:
        failures.append(name)


def run(args):
    return subprocess.run([sys.executable, "-m", "stdraw"] + args,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=ROOT)


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    tmp = tempfile.mkdtemp(prefix="stdraw-manual-")
    try:
        # ── 基线 auto ──
        out_auto = os.path.join(tmp, "auto")
        r = run(["layout", EX, "--outdir", out_auto, "--skip-3d"])
        ok("A0 auto baseline rc=0", r.returncode == 0, r.stderr[-200:])
        lay_a = load(os.path.join(out_auto, "layout.json"))

        # A. 恒等手动布局
        ident = {"tool": "stdraw", "kind": "manual-layout", "graph": "x",
                 "viewBox": lay_a["viewBox"],
                 "nodes": {v: {"x": p["x"], "y": p["y"]}
                           for v, p in lay_a["nodes"].items()}}
        ip = os.path.join(tmp, "ident.json")
        with open(ip, "w", encoding="utf-8") as f:
            json.dump(ident, f, ensure_ascii=False)
        out_i1 = os.path.join(tmp, "ident1")
        out_i2 = os.path.join(tmp, "ident2")
        r1 = run(["layout", EX, "--outdir", out_i1, "--skip-3d", "--from-layout", ip])
        run(["layout", EX, "--outdir", out_i2, "--skip-3d", "--from-layout", ip])
        geo_i = load(os.path.join(out_i1, "geometry_report.json"))
        lay_i = load(os.path.join(out_i1, "layout.json"))
        ok("A1 identical manual rc=0 & geometry fail=0",
           r1.returncode == 0 and geo_i["fail"] == 0,
           f"rc={r1.returncode} fail={geo_i['fail']}")
        ok("A2 identical manual reproduces auto nodes/viewBox",
           lay_i["nodes"] == lay_a["nodes"] and lay_i["viewBox"] == lay_a["viewBox"])
        ok("A3 meta manual + from_layout",
           lay_i["meta"]["position_engine"] == "manual" and
           lay_i["meta"]["from_layout"]["source"] == "ident.json")
        # E. 确定性（两跑逐字节）
        det = all(open(os.path.join(out_i1, fn), "rb").read() ==
                  open(os.path.join(out_i2, fn), "rb").read()
                  for fn in ("layout.json", "certificate.json", "demo-2d.html"))
        ok("E1 from-layout deterministic (byte-identical x2)", det)
        html = open(os.path.join(out_i1, "demo-2d.html"), encoding="utf-8").read()
        ok("E2 demo interactive layer present",
           all(s in html for s in ('id="stdraw-svg"', "data-node=",
                                   "stdraw-export", "__stdrawExportLayout")))

        # B. 扰动手动布局（浏览器拖拽形态：挪一个节点 +30x）
        first = list(lay_a["nodes"])[0]
        pert = json.loads(json.dumps(ident))
        pert["nodes"][first]["x"] += 30
        pp = os.path.join(tmp, "pert.json")
        with open(pp, "w", encoding="utf-8") as f:
            json.dump(pert, f, ensure_ascii=False)
        out_p = os.path.join(tmp, "pert")
        r2 = run(["layout", EX, "--outdir", out_p, "--skip-3d",
                  "--from-layout", pp, "--compare-auto"])
        lay_p = load(os.path.join(out_p, "layout.json"))
        geo_p = load(os.path.join(out_p, "geometry_report.json"))
        ok("B1 perturbed manual honest exit semantics",
           r2.returncode in (0, 1) and (r2.returncode == 1) == (geo_p["fail"] > 0),
           f"rc={r2.returncode} fail={geo_p['fail']}")
        ok("B2 perturbed coordinate applied (snapped 2px)",
           lay_p["nodes"][first]["x"] == lay_a["nodes"][first]["x"] + 30)
        # B3：compare-auto 产物（Windows/AV 下偶发目录可见性延迟，重试 3×1s）
        import time
        cmp_path = os.path.join(out_p, "compare-auto.json")
        cmp_dir2 = os.path.join(tmp, "pert-compare-auto")
        for _ in range(3):
            if os.path.exists(cmp_path) and \
               os.path.exists(os.path.join(cmp_dir2, "certificate.json")):
                break
            time.sleep(1.0)
        ok("B3 compare-auto artifacts",
           os.path.exists(cmp_path) and
           os.path.exists(os.path.join(cmp_dir2, "certificate.json")),
           "stdout_tail=" + " | ".join(r2.stdout.strip().splitlines()[-6:]))
        cmpj = load(cmp_path)
        ok("B4 compare table has both columns",
           set(cmpj["metrics"]["crossings"].keys()) ==
           {"manual", "auto", "delta_manual_minus_auto"})

        # C. 子集格式：[x,y] 数组也接受；id 不一致 exit 2
        arr = {"viewBox": lay_a["viewBox"],
               "nodes": {v: [p["x"], p["y"]] for v, p in lay_a["nodes"].items()}}
        ap_ = os.path.join(tmp, "arr.json")
        with open(ap_, "w", encoding="utf-8") as f:
            json.dump(arr, f, ensure_ascii=False)
        out_c = os.path.join(tmp, "arr")
        rc_ = run(["layout", EX, "--outdir", out_c, "--skip-3d", "--from-layout", ap_])
        ok("C1 [x,y] array subset accepted", rc_.returncode == 0, rc_.stderr[-150:])
        bad = {"viewBox": [0, 0, 100, 100], "nodes": {"nope": {"x": 1, "y": 2}}}
        bp = os.path.join(tmp, "bad.json")
        with open(bp, "w", encoding="utf-8") as f:
            json.dump(bad, f)
        rc2 = run(["layout", EX, "--outdir", os.path.join(tmp, "bad"),
                   "--skip-3d", "--from-layout", bp])
        ok("C2 id-set mismatch → exit 2 with honest error",
           rc2.returncode == 2 and "不一致" in (rc2.stderr + rc2.stdout),
           rc2.stderr[-150:])

        # D. layout-diff：debt-spiral 假想手动布局（debt 往 R1 环心收 20px）
        out_da = os.path.join(tmp, "debt-auto")
        run(["layout", DEBT, "--outdir", out_da, "--skip-3d"])
        lay_d = load(os.path.join(out_da, "layout.json"))
        # 假想手动：把 debt 拉向 R1 环心（debt/interest/deficit）
        peers = ["interest", "deficit"]
        cx = (lay_d["nodes"]["debt"]["x"] +
              sum(lay_d["nodes"][q]["x"] for q in peers)) / 3
        cy = (lay_d["nodes"]["debt"]["y"] +
              sum(lay_d["nodes"][q]["y"] for q in peers)) / 3
        manual_d = json.loads(json.dumps(
            {"viewBox": lay_d["viewBox"],
             "nodes": {v: {"x": p["x"], "y": p["y"]}
                       for v, p in lay_d["nodes"].items()}}))
        dx, dy = cx - lay_d["nodes"]["debt"]["x"], cy - lay_d["nodes"]["debt"]["y"]
        nrm = math.hypot(dx, dy) or 1.0
        manual_d["nodes"]["debt"]["x"] = int(round(lay_d["nodes"]["debt"]["x"] + dx / nrm * 20))
        manual_d["nodes"]["debt"]["y"] = int(round(lay_d["nodes"]["debt"]["y"] + dy / nrm * 20))
        md = os.path.join(tmp, "debt-manual-layout.json")
        with open(md, "w", encoding="utf-8") as f:
            json.dump(manual_d, f, ensure_ascii=False)
        out_dm = os.path.join(tmp, "debt-manual")
        run(["layout", DEBT, "--outdir", out_dm, "--skip-3d", "--from-layout", md])
        dpath = os.path.join(tmp, "debt-diff.json")
        r3 = run(["layout-diff", os.path.join(out_da, "layout.json"),
                  os.path.join(out_dm, "layout.json"),
                  "--cld", DEBT, "--diff-out", dpath])
        ok("D0 layout-diff rc=0", r3.returncode == 0, r3.stderr[-200:])
        d = load(dpath)
        ok("D1 three layers present",
           d.get("node_level") and d.get("structural") and d.get("semantic"))
        # 数字可复核：debt 的位移 = 两份 layout.json 坐标差（测试内独立重算）
        lay_dm = load(os.path.join(out_dm, "layout.json"))
        want_dx = (lay_dm["nodes"]["debt"]["x"] -
                   lay_d["nodes"]["debt"]["x"])
        want_dy = (lay_dm["nodes"]["debt"]["y"] -
                   lay_d["nodes"]["debt"]["y"])
        it = next(n for n in d["node_level"] if n["node"] == "debt")
        ok("D2 debt displacement reproducible",
           it["dx"] == want_dx and it["dy"] == want_dy and
           abs(it["|d|"] - math.hypot(want_dx, want_dy)) < 0.1,
           f"dx={it['dx']} dy={it['dy']} tags={it['tags']}")
        ok("D3 debt tagged toward-loop-center",
           any("往环心收" in t for t in it["tags"]), it["tags"])
        # 结构级七指标两列 + Δ 全为数值
        ok("D4 structural 7 metrics numeric",
           len(d["structural"]) == 7 and all(
               isinstance(v["auto"], (int, float)) and
               isinstance(v["manual"], (int, float))
               for v in d["structural"].values()), list(d["structural"]))
        # 语义级：debt 属 R1/R2 环上；R1 聚拢度测试内独立重算对拍
        sem_debt = next(n for n in d["semantic"]["nodes"] if n["node"] == "debt")
        ok("D5 debt role 环上 with loops",
           sem_debt["role"] == "环上" and set(sem_debt["loops"]) == {"R1", "R2"})

        def cohesion(lay, members):
            ps = [(lay["nodes"][v]["x"], lay["nodes"][v]["y"]) for v in members]
            ds = [math.dist(a, b) for i, a in enumerate(ps) for b in ps[i + 1:]]
            dia = max(ds)
            return (sum(ds) / len(ds)) / dia if dia else None

        ok("D6 R1/R2 cohesion reproducible",
           abs(d["semantic"]["loops"]["R1"]["cohesion_manual"] -
               cohesion(lay_dm, ["debt", "interest", "deficit"])) < 0.002 and
           abs(d["semantic"]["loops"]["R2"]["cohesion_manual"] -
               cohesion(lay_dm, ["debt", "credit", "rate", "interest", "deficit"])) < 0.002,
           d["semantic"]["loops"])

        print()
        if failures:
            print("FAILURES:", failures)
            return 1
        print("All manual-layout regression checks passed.")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
