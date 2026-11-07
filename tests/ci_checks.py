#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CI checks（2026-11-05 六点返修版）。

三层断言：
  A. ortho-v1 冻结配方回归（生产行为 pin 保护）：
     - 两案例 exit 0，11 项几何自检 fail==0；
     - layout.json 与 tests/baselines/ 逐字节一致（planar.py 行为冻结铁门）；
     - legacy 证书 crossings==0 / grade==最优；loops problems==0；
     - 同输入两次运行逐字节一致（确定性）。
  B. auto-v2 默认配方（产品主路径）新硬门：
     - 框压线=0、边-框净距≥16px、锚点平滑、卡净距≥16、CV≤0.35、简单图规律性
       全部 pass；
     - crossings ≤ 2 且 grade ∈ {最优, 其次}（诚实分级，不冒充 0 交叉）；
     - loops problems==0；确定性两次运行逐字节一致。
  C. DOM 实测框界（① CI 侧第二层，可选）：
     - playwright 可用时逐卡量 demo-2d.html 文字实际宽度 vs 规划框界；
     - 不可用时如实 SKIP（不算通过也不算失败，由 workflow 安装可选层兜底）。

Stdlib only（C 层可选依赖 playwright）。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

EXAMPLES = [
    "examples/limits-to-growth.cld",
    "examples/classic-cld-growth-and-burden.cld",
]
# B 层（auto-v2）补盲（F3 返修 ref-scrubbed）：原 B 层只跑 EXAMPLES 两例，
# bullwhip 的弧线鼓出 viewBox（check7 fail）漏检。独立列表，不与 A 层
# ortho 冻结 pin（逐字节基线）共用，避免 ortho 基线连锁。
AUTO_EXAMPLES = EXAMPLES + [
    "benchmarks/corpus/classic/bullwhip.cld",
]
# B2 层（WS3-Q 布线质量返修 ref-scrubbed）：随机稠密图抽样——random n10 固定
# 种子语料中曾 4/10 例 check1 交叉>2 / check3 净距不足（d483639 存量）。门控
# (行,序) 重排 + 联合重定线 + stair 候选池修复后，这 4 例必须保持 exit 0。
# 运行较慢（门控重排+hard-gate polish，每例 ~2min），与 B 层分开成层。
RANDOM_SAMPLES = [
    "benchmarks/corpus/random/random-n10-i00.cld",
    "benchmarks/corpus/random/random-n10-i01.cld",
    "benchmarks/corpus/random/random-n10-i04.cld",
    "benchmarks/corpus/random/random-n10-i05.cld",
]
HARD_GATES = ("box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
              "min_gap_ge_16", "cv_le_035", "pitch_uniform",
              "column_snap24_ge_060",
              "mutual_pairs_separated", "lines_no_coincidence")
# ref-scrubbed 环形排布（placement=ring-cycle）：规律性门切换为环口径
# （行对齐/列吸附对环形不适用，不得拿行口径误判环形不合格）
RING_HARD_GATES = ("box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
                   "min_gap_ge_16", "ring_spacing_cv_le_005",
                   "ring_template_fit_le_005", "mutual_pairs_separated",
                   "lines_no_coincidence")
# ref-scrubbed 纵列/对称排布：规律性门按模式切换（主链列轴对齐 + 行距恒等 /
# 镜像轴误差）。交叉（crossings_zero）与行对齐（row_align_ge_060）已降为
# 报告项（jacky 2026-11-05 定调：部分线相交可接受，秩序与优美优先）。
COLUMN_HARD_GATES = ("box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
                     "min_gap_ge_16", "cv_le_035", "column_axis_aligned",
                     "spine_pitch_uniform", "mutual_pairs_separated",
                     "lines_no_coincidence")
SYM_HARD_GATES = ("box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
                  "min_gap_ge_16", "cv_le_035", "symmetry_mirror_le_2px",
                  "mutual_pairs_separated", "lines_no_coincidence")
