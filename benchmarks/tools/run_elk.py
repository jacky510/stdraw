# ELK 基线 wrapper：.cld → elk 输入 JSON（px 框尺寸）→ node run_elk.cjs → 评测 JSON。
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)

from stdraw.dsl import parse        # noqa: E402
from eval_core import evaluate, box_size  # noqa: E402

NODE = os.environ.get("STDRAW_NODE", "node")   # node 可执行文件；默认走 PATH，可用环境变量覆盖
ELK_ENV = os.path.join(HERE, "env", "elk")


def main(cld_path, rawdir):
    rawdir = os.path.abspath(rawdir)
    os.makedirs(rawdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(cld_path))[0]
    g = parse(open(cld_path, encoding="utf-8").read())
    sizes = {n.id: box_size(n.label) for n in g.nodes}

    out = os.path.join(rawdir, f"{base}.elk.json")
    if os.path.exists(out):
        return
    elk_in = {
        "id": base,
        "children": [{"id": n.id, "width": sizes[n.id][0], "height": sizes[n.id][1]}
                     for n in g.nodes],
        "edges": [{"id": f"e{i}", "sources": [e.a], "targets": [e.b]}
                  for i, e in enumerate(g.edges)],
    }
    in_path = os.path.join(rawdir, f"{base}.elk.in.json")
    layout_path = os.path.join(rawdir, f"{base}.elk.layout.json")
    with open(in_path, "w", encoding="utf-8") as f:
        json.dump(elk_in, f)

    rec = {"tool": "elk-layered", "graph": base, "n": len(g.nodes), "m": len(g.edges)}
    try:
        t0 = time.perf_counter()
        p = subprocess.run([NODE, os.path.join(HERE, "run_elk.cjs"), in_path, layout_path],
                           cwd=ELK_ENV, capture_output=True, timeout=120,
                           env={**os.environ,
                                "ELKJS_PATH": os.path.join(ELK_ENV, "node_modules",
                                                           "elkjs", "lib", "elk.bundled.js")})
        dt = time.perf_counter() - t0
        if p.returncode != 0:
            raise RuntimeError(f"elk rc={p.returncode}: {p.stderr.decode()[:200]}")
        lay = json.load(open(layout_path, encoding="utf-8"))
        nodes = {k: (v["x"], v["y"], v["w"], v["h"]) for k, v in lay["nodes"].items()}
        routes = {int(k): [tuple(pt) for pt in v] for k, v in lay["routes"].items()}
        edges = lay["edges"]
        rec.update(evaluate(nodes, routes, edges, lay.get("runtime_s", dt),
                            "elk-layered", base))
    except Exception as e:
        rec.update({"status": "error", "why": repr(e)})
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
