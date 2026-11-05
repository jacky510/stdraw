# 生成脚本：随机稀疏图族（固定种子，可复现）
# 用法：python gen_random.py [--outdir ../corpus/random] [--manifest ../manifest.json]
# 规则：n ∈ {10,20,30,50} × 各 20 张；seed = 4200 + n*100 + i（写进文件头与清单）；
#       边数 m = round(1.6*n)（CLD 典型稀疏密度）；标签 N01…（等宽短标签，各工具框宽一致）；
#       极性随机 +/-（仅渲染语义，不影响几何）；清单附可平面/不可平面分层（networkx）。
import argparse
import json
import os

import networkx as nx


def gen(n: int, i: int, outdir: str) -> dict:
    seed = 4200 + n * 100 + i
    m = round(1.6 * n)
    g = nx.gnm_random_graph(n, m, seed=seed)
    g = nx.convert_node_labels_to_integers(g)
    lines = [
        f"# 随机稀疏图族 n={n} i={i:02d} seed={seed} m={g.number_of_edges()}",
        f'graph "random-n{n}-i{i:02d}"',
        "",
    ]
    for v in sorted(g.nodes()):
        lines.append(f'var N{v:02d} "N{v:02d}"')
    lines.append("")
    for a, b in sorted(g.edges()):
        pol = "+" if (a + b) % 3 != 0 else "-"
        lines.append(f"N{a:02d} -> {pol} N{b:02d}")
    text = "\n".join(lines) + "\n"
    path = os.path.join(outdir, f"random-n{n}-i{i:02d}.cld")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    planar, _ = nx.check_planarity(g)
    return {"file": os.path.basename(path), "n": n, "m": g.number_of_edges(),
            "seed": seed, "planar": bool(planar)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(__file__), "..", "corpus", "random"))
    ap.add_argument("--manifest", default=os.path.join(os.path.dirname(__file__), "..", "manifest.json"))
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    entries = []
    for n in (10, 20, 30, 50):
        for i in range(20):
            entries.append(gen(n, i, a.outdir))
    manifest = {
        "random_family": {
            "generator": "networkx.gnm_random_graph",
            "seeds": "4200 + n*100 + i, n in {10,20,30,50}, i in 0..19",
            "density": "m = round(1.6*n)",
            "count": len(entries),
            "planar": sum(1 for e in entries if e["planar"]),
            "nonplanar": sum(1 for e in entries if not e["planar"]),
            "entries": entries,
        }
    }
    with open(a.manifest, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f"generated {len(entries)} graphs; "
          f"planar={manifest['random_family']['planar']} "
          f"nonplanar={manifest['random_family']['nonplanar']} -> {a.outdir}")


if __name__ == "__main__":
    main()