# ref-scrubbed（美学 v3）领结共点：规律性门 = 镜像轴误差（同 symmetric 口径）
BOWTIE_HARD_GATES = SYM_HARD_GATES
# ref-scrubbed（v0.7.1）纵柱+翼位：纵柱 x 对齐 + 中线贴靠 + 镜像（等价门）
SPINE_WING_HARD_GATES = ("box_press_zero", "edge_box_clear_ge_16",
                         "anchors_smooth", "min_gap_ge_16", "cv_le_035",
                         "spine_axis_le_2px", "midline_adherence_le_2px",
                         "symmetry_mirror_le_2px", "mutual_pairs_separated",
                         "lines_no_coincidence")


def _hard_gates_for(cert):
    p = cert.get("placement")
    if p == "ring-cycle":
        return RING_HARD_GATES
    if p == "column-chain":
        return COLUMN_HARD_GATES
    if p == "spine-wing":
        return SPINE_WING_HARD_GATES
    if p in ("symmetric", "bowtie-vertex"):
        return SYM_HARD_GATES
    return HARD_GATES


def run_cli(path, outdir, extra=(), pitch="62"):
    # ortho 用 --pitch 62 过净距门禁（legacy 调参）；auto 有自调 pitch=80，不传（pitch=None）
    cmd = [sys.executable, "-m", "stdraw", "layout", path, "--outdir", outdir]
    if pitch:
        cmd += ["--pitch", pitch]
    cmd += list(extra)
    return subprocess.run(cmd, capture_output=True, text=True)


