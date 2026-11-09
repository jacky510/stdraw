# -*- coding: utf-8 -*-
"""CLI: python -m stdraw layout <input.cld|input.json> [options]

Outputs (--outdir, default ./stdraw-out):
  graph.json          graph model (DSL->JSON normalization)
  layout.json         2D layout (delivered coordinates, all integers)
  geometry_report.json  11-check geometry self-report (CI gate form)
  certificate.json    five-metric + placement metrics + honest grading certificate
  loops_audit.json    loop semantics audit (lint)
  demo-2d.html        standalone rendering page (certificate embedded)
  positions3d.json    3D per-solid assignment coordinates
  demo-3d.html        3D interactive page (needs ../assets/three.min.js relative path)
"""
import argparse
import json
import os
import sys

from . import __version__
from .model import Graph
from .dsl import parse, dumps
from .planar import PlanarLayout, NotPlanarError, LayoutConfig
from .recipes import run as recipes_run
from .check import geometry_report_to_file
from .metrics import certificate, scene_from_planar
from .loops import loops_audit
from .render import render_html
from .themes import DEFAULT_STATIC_THEME, THEMES
from .layout3d import SOLIDS, layout3d
from .render3d import render_3d_html
from .delivery import strip_delivery_metadata, stamp_cli_deliverable


def load_graph(path: str) -> Graph:
    if path.endswith(".json"):
        with open(path, encoding="utf-8") as f:
            return Graph.from_dict(json.load(f))
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return parse(text)


