# -*- coding: utf-8 -*-
# WS2 验收比对：重跑随机族 exact，逐图与既有 raw 参考值对拍（cr 不漂移）。
# 用法: python compare_ws2.py <rawdir_new>
# 输出: 比对结果 JSON 到 stdout；退出码 0=全对拍通过/如实降级。
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
BUDGET = 300


def main(newdir):
    clds = sorted(glob.glob(os.path.join(HERE, "..", "corpus", "random", "*.cld")))
    old_raw = os.path.join(HERE, "..", "raw")
    rows = []
    for cld in clds:
        base = os.path.splitext(os.path.basename(cld))[0]
        newdir_abs = os.path.abspath(newdir)
        out = os.path.join(newdir_abs, f"{base}.exact.json")
        if not os.path.exists(out):
            try:
                subprocess.run([PY, os.path.join(HERE, "run_exact.py"), cld, newdir_abs],
                               capture_output=True, timeout=BUDGET, cwd=HERE)
            except subprocess.TimeoutExpired:
                json.dump({"tool": "stdraw-exact", "graph": base, "cr": None,
                           "status": "dnf"}, open(out, "w", encoding="utf-8"))
        new = json.load(open(out, encoding="utf-8"))
        op = os.path.join(old_raw, f"{base}.exact.json")
        old = json.load(open(op, encoding="utf-8")) if os.path.exists(op) else None
        verdict = "no-old"
        if old and old.get("status") == "ok" and old.get("cr") is not None:
            if new.get("status") == "ok" and new.get("cr") == old.get("cr"):
                verdict = "match"
            else:
                verdict = "DRIFT"
        rows.append({"graph": base, "verdict": verdict,
                     "old_cr": old.get("cr") if old else None,
                     "new_cr": new.get("cr"), "new_status": new.get("status"),
                     "new_runtime": new.get("runtime_s")})
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    os.makedirs(newdir_abs, exist_ok=True)
    with open(os.path.join(newdir_abs, "_compare_summary.json"), "w",
              encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    n_drift = sum(1 for r in rows if r["verdict"] == "DRIFT")
    n_match = sum(1 for r in rows if r["verdict"] == "match")
    n_noold = sum(1 for r in rows if r["verdict"] == "no-old")
    crash = sum(1 for r in rows if r["new_status"] not in ("ok", "dnf"))
    print(f"SUMMARY match={n_match} no-old={n_noold} drift={n_drift} "
          f"crash={crash} total={len(rows)}", flush=True)
    sys.exit(1 if (n_drift or crash) else 0)


if __name__ == "__main__":
    main(sys.argv[1])
