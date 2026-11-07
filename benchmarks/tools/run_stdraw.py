# stdraw runner: single file × single form -> raw JSON (the orchestrator invokes it per form and controls the budget
# via a subprocess timeout; on a timeout kill the orchestrator writes a DNF JSON). Re-enterable (existing outputs skipped).
#
# Forms:
#   ortho       constructive (ortho-v1; non-planar -> not_planar_skip, honestly recorded)
#   auto        auto-v2 (CP-SAT placement + WS3 mathematical routing + polish refinement)
#   auto-exact  auto-v2 layout + WS2 exact crossing-number layer cr(G) (exactness block)
#
# Usage: python run_stdraw.py <file.cld> <rawdir> <form>
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stdraw.dsl import parse                    # noqa: E402
from stdraw.planar import PlanarLayout, LayoutConfig, NotPlanarError  # noqa: E402
from stdraw.recipes import run as recipes_run   # noqa: E402
from stdraw.layout_auto import AutoConfig       # noqa: E402
from eval_core import evaluate, box_size        # noqa: E402


def to_scene(v4):
    """layout.json v4 -> unified nodes/routes."""
    ch = v4["meta"].get("cardH", 44)
    nodes = {v: (p["x"], p["y"], p.get("w", 140), ch) for v, p in v4["nodes"].items()}
    routes = {}
    for i, e in enumerate(v4["edges"]):
        if "route" in e:
            routes[i] = [tuple(p) for p in e["route"]["points"]]
        else:
            routes[i] = [(e["x"], e["y1"]), (e["x"], e["y2"])]
    edges = [{"a": e["a"], "b": e["b"]} for e in v4["edges"]]
    return nodes, routes, edges


def save(rawdir, base, suffix, rec):
    with open(os.path.join(rawdir, f"{base}.{suffix}.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)


def run_form(cld_path, rawdir, form):
    base = os.path.splitext(os.path.basename(cld_path))[0]
    out = os.path.join(rawdir, f"{base}.{form}.json")
    if os.path.exists(out):
        print(out)
        return
    g = parse(open(cld_path, encoding="utf-8").read())
    rec = {"tool": f"stdraw-{form}", "graph": base, "n": len(g.nodes), "m": len(g.edges)}

    if form == "ortho":
        try:
            t0 = time.perf_counter()
            v4 = PlanarLayout(g, LayoutConfig()).run()
            dt = time.perf_counter() - t0
            nodes, routes, edges = to_scene(v4)
            rec.update(evaluate(nodes, routes, edges, dt, "stdraw-ortho", base))
        except NotPlanarError as e:
            rec.update({"status": "not_planar_skip", "why": str(e)})
        except Exception as e:
            rec.update({"status": "error", "why": repr(e)})
        save(rawdir, base, form, rec)
        print(out)
        return

    if form in ("auto", "auto-exact"):
        try:
            cfg = AutoConfig()
            t0 = time.perf_counter()
            v4 = recipes_run("auto-v2", g, cfg, "straight")
            dt = time.perf_counter() - t0
            nodes, routes, edges = to_scene(v4)
            exact_note = None
            if form == "auto-exact":
                try:
                    from stdraw.crossing_exact import crossing_exact
                    t1 = time.perf_counter()
                    ex = crossing_exact(g)
                    exact_note = {"cr": ex.get("crossing_number"),
                                  "proven_optimal": ex.get("proven_optimal"),
                                  "coverage": ex.get("coverage"),
                                  "gap": ex.get("gap"),
                                  "exact_time_s": round(time.perf_counter() - t1, 3)}
                except Exception as e:
                    exact_note = {"error": repr(e)}
            rec.update(evaluate(nodes, routes, edges, dt, f"stdraw-{form}", base,
                                extra={"exactness": exact_note}))
        except Exception as e:
            rec.update({"status": "error", "why": repr(e)})
        save(rawdir, base, form, rec)
        print(out)
        return

    raise ValueError(f"unknown form {form}")


if __name__ == "__main__":
    run_form(sys.argv[1], sys.argv[2], sys.argv[3])
