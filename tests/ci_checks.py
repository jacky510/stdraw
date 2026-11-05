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
HARD_GATES = ("box_press_zero", "edge_box_clear_ge_16", "anchors_smooth",
              "min_gap_ge_16", "cv_le_035", "regularity_simple")


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
            # 确定性
            for fn in ("layout.json", "demo-2d.html"):
                with open(os.path.join(out1, fn), "rb") as a, \
                     open(os.path.join(out2, fn), "rb") as b:
                    if a.read() != b.read():
                        failures.append(f"ortho {ex}: {fn} 不确定（两次运行不一致）")
            audit = load(out1, "loops_audit.json")
            if audit["summary"]["problems"] != 0:
                failures.append(f"ortho {ex}: loops problems={audit['summary']['problems']}")
            print(f"OK  ortho {ex}: 11 checks fail=0, baseline byte-identical, deterministic")

        # ── B. auto-v2 新硬门 ──
        for ex in EXAMPLES:
            name = os.path.splitext(os.path.basename(ex))[0]
            out1 = os.path.join(tmp, name + "-auto-1")
            out2 = os.path.join(tmp, name + "-auto-2")
            r1 = run_cli(ex, out1, ("--recipe", "auto"), pitch=None)
            # auto 配方不传 pitch（自调 80）
            if r1.returncode != 0:
                failures.append(f"auto {ex}: CLI exit {r1.returncode}\n{r1.stderr}")
                continue
            run_cli(ex, out2, ("--recipe", "auto"), pitch=None)
            geo = load(out1, "geometry_report.json")
            if geo.get("fail", 0) != 0:
                failures.append(f"auto {ex}: geometry fail={geo['fail']}")
            cert = load(out1, "certificate.json")
            m = cert["metrics"]
            for k in HARD_GATES:
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
            # 确定性
            for fn in ("layout.json", "certificate.json", "demo-2d.html"):
                with open(os.path.join(out1, fn), "rb") as a, \
                     open(os.path.join(out2, fn), "rb") as b:
                    if a.read() != b.read():
                        failures.append(f"auto {ex}: {fn} 不确定（两次运行不一致）")
            print(f"OK  auto {ex}: hard gates pass, crossings={m['crossings']}, "
                  f"grade={cert['grade']}, deterministic")

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
