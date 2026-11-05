# WS2 精确交叉数层单独 runner：cr(G)（布局无关参考真值）→ raw JSON。
# 用法：python run_exact.py <file.cld> <rawdir>   （orchestrator 控 subprocess 超时）
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from stdraw.dsl import parse                    # noqa: E402


def main(cld_path, rawdir):
    rawdir = os.path.abspath(rawdir)
    os.makedirs(rawdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(cld_path))[0]
    out = os.path.join(rawdir, f"{base}.exact.json")
    if os.path.exists(out):
        print(out)
        return
    g = parse(open(cld_path, encoding="utf-8").read())
    from stdraw.crossing_exact import crossing_exact
    t0 = time.perf_counter()
    ex = crossing_exact(g)
    rec = {"tool": "stdraw-exact", "graph": base, "n": len(g.nodes), "m": len(g.edges),
           "cr": ex.get("crossing_number"), "proven_optimal": ex.get("proven_optimal"),
           "lb": ex.get("lb"), "gap": ex.get("gap"), "coverage": ex.get("coverage"),
           "status": "ok", "runtime_s": round(time.perf_counter() - t0, 3)}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