def load(outdir, name):
    with open(os.path.join(outdir, name), encoding="utf-8") as f:
        return json.load(f)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
    failures = []
    tmp = tempfile.mkdtemp(prefix="stdraw-ci-")
    try:
        # ── A. ortho-v1 冻结回归（生产行为 pin）──
        for ex in EXAMPLES:
            name = os.path.splitext(os.path.basename(ex))[0]
            out1 = os.path.join(tmp, name + "-ortho-1")
            out2 = os.path.join(tmp, name + "-ortho-2")
            r1 = run_cli(ex, out1, ("--recipe", "ortho"))
            if r1.returncode != 0:
                failures.append(f"ortho {ex}: CLI exit {r1.returncode}\n{r1.stderr}")
                continue
            run_cli(ex, out2, ("--recipe", "ortho"))
            geo = load(out1, "geometry_report.json")
            if geo.get("fail", 0) != 0:
                failures.append(f"ortho {ex}: geometry fail={geo['fail']}")
            cert = load(out1, "certificate.json")
            if cert["metrics"]["crossings"] != 0 or cert["grade"] != "最优":
                failures.append(f"ortho {ex}: legacy cert crossings="
                                f"{cert['metrics']['crossings']} grade={cert['grade']}")
            # 生产 pin 铁门：与提交基线逐字节一致
            base = os.path.join(root, "tests", "baselines", name + ".layout.json")
            with open(base, "rb") as a, \
                 open(os.path.join(out1, "layout.json"), "rb") as b:
                if a.read() != b.read():
                    failures.append(f"ortho {ex}: layout.json 漂移 vs tests/baselines/"
                                    f"（生产行为 pin 被破坏——planar.py 必须冻结）")
            # 确定性（ref-scrubbed：loops_audit.json 纳入逐字节确定性清单）
            for fn in ("layout.json", "demo-2d.html", "loops_audit.json"):
                with open(os.path.join(out1, fn), "rb") as a, \
                     open(os.path.join(out2, fn), "rb") as b:
                    if a.read() != b.read():
                        failures.append(f"ortho {ex}: {fn} 不确定（两次运行不一致）")
            audit = load(out1, "loops_audit.json")
            if audit["summary"]["problems"] != 0:
                failures.append(f"ortho {ex}: loops problems={audit['summary']['problems']}")
            print(f"OK  ortho {ex}: 11 checks fail=0, baseline byte-identical, deterministic")

        # ── B. auto-v2 新硬门 ──
        for ex in AUTO_EXAMPLES:
            name = os.path.splitext(os.path.basename(ex))[0]
            out1 = os.path.join(tmp, name + "-auto-1")
            out2 = os.path.join(tmp, name + "-auto-2")
            r1 = run_cli(ex, out1, ("--recipe", "auto"), pitch=None)
            # auto 配方不传 pitch（自调 80）
            if r1.returncode != 0:
                tail = "\n".join(r1.stdout.strip().splitlines()[-25:])
                try:
                    lj = json.load(open(os.path.join(out1, "layout.json"),
                                        encoding="utf-8"))
                    dump = json.dumps({"viewBox": lj["viewBox"],
                                       "nodes": {v: p for v, p in lj["nodes"].items()}},
                                      ensure_ascii=False)
                except Exception as _e:
                    dump = f"layout.json unreadable: {_e}"
                failures.append(f"auto {ex}: CLI exit {r1.returncode}\n"
                                f"stderr={r1.stderr}\nstdout_tail:\n{tail}\n"
                                f"layout_dump={dump}")
                continue
            run_cli(ex, out2, ("--recipe", "auto"), pitch=None)
            geo = load(out1, "geometry_report.json")
            if geo.get("fail", 0) != 0:
                failures.append(f"auto {ex}: geometry fail={geo['fail']}")
            cert = load(out1, "certificate.json")
            m = cert["metrics"]
            gates = _hard_gates_for(cert)
            for k in gates:
                if not cert["gates"].get(k, False):
                    failures.append(f"auto {ex}: 硬门 {k} FAIL "
                                    f"(metrics={json.dumps(m, ensure_ascii=False)[:300]})")
            if m["crossings"] > 2:
                failures.append(f"auto {ex}: crossings={m['crossings']} > 2")
            if cert["grade"] not in ("最优", "其次"):
                failures.append(f"auto {ex}: grade={cert['grade']}")
            audit = load(out1, "loops_audit.json")
            if audit["summary"]["problems"] != 0:
                failures.append(f"auto {ex}: loops problems={audit['summary']['problems']}")
            # 确定性（ref-scrubbed：loops_audit.json 纳入逐字节确定性清单）
            for fn in ("layout.json", "certificate.json", "demo-2d.html",
                       "loops_audit.json"):
                with open(os.path.join(out1, fn), "rb") as a, \
                     open(os.path.join(out2, fn), "rb") as b:
                    if a.read() != b.read():
                        failures.append(f"auto {ex}: {fn} 不确定（两次运行不一致）")
            print(f"OK  auto {ex}: hard gates pass, crossings={m['crossings']}, "
                  f"grade={cert['grade']}, deterministic")

        # ── B2. 随机稠密图抽样（WS3-Q 布线质量门控回归）──
        for ex in RANDOM_SAMPLES:
            name = os.path.splitext(os.path.basename(ex))[0]
            out1 = os.path.join(tmp, name + "-auto-1")
            out2 = os.path.join(tmp, name + "-auto-2")
            r1 = run_cli(ex, out1, ("--recipe", "auto"), pitch=None)
            if r1.returncode != 0:
                tail = "\n".join(r1.stdout.strip().splitlines()[-10:])
                failures.append(f"random {ex}: CLI exit {r1.returncode}\n{tail}")
                continue
            run_cli(ex, out2, ("--recipe", "auto"), pitch=None)
            geo = load(out1, "geometry_report.json")
            if geo.get("fail", 0) != 0:
                failures.append(f"random {ex}: geometry fail={geo['fail']}")
            cert = load(out1, "certificate.json")
            m = cert["metrics"]
            if m["crossings"] > 2:
                failures.append(f"random {ex}: crossings={m['crossings']} > 2")
            if (m.get("edge_box_min_clear") or 0) < 16:
                failures.append(f"random {ex}: edge_box_min_clear="
                                f"{m.get('edge_box_min_clear')} < 16")
            # 确定性（ref-scrubbed：loops_audit.json 纳入逐字节确定性清单）
            for fn in ("layout.json", "demo-2d.html", "loops_audit.json"):
                with open(os.path.join(out1, fn), "rb") as a, \
                     open(os.path.join(out2, fn), "rb") as b:
                    if a.read() != b.read():
                        failures.append(f"random {ex}: {fn} 不确定（两次运行不一致）")
            print(f"OK  random {ex}: crossings={m['crossings']}, "
                  f"min_clear={m.get('edge_box_min_clear')}px, deterministic")

        # ── C. DOM 实测框界（可选层）──
        r = subprocess.run(
            [sys.executable, "-m", "stdraw.rendercheck",
             os.path.join(tmp, os.path.basename(EXAMPLES[0]).split(".")[0] + "-auto-1")],
            capture_output=True, text=True)
        if r.returncode == 2:
            print("SKIP  rendercheck: playwright 不可用（CI workflow 安装可选层兜底）")
        elif r.returncode != 0:
            failures.append(f"rendercheck: exit {r.returncode}\n{r.stdout}\n{r.stderr}")
        else:
            print("OK  rendercheck: DOM 实测框界无溢出")

        # ── D. WS3 布线数学层单元（可见性图最短路/净距/双口径）──
        r = subprocess.run([sys.executable, os.path.join(root, "tests",
                                                          "test_visibility.py")],
                           capture_output=True, text=True)
        if r.returncode != 0:
            failures.append(f"test_visibility: exit {r.returncode}\n{r.stdout}\n{r.stderr}")
        else:
            print("OK  test_visibility: 可见性图最短路/弧平滑/双口径 单元全过")

        # ── E. WS2 精确交叉数层（可选层：需 ortools；不可用如实 SKIP）──
        try:
            import ortools  # noqa: F401
            has_ortools = True
        except Exception:
            has_ortools = False
        if has_ortools:
            for t in ("test_crossing_exact.py", "test_placement.py",
                      "test_scalability.py"):
                r = subprocess.run([sys.executable, os.path.join(root, "tests", t)],
                                   capture_output=True, text=True)
                if r.returncode != 0:
                    failures.append(f"{t}: exit {r.returncode}\n"
                                    f"{r.stdout}\n{r.stderr}")
                else:
                    print(f"OK  {t}: 全过")
        else:
            print("SKIP test_crossing_exact/test_placement: "
                  "ortools 不可用（CI workflow 安装 [solver] 可选层兜底）")

        # ── F. 手动布局闭环（ref-scrubbed）：--from-layout 恒等复现 + layout-diff ──
        ex = EXAMPLES[0]
        name = os.path.splitext(os.path.basename(ex))[0]
        out_f = os.path.join(tmp, name + "-manual-f")
        r_f = run_cli(ex, out_f, (), pitch=None)          # auto 基线（F 层自持）
        if r_f.returncode != 0:
            failures.append(f"manual-loop {ex}: auto 基线 exit {r_f.returncode}")
        else:
            lay = load(out_f, "layout.json")
            ident = {"viewBox": lay["viewBox"],
                     "nodes": {v: {"x": p["x"], "y": p["y"]}
                               for v, p in lay["nodes"].items()}}
            ipath = os.path.join(tmp, "ci-ident-manual.json")
            with open(ipath, "w", encoding="utf-8") as f:
                json.dump(ident, f, ensure_ascii=False)
            out_f2 = os.path.join(tmp, name + "-manual-f2")
            r_f2 = run_cli(ex, out_f2, ("--from-layout", ipath), pitch=None)
            geo_f = load(out_f2, "geometry_report.json")
            lay_f = load(out_f2, "layout.json")
            if r_f2.returncode != 0 or geo_f.get("fail", 0) != 0:
                failures.append(f"manual-loop {ex}: 恒等手动布局 exit "
                                f"{r_f2.returncode} fail={geo_f.get('fail')}")
            elif lay_f["nodes"] != lay["nodes"] or \
                    lay_f["meta"].get("position_engine") != "manual":
                failures.append(f"manual-loop {ex}: 恒等手动布局漂移/engine 非 manual")
            else:
                dpath = os.path.join(tmp, "ci-layout-diff.json")
                r_d = subprocess.run(
                    [sys.executable, "-m", "stdraw", "layout-diff",
                     os.path.join(out_f, "layout.json"),
                     os.path.join(out_f2, "layout.json"),
                     "--cld", ex, "--diff-out", dpath],
                    capture_output=True, text=True)
                try:
                    with open(dpath, encoding="utf-8") as f:
                        diff = json.load(f)
                    assert (diff["node_level"] and diff["structural"]
                            and diff["semantic"])
                except Exception as e:
                    failures.append(f"manual-loop layout-diff: {e}\n{r_d.stdout[-300:]}")
                if not failures or all("manual-loop" not in x for x in failures):
                    print("OK  manual-loop: --from-layout 恒等复现 fail=0 + "
                          "layout-diff 三层齐备")

        # ── F2. ref-scrubbed：--from-layout waypoints 恒等复算（折点把手全链）──
        # 夹具：ref-scrubbed 起折线带固定类型代价（弧线>直线>折线），路由器
        # 很少再自发产出 vg 边——夹具改为**手工锚定 waypoints**（与 demo 折点
        # 把手导出同构），验证同一全链：waypoints 原样锚定喂回 → kind=
        # waypoints 的同一折线（锚点重算贴框边）+ 确定性成立。
        lay_g = load(out_f, "layout.json")
        man_base = {"viewBox": lay_g["viewBox"],
                    "nodes": {v: {"x": p["x"], "y": p["y"]}
                              for v, p in lay_g["nodes"].items()}}
        e0 = lay_g["edges"][0]
        a0n, b0n = nodes_of = (e0["a"], e0["b"])
        p0 = lay_g["nodes"][a0n]
        p1 = lay_g["nodes"][b0n]
        mx = (p0["x"] + p1["x"]) / 2
        my = (p0["y"] + p1["y"]) / 2
        # 垂直于边方向的确定性绕行折点（两侧各一，整 2px 网格）
        dx, dy = p1["x"] - p0["x"], p1["y"] - p0["y"]
        n = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = -dy / n, dx / n
        wp = [[int(round((mx + ux * 70) / 2)) * 2, int(round((my + uy * 70) / 2)) * 2],
              [int(round((mx - ux * 70) / 2)) * 2, int(round((my - uy * 70) / 2)) * 2]]
        man_base["edges"] = [{"a": a0n, "b": b0n, "waypoints": wp}]
        ipath2 = os.path.join(tmp, "ci-wp-manual.json")
        with open(ipath2, "w", encoding="utf-8") as f:
            json.dump(man_base, f, ensure_ascii=False)
        out_w1 = os.path.join(tmp, name + "-wp-1")
        out_w2 = os.path.join(tmp, name + "-wp-2")
        r_w1 = run_cli(ex, out_w1, ("--from-layout", ipath2), pitch=None)
        run_cli(ex, out_w2, ("--from-layout", ipath2), pitch=None)
        lay_w = load(out_w1, "layout.json")
        e_w = next((x for x in lay_w["edges"]
                    if (x["a"], x["b"]) == (a0n, b0n)), None)
        want_via = [[float(q[0]), float(q[1])] for q in wp]
        if (not e_w or e_w["route"]["kind"] != "waypoints" or
                e_w["route"].get("via") != want_via or
                len(e_w["route"]["points"]) != len(want_via) + 2):
            failures.append(f"manual-waypoints: 复算不一致 rc={r_w1.returncode} "
                            f"kind={e_w['route']['kind'] if e_w else '?'}")
        else:
            for fn in ("layout.json", "demo-2d.html"):
                with open(os.path.join(out_w1, fn), "rb") as a, \
                     open(os.path.join(out_w2, fn), "rb") as b:
                    if a.read() != b.read():
                        failures.append(f"manual-waypoints: {fn} 不确定")
            if not any("manual-waypoints" in x for x in failures):
                print("OK  manual-waypoints: --from-layout waypoints 恒等复算 "
                      "fail=0 + 确定性")

        # ── G. 回路主导环形排布（ref-scrubbed）：触发/口径/负例/回退 ──
        r = subprocess.run([sys.executable, os.path.join(root, "tests",
                                                          "test_ring_layout.py")],
                           capture_output=True, text=True)
        if r.returncode != 0:
            failures.append(f"test_ring_layout: exit {r.returncode}\n"
                            f"{r.stdout}\n{r.stderr}")
        else:
            print("OK  test_ring_layout: 环形触发/口径/负例不误伤/确定性 全过")

        # G2. debt-spiral 实测：主环成圆、0 交叉、环形口径门全过
        ds = os.path.join(root, "benchmarks/corpus/classic/debt-spiral.cld")
        out_g = os.path.join(tmp, "debt-spiral-ring")
        r_g = run_cli(ds, out_g, (), pitch=None)
        if r_g.returncode != 0:
            failures.append(f"ring debt-spiral: CLI exit {r_g.returncode}\n{r_g.stdout[-800:]}")
        else:
            lay_g = load(out_g, "layout.json")
            cert_g = load(out_g, "certificate.json")
            if lay_g["meta"].get("placement") != "ring-cycle" or \
                    lay_g["meta"].get("position_engine") != "ring-construct":
                failures.append("ring debt-spiral: 未走环形排布 "
                                f"(engine={lay_g['meta'].get('position_engine')})")
            if cert_g["metrics"]["crossings"] != 0 or \
                    cert_g.get("placement") != "ring-cycle":
                failures.append(f"ring debt-spiral: crossings="
                                f"{cert_g['metrics']['crossings']} placement="
                                f"{cert_g.get('placement')}")
            for k in RING_HARD_GATES:
                if not cert_g["gates"].get(k, False):
                    failures.append(f"ring debt-spiral: 环形口径门 {k} FAIL")
            if cert_g["grade"] != "最优":
                failures.append(f"ring debt-spiral: grade={cert_g['grade']}")
            if not failures or all("debt-spiral" not in x for x in failures):
                print("OK  ring debt-spiral: 主环成圆(5节点) 交叉0 最优 "
                      "环形口径门全过")

        # G3. 负例不误伤：链/树/13节点环/双三角+桥 → 不触发环形
        # （ref-scrubbed：双三角+桥可进纵列——少环+主链结构；断言只禁 ring）
        neg_fixtures = {
            "ci-neg-chain.cld": 'graph "链"\nvar a "A"\nvar b "B"\nvar c "C"\n'
                                'var d "D"\na -> + b\nb -> + c\nc -> + d\n',
            "ci-neg-tree.cld": 'graph "树"\nvar root "根"\nvar x1 "子一"\n'
                               'var x2 "子二"\nroot -> + x1\nroot -> + x2\n',
            "ci-neg-big-ring.cld": "graph \"大环\"\n" + "".join(
                f'var v{i} "节点{i}"\n' for i in range(13)) + "".join(
                f'v{i} -> + v{(i + 1) % 13}\n' for i in range(13)),
            "ci-neg-two-tri.cld": 'graph "双三角"\nvar a1 "甲一"\nvar a2 "甲二"\n'
                                  'var a3 "甲三"\nvar b1 "乙一"\nvar b2 "乙二"\n'
                                  'var b3 "乙三"\na1 -> + a2\na2 -> + a3\n'
                                  'a3 -> + a1\nb1 -> + b2\nb2 -> + b3\n'
                                  'b3 -> + b1\na1 -> + b1\n',
        }
        for fn, text in neg_fixtures.items():
            p = os.path.join(tmp, fn)
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            out_n = os.path.join(tmp, fn + "-out")
            r_n = run_cli(p, out_n, (), pitch=None)
            if r_n.returncode not in (0, 1):     # 几何 fail=存量语义，exit 1 合法
                failures.append(f"ring 负例 {fn}: CLI exit {r_n.returncode}")
                continue
            lay_n = load(out_n, "layout.json")
            if lay_n["meta"].get("position_engine") == "ring-construct":
                failures.append(f"ring 负例 {fn}: 误触发环形排布")
        if not failures or all("负例" not in x for x in failures):
            print("OK  ring 负例 4 张（链/树/13节点环/双三角+桥）：不触发环形"
                  "（双三角+桥 ref-scrubbed 起可进纵列，只禁 ring）")

        # ── H. 布局美学 v2（ref-scrubbed）：纵列/对称触发 + R/B 颜色化 + 全语料 ──
        r = subprocess.run([sys.executable, os.path.join(root, "tests",
                                                          "test_layout_modes.py")],
                           capture_output=True, text=True)
        if r.returncode != 0:
            failures.append(f"test_layout_modes: exit {r.returncode}\n"
                            f"{r.stdout}\n{r.stderr}")
        else:
            print("OK  test_layout_modes: 纵列/对称触发·几何·R/B 颜色化·"
                  "交叉软目标·确定性 全过")

        # H2. 全 classic 语料 19 张：exit 0 + 全部最优 + 硬门全过（新口径）
        corpus_dir = os.path.join(root, "benchmarks", "corpus", "classic")
        n_ok = 0
        for fn in sorted(os.listdir(corpus_dir)):
            if not fn.endswith(".cld"):
                continue
            name = fn[:-4]
            out_h = os.path.join(tmp, "H-" + name)
            r_h = run_cli(os.path.join(corpus_dir, fn), out_h, (), pitch=None)
            if r_h.returncode != 0:
                failures.append(f"corpus {name}: CLI exit {r_h.returncode}\n"
                                f"{r_h.stdout[-500:]}")
                continue
            cert_h = load(out_h, "certificate.json")
            if cert_h["grade"] != "最优":
                failures.append(f"corpus {name}: grade={cert_h['grade']}")
            for k in _hard_gates_for(cert_h):
                if not cert_h["gates"].get(k, False):
                    failures.append(f"corpus {name}: 硬门 {k} FAIL")
            if cert_h["metrics"]["crossings"] > 2:
                failures.append(f"corpus {name}: crossings="
                                f"{cert_h['metrics']['crossings']}")
            n_ok += 1
        print(f"OK  corpus 全语料 {n_ok}/19：exit 0 · 最优 · 新口径硬门全过")

        # H3. R/B 颜色化口径：wage R1 琥珀/B1 天蓝/多环异色中性 + 极性数据保留
        out_w = os.path.join(tmp, "H-wage")
        run_cli(os.path.join(corpus_dir, "wage-price-spiral.cld"), out_w,
                (), pitch=None)
        lay_w = load(out_w, "layout.json")
        by_pair = {(e["a"], e["b"]): e for e in lay_w["edges"]}
        for pr, kinds, color in (
                (("wages", "cost"), ["R"], "#d97706"),
                (("cost", "prices"), ["R"], "#d97706"),
                (("prices", "real_income"), ["B"], "#0284c7"),
                (("demand", "prices"), ["B"], "#0284c7")):
            e = by_pair[pr]
            if e["loop_kinds"] != kinds or e["loop_color"] != color:
                failures.append(f"R/B 颜色化 {pr}: kinds={e['loop_kinds']} "
                                f"color={e['loop_color']}")
            if "polarity" not in e:
                failures.append(f"R/B 颜色化 {pr}: 极性数据丢失")
        demo_w = open(os.path.join(out_w, "demo-2d.html"), encoding="utf-8").read()
        if "data-pol" in demo_w:
            failures.append("R/B 颜色化: demo 仍含文字徽标 data-pol")
        if 'stroke="#d97706"' not in demo_w or 'stroke="#0284c7"' not in demo_w:
            failures.append("R/B 颜色化: demo 未含 R 琥珀/B 天蓝着色")
        print("OK  R/B 颜色化: 回路边按极性着色（R=琥珀/B=天蓝），"
              "文字徽标已移除，极性数据保留")

        # I. demo 交付件新鲜度（ref-scrubbed 返修，v0.7.1 教训）：引擎切
        #    spine-wing 后 demos/classic-cld-2d.html 没重渲染，jacky 眼验
        #    看到的仍是 ring-construct 旧图被误判「结构不一致」。铁门：
        #    交付 demo 必须与当前引擎重渲染逐字节一致（引擎确定性已由
        #    双跑验证，可逐字节 pin）。
        fresh_out = os.path.join(tmp, "I-fresh-demo")
        r_f = run_cli("examples/classic-cld-growth-and-burden.cld", fresh_out,
                      ("--name", "classic-cld", "--skip-3d"), pitch=None)
        if r_f.returncode != 0:
            failures.append(f"demo 新鲜度: CLI exit {r_f.returncode}\n"
                            f"{r_f.stderr[-500:]}")
        else:
            committed = os.path.join(root, "demos", "classic-cld-2d.html")
            with open(committed, "rb") as a, \
                    open(os.path.join(fresh_out, "demo-2d.html"), "rb") as b:
                if a.read() != b.read():
                    failures.append(
                        "demo 新鲜度: demos/classic-cld-2d.html 与当前引擎"
                        "重渲染不一致（交付件过期——重跑 "
                        "python -m stdraw layout examples/"
                        "classic-cld-growth-and-burden.cld --name classic-cld"
                        " --skip-3d 并更新 demo + docs/gallery 截图）")
                else:
                    print("OK  demo 新鲜度: demos/classic-cld-2d.html 与当前"
                          "引擎重渲染逐字节一致（ref-scrubbed 防过期门）")

        if failures:
            print("\nFAILURES:")
            for f in failures:
                print(" -", f)
            return 1
        print("\nAll CI checks passed.")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
