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

        # ── G. ref-scrubbed：waypoints 全链（折点把手 → 导出 → --from-layout 复算）──
        # 夹具：第三节点压直线边中点 → from-layout 产出 vg 折线（jacky 场景）
        vg_edge = None
        blocker_manual = None
        for e in lay_a["edges"]:
            if e["route"]["kind"] not in ("line", "arc"):
                continue
            fa, fb = e["a"], e["b"]
            for fc in lay_a["nodes"]:
                if fc in (fa, fb):
                    continue
                man_try = json.loads(json.dumps(ident))
                mxx = (lay_a["nodes"][fa]["x"] + lay_a["nodes"][fb]["x"]) / 2
                myy = (lay_a["nodes"][fa]["y"] + lay_a["nodes"][fb]["y"]) / 2
                man_try["nodes"][fc] = {"x": int(mxx) - int(mxx) % 2,
                                        "y": int(myy) - int(myy) % 2}
                pth = os.path.join(tmp, "wp-fixture.json")
                with open(pth, "w", encoding="utf-8") as f:
                    json.dump(man_try, f, ensure_ascii=False)
                out_try = os.path.join(tmp, "wp-fixture")
                run(["layout", EX, "--outdir", out_try, "--skip-3d",
                     "--from-layout", pth])
                lay_try = load(os.path.join(out_try, "layout.json"))
                vgs = [x for x in lay_try["edges"] if x["route"]["kind"] == "vg"]
                if vgs:
                    vg_edge = vgs[0]
                    blocker_manual = man_try
                    break
            if vg_edge:
                break
        ok("G0 vg fixture built", vg_edge is not None,
           f"{vg_edge['a']}->{vg_edge['b']}" if vg_edge else "no vg")
        if vg_edge:
            wps = [[int(round(p[0])), int(round(p[1]))]
                   for p in vg_edge["route"]["via"][1:-1]]
            blocker_manual["edges"] = [{"a": vg_edge["a"], "b": vg_edge["b"],
                                        "waypoints": wps}]
            wpth = os.path.join(tmp, "wp-manual.json")
            with open(wpth, "w", encoding="utf-8") as f:
                json.dump(blocker_manual, f, ensure_ascii=False)
            out_w1 = os.path.join(tmp, "wp1")
            out_w2 = os.path.join(tmp, "wp2")
            r_w1 = run(["layout", EX, "--outdir", out_w1, "--skip-3d",
                        "--from-layout", wpth])
            run(["layout", EX, "--outdir", out_w2, "--skip-3d",
                 "--from-layout", wpth])
            geo_w = load(os.path.join(out_w1, "geometry_report.json"))
            lay_w = load(os.path.join(out_w1, "layout.json"))
            e_w = next(x for x in lay_w["edges"]
                       if (x["a"], x["b"]) == (vg_edge["a"], vg_edge["b"]))
            ok("G1 waypoints honored (kind/via/geometry)",
               r_w1.returncode == 0 and geo_w["fail"] == 0 and
               e_w["route"]["kind"] == "waypoints" and
               e_w["route"]["via"] == [[float(q[0]), float(q[1])]
                                       for q in wps] and
               lay_w["meta"]["from_layout"].get("waypoint_edges") == 1,
               f"rc={r_w1.returncode} fail={geo_w['fail']} "
               f"kind={e_w['route']['kind']} via={e_w['route'].get('via')}")
            # 证书几何复检口径含 waypoints：route.points = 锚 + waypoints + 锚
            pts_w = e_w["route"]["points"]
            ok("G2 route.points embed waypoints (certificate caliber)",
               len(pts_w) == len(wps) + 2 and
               all(math.hypot(pts_w[k + 1][0] - wps[k][0],
                              pts_w[k + 1][1] - wps[k][1]) < 0.6
                   for k in range(len(wps))),
               f"n_pts={len(pts_w)} n_wps={len(wps)}")
            det_w = all(open(os.path.join(out_w1, fn), "rb").read() ==
                        open(os.path.join(out_w2, fn), "rb").read()
                        for fn in ("layout.json", "certificate.json",
                                   "demo-2d.html"))
            ok("G3 waypoints layout deterministic (byte-identical x2)", det_w)
            # 锚点口径：首/末点贴自家框边（borderPoint 朝向首/末 waypoint）
            ea = lay_w["nodes"][vg_edge["a"]]
            p0 = pts_w[0]
            ok("G4 anchor on a-side box border",
               abs(math.hypot(abs(abs(p0[0] - ea["x"]) - ea["w"] / 2),
                              abs(abs(p0[1] - ea["y"]) - lay_w["meta"]["cardH"] / 2))) < 0.9
               or (abs(p0[0] - ea["x"]) <= ea["w"] / 2 + 0.6 and
                   abs(abs(p0[1] - ea["y"]) - lay_w["meta"]["cardH"] / 2) < 0.6) or
               (abs(p0[1] - ea["y"]) <= lay_w["meta"]["cardH"] / 2 + 0.6 and
                abs(abs(p0[0] - ea["x"]) - ea["w"] / 2) < 0.6),
               f"p0={p0} a={ea}")
            # layout-diff 对 waypoints 布局可用（全链第三层）
            dpath_w = os.path.join(tmp, "wp-diff.json")
            r_dw = run(["layout-diff", os.path.join(out_auto, "layout.json"),
                        os.path.join(out_w1, "layout.json"),
                        "--cld", EX, "--diff-out", dpath_w])
            ok("G5 layout-diff accepts waypoints layout", r_dw.returncode == 0,
               r_dw.stderr[-120:])

        # H. ref-scrubbed：waypoints 诚实报错（未知边/坏格式 → exit 2）
        bad1 = json.loads(json.dumps(ident))
        bad1["edges"] = [{"a": "nope", "b": "nada", "waypoints": [[1, 2]]}]
        bp1 = os.path.join(tmp, "wp-bad1.json")
        with open(bp1, "w", encoding="utf-8") as f:
            json.dump(bad1, f, ensure_ascii=False)
        rc_b1 = run(["layout", EX, "--outdir", os.path.join(tmp, "wpbad1"),
                     "--skip-3d", "--from-layout", bp1])
        ok("H1 unknown edge in waypoints → exit 2",
           rc_b1.returncode == 2 and "不存在" in (rc_b1.stderr + rc_b1.stdout),
           rc_b1.stderr[-120:])
        bad2 = json.loads(json.dumps(ident))
        bad2["edges"] = [{"a": lay_a["edges"][0]["a"],
                          "b": lay_a["edges"][0]["b"],
                          "waypoints": [["x", "y"]]}]
        bp2 = os.path.join(tmp, "wp-bad2.json")
        with open(bp2, "w", encoding="utf-8") as f:
            json.dump(bad2, f, ensure_ascii=False)
        rc_b2 = run(["layout", EX, "--outdir", os.path.join(tmp, "wpbad2"),
                     "--skip-3d", "--from-layout", bp2])
        ok("H2 non-numeric waypoint → exit 2",
           rc_b2.returncode == 2 and "非数值" in (rc_b2.stderr + rc_b2.stdout),
           rc_b2.stderr[-120:])
        # 无 edges 字段 = 原行为（A1 已覆盖恒等；此处验证缺省不受影响）
        rc_ne = run(["layout", EX, "--outdir", os.path.join(tmp, "wp-noedge"),
                     "--skip-3d", "--from-layout", ip])
        ok("H3 manual without edges key unchanged (rc=0)", rc_ne.returncode == 0,
           rc_ne.stderr[-100:])

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
