# -*- coding: utf-8 -*-
"""F3 返修回归（ref-scrubbed）：auto 弧线鼓出必须落在 viewBox 内。

背景：viewBox 自 v0.2 起只按节点框计算，bullwhip 的 inventory->forecast 弧向
左鼓出 7.5px 出 viewBox 左缘 → check7 fail（CLI exit 1）。修复：交付层把全部
边几何（采样点 ∪ 弧 ctrl）纳入平移量与 W/H 计算。

覆盖：
  A. bullwhip（回归原案）：CLI exit 0、几何自检 fail=0、
     全部 route.points/ctrl 严格落在 viewBox 开区间内；
  B. 双 CI 例（limits-to-growth / classic-cld-growth-and-burden）：
     同样断言（B 层 ci_checks 已跑，这里做逐点包含的细口径）；
  C. 确定性：同输入两次 layout 逐字节一致。

运行：python tests/test_auto_viewbox.py（stdlib-only，exit 0 = 全过）。
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FAILURES = []


def ok(name, cond, detail=""):
    tag = "OK " if cond else "FAIL"
    print(f"{tag} {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def layout_and_check(root, cld, outdir):
    r = subprocess.run([sys.executable, "-m", "stdraw", "layout", cld,
                        "--recipe", "auto", "--outdir", outdir],
                       capture_output=True, text=True, cwd=root)
    lj = json.load(open(os.path.join(outdir, "layout.json"), encoding="utf-8"))
    geo = json.load(open(os.path.join(outdir, "geometry_report.json"),
                         encoding="utf-8"))
    return r, lj, geo


def contained(lj):
    """全部边交付几何（采样点 + 弧 ctrl）严格落在 viewBox 开区间内。"""
    W, H = lj["viewBox"][2], lj["viewBox"][3]
    bad = []
    for e in lj["edges"]:
        pts = [tuple(p) for p in e["route"]["points"]]
        c = e["route"].get("ctrl")
        if c:
            pts.append(tuple(c))
        for px, py in pts:
            if not (0 < px < W and 0 < py < H):
                bad.append((e["a"], e["b"], px, py))
    return bad


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
    cases = [
        "benchmarks/corpus/classic/bullwhip.cld",
        "examples/limits-to-growth.cld",
        "examples/classic-cld-growth-and-burden.cld",
    ]
    tmp = tempfile.mkdtemp(prefix="stdraw-f3-")
    for cld in cases:
        name = os.path.splitext(os.path.basename(cld))[0]
        o1 = os.path.join(tmp, name + "-1")
        o2 = os.path.join(tmp, name + "-2")
        r1, lj, geo = layout_and_check(root, cld, o1)
        ok(f"{name}: CLI exit 0", r1.returncode == 0,
           f"exit={r1.returncode}" + ("" if r1.returncode == 0
                                      else "\n" + r1.stdout[-500:]))
        ok(f"{name}: geometry fail=0", geo.get("fail", -1) == 0,
           f"fail={geo.get('fail')}")
        bad = contained(lj)
        ok(f"{name}: 边几何全部在 viewBox 内", not bad,
           f"viewBox={lj['viewBox']} 越界={bad[:3]}")
        layout_and_check(root, cld, o2)
        a = open(os.path.join(o1, "layout.json"), "rb").read()
        b = open(os.path.join(o2, "layout.json"), "rb").read()
        ok(f"{name}: 确定性（两次 layout.json 逐字节一致）", a == b)
    print()
    if FAILURES:
        print(f"FAILURES ({len(FAILURES)}):", FAILURES)
        return 1
    print("All auto-viewbox regression checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
