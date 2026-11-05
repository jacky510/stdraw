# Graphviz 基线 runner：dot / neato / sfdp × 单文件 → raw JSON。
# 框尺寸以 inch=px/72、fixedsize 传入（native px 与 stdraw/ELK 同物理尺度）。
# 边折线取 -Tplain 的 spline 控制点（dot 默认 splines=true 的 bezier 控制多边形；
# neato/sfdp 为直线两点）。
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stdraw.dsl import parse        # noqa: E402
from eval_core import evaluate, box_size  # noqa: E402

GV_BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "env",
                      "Graphviz-16.1.0-win64", "bin")
LAYOUTS = ["dot", "neato", "sfdp"]
DPI = 72.0


def build_gv(g, sizes):
    lines = ["digraph G {", "  node [shape=box; fixedsize=true; style=filled; fillcolor=white;]"]
    for n in g.nodes:
        w, h = sizes[n.id]
        lines.append(f'  "{n.id}" [width={w / DPI:.4f}; height={h / DPI:.4f}; label="";]')
    for e in g.edges:
        lines.append(f'  "{e.a}" -> "{e.b}";')
    lines.append("}")
    return "\n".join(lines) + "\n"


def run_layout(prog, gv_text, timeout=120):
    exe = os.path.join(GV_BIN, f"{prog}.exe")
    t0 = time.perf_counter()
    p = subprocess.run([exe, "-Tplain"], input=gv_text.encode("utf-8"),
                       capture_output=True, timeout=timeout)
    dt = time.perf_counter() - t0
    if p.returncode != 0:
        raise RuntimeError(f"{prog} rc={p.returncode}: {p.stderr[:200]}")
    return p.stdout.decode("utf-8"), dt


def parse_plain(plain):
    nodes, routes, edges = {}, {}, []
    for line in plain.splitlines():
        t = line.split()
        if not t:
            continue
        if t[0] == "node":
            name, x, y, w, h = t[1], float(t[2]) * DPI, float(t[3]) * DPI, \
                float(t[4]) * DPI, float(t[5]) * DPI
            nodes[name] = (x, y, w, h)
        elif t[0] == "edge":
            a, b = t[1], t[2]
            npts = int(t[3])
            coords = [float(v) * DPI for v in t[4:4 + 2 * npts]]
            routes[len(edges)] = list(zip(coords[0::2], coords[1::2]))
            edges.append({"a": a, "b": b})
    return nodes, routes, edges


def main(cld_path, rawdir):
    os.makedirs(rawdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(cld_path))[0]
    g = parse(open(cld_path, encoding="utf-8").read())
    sizes = {n.id: box_size(n.label) for n in g.nodes}
    gv_text = build_gv(g, sizes)
    for prog in LAYOUTS:
        out = os.path.join(rawdir, f"{base}.gv-{prog}.json")
        if os.path.exists(out):
            continue
        rec = {"tool": f"graphviz-{prog}", "graph": base,
               "n": len(g.nodes), "m": len(g.edges)}
        try:
            plain, dt = run_layout(prog, gv_text)
            nodes, routes, edges = parse_plain(plain)
            rec.update(evaluate(nodes, routes, edges, dt, f"graphviz-{prog}", base))
        except Exception as e:
            rec.update({"status": "error", "why": repr(e)})
        with open(out, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False)
        print(out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
