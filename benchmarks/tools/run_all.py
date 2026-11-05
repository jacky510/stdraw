# 批量 orchestrator：全语料 × 全工具 → raw/。逐 run subprocess 控预算，超时落 DNF。
# 可重入：已存在的输出跳过。进度写 run_all.log。
#
# 预算（秒，REPORT §2 口径）：
#   ortho 60；auto classic 300 / 随机 n≤10 350 / 随机 n≥20 100；
#   auto-exact = auto 布局复用（WS2 已证确定性逐字节一致）+ 单独跑 cr(G)（300s）；
#   graphviz/elk 120。
# WS5 后引擎口径：n>10 的 CP-SAT 定位带确定性时间预算（max_deterministic_time
# =8det，输出仍逐字节可复现），n≤10 与布线层不变（求到最优）；旧版 n≥20 全 DNF
# 的根因是 CP-SAT 证最优耗时随 n 爆炸（不是 polish——polish 有 core≤10 门），
# 详见 REPORT §5。
import glob
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
RAW = os.path.abspath(os.path.join(HERE, "..", "raw"))
PY = sys.executable

BASELINE_BUDGET = 120
EXACT_BUDGET = 300


def auto_budget(n):
    if n <= 10:
        return 350
    return 100


def run(cmd, budget, log):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=budget, cwd=REPO)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        rc = "TIMEOUT"
    log.write(f"  rc={rc} {time.time() - t0:.1f}s\n")
    log.flush()
    return rc


def save_json(path, rec):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)


def one(cld, family, log):
    base = os.path.splitext(os.path.basename(cld))[0]
    gtxt = open(cld, encoding="utf-8").read()
    n = gtxt.count("\nvar ")
    log.write(f"{family}/{base} (n={n})\n")
    log.flush()
    # 基线
    for tool in ("run_graphviz.py", "run_elk.py"):
        run([PY, os.path.join(HERE, tool), cld, RAW], BASELINE_BUDGET, log)
    # stdraw 构造法
    out = os.path.join(RAW, f"{base}.ortho.json")
    if not os.path.exists(out):
        rc = run([PY, os.path.join(HERE, "run_stdraw.py"), cld, RAW, "ortho"], 60, log)
        if rc == "TIMEOUT":
            save_json(out, {"tool": "stdraw-ortho", "graph": base, "status": "dnf",
                            "why": "timeout", "budget_s": 60})
    # stdraw auto-v2
    out = os.path.join(RAW, f"{base}.auto.json")
    if not os.path.exists(out):
        b = 300 if family == "classic" else auto_budget(n)
        rc = run([PY, os.path.join(HERE, "run_stdraw.py"), cld, RAW, "auto"], b, log)
        if rc == "TIMEOUT":
            save_json(out, {"tool": "stdraw-auto", "graph": base, "status": "dnf",
                            "why": f"timeout at budget {b}s (engine has no wall-clock "
                                   f"limit by determinism design; CP-SAT uses a "
                                   f"deterministic-time budget for n>10, see REPORT §5)",
                            "budget_s": b})
    # stdraw auto+WS2 精确层：布局复用 auto（确定性逐字节一致）+ 单独跑 cr(G)
    out = os.path.join(RAW, f"{base}.auto-exact.json")
    auto_path = os.path.join(RAW, f"{base}.auto.json")
    if not os.path.exists(out):
        auto_ok = (os.path.exists(auto_path) and
                   json.load(open(auto_path, encoding="utf-8")).get("status") == "ok")
        if not auto_ok:
            save_json(out, {"tool": "stdraw-auto-exact", "graph": base,
                            "status": "dnf", "why": "auto form not ok — layout unavailable",
                            "budget_s": 0})
        else:
            ex_out = os.path.join(RAW, f"{base}.exact.json")
            rc = run([PY, os.path.join(HERE, "run_exact.py"), cld, RAW], EXACT_BUDGET, log)
            if rc == "TIMEOUT":
                save_json(ex_out, {"tool": "stdraw-exact", "graph": base, "status": "dnf",
                                   "why": "timeout", "budget_s": EXACT_BUDGET})
            auto = json.load(open(auto_path, encoding="utf-8"))
            exact = json.load(open(ex_out, encoding="utf-8")) if os.path.exists(ex_out) else {}
            merged = dict(auto)
            merged["tool"] = "stdraw-auto-exact"
            et = exact.get("runtime_s")
            merged["runtime_s"] = round(auto.get("runtime_s", 0) + (et or 0), 3)
            merged["exactness"] = (None if exact.get("status") != "ok" else
                                   {"cr": exact.get("cr"), "proven_optimal": exact.get("proven_optimal"),
                                    "coverage": exact.get("coverage"), "gap": exact.get("gap"),
                                    "exact_time_s": et,
                                    "note": "layout metrics reused from the deterministic auto run "
                                            "(byte-identical determinism, WS2 CI-verified); "
                                            "runtime_s = layout + cr(G) computation"})
            save_json(out, merged)


def main():
    log = open(os.path.join(RAW, "run_all.log"), "a", encoding="utf-8")
    started = time.time()
    classic = sorted(glob.glob(os.path.join(REPO, "benchmarks", "corpus", "classic", "*.cld")))
    random_ = sorted(glob.glob(os.path.join(REPO, "benchmarks", "corpus", "random", "*.cld")))
    log.write(f"=== run_all start {time.strftime('%F %T')} "
              f"classic={len(classic)} random={len(random_)} ===\n")
    log.flush()
    for cld in classic:
        one(cld, "classic", log)
    for cld in random_:
        one(cld, "random", log)
    log.write(f"=== run_all done {time.strftime('%F %T')} "
              f"elapsed={time.time() - started:.0f}s ===\n")
    log.close()


if __name__ == "__main__":
    main()
