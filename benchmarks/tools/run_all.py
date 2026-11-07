# Batch orchestrator: full corpus × all tools -> raw/. Each run is a subprocess under a budget; timeouts land as DNF.
# Re-enterable: existing outputs are skipped. Progress is written to run_all.log.
#
# Budgets (seconds, per REPORT §2 conventions):
#   ortho 60; auto classic 300 / random n<=10 350 / random n>=20 100;
#   auto-exact = auto layout reuse (WS2 proved deterministic byte-identical) + a separate cr(G) run (300s);
#   graphviz/elk 120.
# Post-WS5 engine conventions: CP-SAT placement for n>10 carries a deterministic time budget (max_deterministic_time
# =8det, output still byte-for-byte reproducible), n<=10 and the routing layer unchanged (solved to optimality); the root cause of the old
# all-DNF for n>=20 was CP-SAT optimality-proof time exploding with n (not polish -- polish has a core<=10 gate),
# see REPORT §5 for details.
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
    # baselines
    for tool in ("run_graphviz.py", "run_elk.py"):
        run([PY, os.path.join(HERE, tool), cld, RAW], BASELINE_BUDGET, log)
    # stdraw constructive form
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
    # stdraw auto+WS2 exact layer: layout reused from auto (deterministic byte-identical) + a separate cr(G) run
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