def load_manual_layout(path: str) -> dict:
    """Manual layout JSON -> the manual argument of layout().

    Accepts a full layout.json or the demo-2d.html "Export layout" subset
    ({nodes: {id: {x,y}|[x,y]}, viewBox}). source records the file name for
    meta provenance.
    Optionally edges: [{a, b, waypoints: [[x,y],...]}] — waypoints manually
    anchored by the user on demo-2d bend handles; --from-layout recomputes
    them under the same caliber.
    """
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if "nodes" not in raw:
        raise ValueError(f"{path}: manual layout is missing nodes (node id -> x,y)")
    return {"nodes": raw["nodes"], "viewBox": raw.get("viewBox"),
            "edges": raw.get("edges"),
            "source": os.path.basename(path)}


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="stdraw",
        description="stdraw — planarity-aware systems-thinking diagram engine "
                    "(text DSL in, certified diagram out)",
        epilog=(
            "Examples:\n"
            "  stdraw layout examples/limits-to-growth.cld --outdir out\n"
            "  python -m stdraw layout examples/limits-to-growth.cld --outdir out --pitch 62\n"
            "Outputs (--outdir, default ./stdraw-out): graph.json / layout.json /\n"
            "geometry_report.json / certificate.json / loops_audit.json /\n"
            "demo-2d.html / positions3d.json / demo-3d.html"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["layout", "layout-diff"],
                    help="subcommand: layout = full layout pipeline; layout-diff = auto vs manual three-layer diff")
    ap.add_argument("input", help="input .cld (DSL) or .json (graph model)")
    ap.add_argument("input2", nargs="?",
                    help="layout-diff second argument: manual layout layout.json")
    ap.add_argument("--outdir", default="stdraw-out")
    ap.add_argument("--recipe", default="auto", choices=["auto", "ortho"],
                    help="layout recipe: auto = auto-v2 (default, straight/arc lines + new hard gates); "
                         "ortho = ortho-v1 (orthogonal vertical-line constructive, behavior frozen, pin-safe)")
    ap.add_argument("--linestyle", default="straight", choices=["straight", "arc"],
                    help="auto recipe line style (default straight; arc = all-arc preference)")
    ap.add_argument("--skip-3d", action="store_true", help="run the 2D layer only")
    ap.add_argument("--solids", default="sphere,cube,tetra,cone",
                    help="3D solid list (comma separated)")
    ap.add_argument("--pitch", type=int, default=None,
                    help="row pitch px (default 56; raise it for small graphs to pass the clearance gate, parameter is transparent)")
    ap.add_argument("--value-pad", type=float, default=None, metavar="PX",
                    help="extra per-side padding px for the value (second) text line "
                         "(default: historical baseline; raise it when long ticker/price "
                         "value strings overflow the planned card width)")
    ap.add_argument("--column-order", default=None, metavar="V1,V2,...",
                    help="v0.7.11 deterministic constraint (comb layouts): explicit "
                         "source-column internal order, top->bottom, as a hard "
                         "constraint (components keep their internal DFS order)")
    ap.add_argument("--hub-side", default=None, metavar="NODE=left|right,...",
                    help="v0.7.11 deterministic constraint (comb layouts): explicit "
                         "hub side assignment, e.g. wdc=left,stx=right")
    ap.add_argument("--name", default="", help="graph name (default: the DSL graph name)")
    ap.add_argument("--theme", default=DEFAULT_STATIC_THEME, choices=sorted(THEMES),
                    help="2D demo HTML theme (default: light = the current production face)")
    ap.add_argument("--exact", action="store_true",
                    help="WS2 exact crossing-number layer: B&B squeeze computes cr(G) and writes the "
                         "certificate exactness block (proven_optimal/gap; requires the optional "
                         "ortools dependency; honestly degraded when not installed)")
    ap.add_argument("--from-layout", default=None, metavar="MANUAL_JSON",
                    help="manual layout JSON (the demo-2d.html \"Export layout\" product or a "
                         "layout.json subset: node id->x,y + viewBox). Runs the same routing + "
                         "certificate pipeline on manual coordinates; hard-gate caliber unchanged, "
                         "graded honestly")
    ap.add_argument("--compare-auto", action="store_true",
                    help="with --from-layout: also runs the automatic layout of the same graph into <outdir>-compare-auto/, "
                         "writing the dual-certificate comparison compare-auto.json (the aesthetic distance between engine and human)")
    ap.add_argument("--cld", default=None,
                    help="layout-diff: graph source (.cld/.json), enables the semantic layer (loop membership / cohesion)")
    ap.add_argument("--diff-out", default="layout-diff.json",
                    help="layout-diff: machine-readable JSON output path")
    a = ap.parse_args(argv)

    if a.command == "layout-diff":
        if not a.input2:
            print("layout-diff requires two arguments: <auto-layout.json> <manual-layout.json>",
                  file=sys.stderr)
            sys.exit(2)
        from .layoutdiff import main as diff_main
        sys.exit(diff_main([a.input, a.input2] +
                           (["--cld", a.cld] if a.cld else []) +
                           ["--out", a.diff_out]))

    g = load_graph(a.input)
    os.makedirs(a.outdir, exist_ok=True)
    deferred_exit = 0        # --compare-auto: emit the comparison report first, exit later on geometry fail
    name = a.name or g.name or os.path.splitext(os.path.basename(a.input))[0]
    problems = g.validate()
    if problems:
        print("Structural validation failed:", *problems, sep="\n  ", file=sys.stderr)
        sys.exit(2)

    def w(fn, obj):
        p = os.path.join(a.outdir, fn)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        return p

    # Graph model + normalized DSL text
    p = w("graph.json", g.to_dict())
    with open(os.path.join(a.outdir, "graph.cld"), "w", encoding="utf-8") as f:
        f.write(dumps(g))
    print(f"[1/6] graph model OK: {len(g.nodes)} nodes / {len(g.edges)} edges / "
          f"{len(g.loops)} declared loops -> {p}")

    # Loop semantics audit (lint)
    lr = loops_audit(g)
    p = w("loops_audit.json", lr)
    print(f"[2/6] loop audit: declared {lr['summary']['declared']}, closed "
          f"{lr['summary']['closed']}, independently enumerated {lr['summary']['enumerated']}, "
          f"problems {lr['summary']['problems']} -> {p}")
    for pr in lr["problems"]:
        print("   lint:", pr)

    # 2D layout
    if a.recipe == "ortho":
        cfg = LayoutConfig()
        if a.pitch:
            cfg.pitch = a.pitch
        eng = PlanarLayout(g, cfg)
        try:
            v4 = eng.run()
        except NotPlanarError as e:
            print(f"[3/6] 2D planar layer inapplicable: {e}")
            print("      honest degradation: skipping the 2D certificate (a replaceable layout-layer implementation is M1+)")
            v4 = None
        else:
            # ortho-v1 freeze-compat: the pipeline stamps delivery-contract
            # metadata (stdraw/delivery.py), but the CLI ortho layout.json is a
            # byte-frozen production pin (tests/baselines/, ci_checks gate A),
            # so the metadata is stripped here; the ortho delivery contract
            # travels on certificate.json (interactive / drag_layer) instead.
            v4 = strip_delivery_metadata(v4)
            labels = {n.id: n.label for n in g.nodes}
            values = {n.id: n.value for n in g.nodes if n.value}
            p = w("layout.json", v4)
            print(f"[3/6] 2D layout (ortho-v1 frozen recipe): {v4['viewBox'][2]}x"
                  f"{v4['viewBox'][3]}, {v4['meta']['rows']} rows -> {p}")
            # 11-check geometry self-report (runs on delivered coordinates)
            rc = geometry_report_to_file(
                v4, os.path.join(a.outdir, "geometry_report.json"))
            # Five-metric certificate (legacy caliber, byte-compatible)
            cert = certificate(scene_from_planar(v4), graph_name=name,
                               layer="2D",
                               notes=["unrelated lines piercing cards occlusion-style is allowed by design (cards are opaque)"],
                               interactive="yes", drag_layer="yes")
            p = w("certificate.json", cert)
            m = cert["metrics"]
            print(f"[4/6] certificate: crossings {m['crossings']} / true card piercings {m['occlusions_true_0px']} / "
                  f"gap {m['min_card_gap']} / alignment {m['row_align_rate']} / CV "
                  f"{m['spacing_cv']} -> grade [{cert['grade']}] -> {p}")
            hp = os.path.join(a.outdir, "demo-2d.html")
            with open(hp, "w", encoding="utf-8") as f:
                f.write(render_html(v4, name, cert, lr, labels, values, a.theme))
            print(f"      demo -> {hp} (theme {a.theme})")
            if rc:
                sys.exit(1)
    else:
        from .layout_auto import AutoConfig
        from .metrics import certificate_auto, scene_from_auto
        cfg = AutoConfig()
        if a.pitch:
            cfg.pitch = a.pitch
        if a.value_pad is not None:
            cfg.value_pad_extra = a.value_pad
        if a.column_order:
            cfg.column_order = [v.strip() for v in a.column_order.split(",") if v.strip()]
        if a.hub_side:
            cfg.hub_side = {}
            for _part in a.hub_side.split(","):
                if "=" in _part:
                    _k, _v = _part.split("=", 1)
                    _v = _v.strip().lower()
                    if _v in ("left", "right"):
                        cfg.hub_side[_k.strip()] = _v
        if a.from_layout:
            # Manual layout: same routing + certificate pipeline; hard-gate
            # caliber unchanged, graded honestly
            from .layout_auto import layout as _auto_layout_fn
            try:
                _manual = load_manual_layout(a.from_layout)
                v4 = _auto_layout_fn(g, cfg, a.linestyle, manual=_manual)
            except ValueError as e:
                print(f"manual layout unusable: {e}", file=sys.stderr)
                sys.exit(2)
        else:
            v4 = recipes_run("auto-v2", g, cfg, a.linestyle)
        labels = {n.id: n.label for n in g.nodes}
        values = {n.id: n.value for n in g.nodes if n.value}
        # Full CLI deliverable (demo-2d.html + certificate.json) is produced
        # below: the layout.json that ships with it is re-stamped interactive
        # (delivery="stdraw-cli", no warning) per the delivery contract.
        v4 = stamp_cli_deliverable(v4)
        p = w("layout.json", v4)
        meta = v4["meta"]
        print(f"[3/6] 2D layout (auto-v2, engine={meta['position_engine']}, "
              f"line style={meta['line_style']}): {v4['viewBox'][2]}x{v4['viewBox'][3]}, "
              f"{meta['rows']} rows -> {p}")
        rc = geometry_report_to_file(
            v4, os.path.join(a.outdir, "geometry_report.json"))
        exactness = None
        if a.exact:
            from .crossing_exact import crossing_exact
            exactness = crossing_exact(g)
            print(f"      [exact] cr={exactness['crossing_number']} "
                  f"proven_optimal={exactness['proven_optimal']} "
                  f"lb={exactness['lb']} gap={exactness['gap']} "
                  f"coverage={exactness['coverage']}")
        cert = certificate_auto(scene_from_auto(v4), graph_name=name, layer="2D",
                                graph=g, exactness=exactness,
                                interactive="yes", drag_layer="yes")
        p = w("certificate.json", cert)
        m = cert["metrics"]
        print(f"[4/6] certificate: crossings {m['crossings']} / box press {m['box_press_1px']} / "
              f"edge-box clearance {m['edge_box_min_clear']} / anchor violations {m['anchor_violations']} / "
              f"gap {m['min_card_gap']} / CV {m['spacing_cv']} -> "
              f"grade [{cert['grade']}] -> {p}")
        hp = os.path.join(a.outdir, "demo-2d.html")
        with open(hp, "w", encoding="utf-8") as f:
            f.write(render_html(v4, name, cert, lr, labels, values, a.theme))
        print(f"      demo -> {hp} (theme {a.theme})")
        if rc:
            if a.from_layout and a.compare_auto:
                deferred_exit = 1     # emit the comparison report first, exit code deferred
            else:
                sys.exit(1)

    # 3D per-solid assignment
    if not a.skip_3d:
        gd = {"nodes": [{"id": n.id, "label": n.label} for n in g.nodes],
              "edges": [{"a": e.a, "b": e.b, "p": e.polarity} for e in g.edges]}
        solids = [s.strip() for s in a.solids.split(",") if s.strip()]
        unknown = [s for s in solids if s not in SOLIDS]
        if unknown:
            print(f"unknown solids {unknown}, choose from {list(SOLIDS)}", file=sys.stderr)
            sys.exit(2)
        layouts = {s: layout3d(gd, s) for s in solids}
        p = w("positions3d.json",
              {s: layouts[s]["positions"] for s in solids})
        print(f"[5/6] 3D assignment: {solids} -> {p}")
        hp = os.path.join(a.outdir, "demo-3d.html")
        note = ("deterministic placement: slots + minimum-total-edge-length assignment; "
                "no crossing promise in 3D, projection crossings are solved by the camera")
        with open(hp, "w", encoding="utf-8") as f:
            f.write(render_3d_html(gd, layouts, name, note))
        print(f"      demo -> {hp} (must live in the same tree as assets/three.min.js relative path)")
    # ── compare-auto: automatic-layout comparison for the same graph (dual certificates) ──
    if a.from_layout and a.compare_auto:
        cmp_dir = a.outdir.rstrip("/\\") + "-compare-auto"
        print("\n-- compare-auto: automatic layout comparison for the same graph --")
        try:
            rc_cmp = main(["layout", a.input, "--outdir", cmp_dir, "--skip-3d"]
                          + (["--name", name] if name else []))
        except SystemExit as _e:                    # geometry fail -> exit 1, recorded honestly
            rc_cmp = _e.code

        def _cert(d):
            with open(os.path.join(d, "certificate.json"), encoding="utf-8") as f:
                return json.load(f)

        cert_m, cert_a = _cert(a.outdir), _cert(cmp_dir)
        keys = ("crossings", "box_press_1px", "edge_box_min_clear",
                "anchor_violations", "avg_edge_length", "row_align_rate",
                "min_card_gap", "spacing_cv", "column_snap24_rate")
        table = {}
        for k in keys:
            mv, av = cert_m["metrics"].get(k), cert_a["metrics"].get(k)
            delta = (mv - av) if isinstance(mv, (int, float)) and \
                isinstance(av, (int, float)) else None
            table[k] = {"manual": mv, "auto": av,
                        "delta_manual_minus_auto": delta}
        cmp_obj = {
            "tool": "stdraw --compare-auto", "graph": name,
            "manual_outdir": a.outdir, "auto_outdir": cmp_dir,
            "auto_cli_exit": rc_cmp,
            "metrics": table,
            "grade": {"manual": cert_m["grade"], "auto": cert_a["grade"]},
            "gates_passed": {"manual": cert_m["gates_passed"],
                             "auto": cert_a["gates_passed"]},
            "note": ("the gap is the aesthetic distance between engine and human "
                     "(the basis for future objective-function tuning); the hard-gate "
                     "caliber applies equally to manual layouts and grades honestly "
                     "without manual favors; the comparison automatic layout did not "
                     "run the --exact layer"),
        }
        p = os.path.join(a.outdir, "compare-auto.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cmp_obj, f, ensure_ascii=False, indent=1)
        print("  metric                      manual       auto")
        for k, v in table.items():
            print(f"  {k:<26} {str(v['manual']):>8} {str(v['auto']):>10}"
                  f"  D={v['delta_manual_minus_auto']}")
        print(f"  grade: manual={cert_m['grade']} / auto={cert_a['grade']}; "
              f"gates manual {cert_m['gates_passed']} / auto {cert_a['gates_passed']}"
              f" (auto_cli_exit={rc_cmp})")
        print(f"  -> {p}")

    print("[6/6] done.")
    return deferred_exit


if __name__ == "__main__":
    sys.exit(main())
