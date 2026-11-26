# -*- coding: utf-8 -*-
"""CLI: python -m stdraw layout <input.cld|input.json> [options]

Outputs (--outdir, default ./stdraw-out):
  graph.json          graph model (DSL->JSON normalization)
  layout.json         2D layout (delivered coordinates, all integers)
  geometry_report.json  11-check geometry self-report (CI gate form)
  certificate.json    five-metric + placement metrics + honest grading certificate
  loops_audit.json    loop semantics audit (lint)
  demo-2d.html        standalone rendering page (certificate embedded)
"""
import argparse
import json
import os
import sys

from . import __version__
from .model import Graph
from .dsl import parse, dumps
from .recipes import run as recipes_run
from .check import geometry_report_to_file
from .loops import loops_audit
from .limits import MAX_LAYOUT_NODES, HARD_CEILING_NODES, size_refusal
from .hints import apply_hints, has_hints
from .render import render_html, line_kind_summary
from .themes import DEFAULT_STATIC_THEME, THEMES
from .delivery import stamp_cli_deliverable


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
    Optionally edges: [{a, b, waypoints: [[x,y],...], anchors: {src, dst}}] —
    waypoints manually anchored by the user on demo-2d bend handles and
    explicitly designated standard anchors (endpoint drag / anchor click,
    viewer userAnchored semantics); --from-layout recomputes them under the
    same caliber (anchors land exactly on anchors.py coordinates and join
    the frozen set; the certificate records the anchor source honestly).
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
            "demo-2d.html"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["layout"],
                    help="subcommand: layout = full layout pipeline")
    ap.add_argument("input", help="input .cld (DSL) or .json (graph model)")
    ap.add_argument("--outdir", default="stdraw-out")
    ap.add_argument("--recipe", default="auto",
                    choices=["auto", "candidate-v1"],
                    help="layout recipe: auto = auto-v2 (default, straight/arc lines + new hard gates); "
                         "candidate-v1 = candidate pool (M1: structure analyzer + template sources + orchestrator "
                         "+ three-tier selection, not-worse-than-auto guard). "
                         "(The retired ortho-v1 recipe entry was removed by owner ruling, 2026-11-24.)")
    ap.add_argument("--linestyle", default="straight", choices=["straight", "arc"],
                    help="auto recipe line style (default straight; arc = all-arc preference). "
                         "This is the REQUEST; the delivered line-kind facts are printed "
                         "as 'line kinds ...' and live in certificate metrics.line_kind_counts")
    ap.add_argument("--no-loop-labels", dest="loop_labels", action="store_false",
                    help="suppress the annotation layer in demo-2d.html (loop-center "
                         "labels AND @delay marks, one switch): the certificate then "
                         "records loop_labels_clear / delay_marks_clear as N/A (excluded "
                         "from the pass count, never blocking; grade semantics unchanged)")
    ap.set_defaults(loop_labels=True)
    ap.add_argument("--pitch", type=int, default=None,
                    help="DEPRECATED pixel parameter (removal planned): row pitch px "
                         "(default 56; raise it for small graphs to pass the clearance gate, "
                         "parameter is transparent). Prefer the DSL semantic hints "
                         "@main / @order / @pair — see docs/agent-interface.md")
    ap.add_argument("--allow-oversize", action="store_true",
                    help="VALIDATION-SWEEP ESCAPE ONLY (benchmarks/tools/sweep_tiers.py): "
                         "extend the CLI size limit from %d to the engine capability "
                         "ceiling %d nodes. Nothing beyond %d nodes is ever laid out "
                         "(n<=20 scope ruling); agent callers should keep the default "
                         "structured refusal" % (MAX_LAYOUT_NODES, HARD_CEILING_NODES,
                                                 HARD_CEILING_NODES))
    ap.add_argument("--value-pad", type=float, default=None, metavar="PX",
                    help="extra per-side padding px for the value (second) text line "
                         "(default: historical baseline; raise it when long ticker/price "
                         "value strings overflow the planned card width)")
    ap.add_argument("--column-order", default=None, metavar="V1,V2,...",
                    help="DEPRECATED pixel parameter (removal planned; prefer @order): "
                         "v0.7.11 deterministic constraint (comb layouts): explicit "
                         "source-column internal order, top->bottom, as a hard "
                         "constraint (components keep their internal DFS order)")
    ap.add_argument("--hub-side", default=None, metavar="NODE=left|right,...",
                    help="DEPRECATED pixel parameter (removal planned): "
                         "v0.7.11 deterministic constraint (comb layouts): explicit "
                         "hub side assignment, e.g. wdc=left,stx=right")
    ap.add_argument("--name", default="", help="graph name (default: the DSL graph name)")
    ap.add_argument("--theme", default=DEFAULT_STATIC_THEME, choices=sorted(THEMES),
                    help="2D demo HTML theme (default: light = the current production face)")
    ap.add_argument("--exact", action="store_true",
                    help="WS2 exact crossing-number layer: B&B squeeze computes cr(G) and writes the "
                         "certificate exactness block (proven_optimal/gap; requires the optional "
                         "ortools dependency; honestly degraded when not installed)")
    ap.add_argument("--no-exact", dest="no_exact", action="store_true",
                    help="D4 fallback (jacky 2026-11-14 scope ruling, stdraw range n<=20): opt OUT "
                         "of the L1-default exact layer.  L1 planarized drawings then keep the "
                         "witness-marked drawing but stay honestly 'uncertified' "
                         "(three_account_consistent cannot pass without the oracle cr UB).")
    ap.add_argument("--mirror-symmetry", action="store_true",
                    help="anchors-as-prior S2: deterministic mirror-symmetry post-pass at the end "
                         "of stage 2 (left-right mirror edge pairs rewritten as exact geometric "
                         "mirrors x'=2c-x, hard-gate re-run with fail-loud exceptions). DEFAULT "
                         "OFF -- the flag off output is byte-identical to history")
    ap.add_argument("--from-layout", default=None, metavar="MANUAL_JSON",
                    help="manual layout JSON (the demo-2d.html \"Export layout\" product or a "
                         "layout.json subset: node id->x,y + viewBox). Runs the same routing + "
                         "certificate pipeline on manual coordinates; hard-gate caliber unchanged, "
                         "graded honestly")
    ap.add_argument("--interactive", action="store_true",
                    help="opt-in: ship demo-2d.html with the drag touch-up layer "
                         "(toolbar + live re-routing + waypoint handles + export). "
                         "Default output is the static page (SVG + certificate only); "
                         "layout.json / certificate.json honestly declare the delivery "
                         "face either way")
    a = ap.parse_args(argv)

    g = load_graph(a.input)
    os.makedirs(a.outdir, exist_ok=True)
    name = a.name or g.name or os.path.splitext(os.path.basename(a.input))[0]
    problems = g.validate()
    if problems:
        print("Structural validation failed:", *problems, sep="\n  ", file=sys.stderr)
        sys.exit(2)

    # T14: apply the semantic hints (@order reading order) — BEFORE the loop
    # audit and the graph.json write, so every delivered artifact follows the
    # declared reading sequence. Idempotent; hints-free graphs unchanged.
    if has_hints(g):
        g, _hint_applied = apply_hints(g)

    # T15: explicit size limit — refuse BEFORE any layout attempt (a
    # structured refusal instead of a costly run that ends in an honest but
    # late "uncertified"). --allow-oversize extends the service limit to the
    # engine capability ceiling for the validation sweeps; nothing beyond
    # the ceiling is ever laid out.
    limit = HARD_CEILING_NODES if a.allow_oversize else MAX_LAYOUT_NODES
    if len(g.nodes) > limit:
        refusal = size_refusal(g, limit=limit)
        rp = os.path.join(a.outdir, "refusal.json")
        with open(rp, "w", encoding="utf-8") as f:
            json.dump(refusal, f, ensure_ascii=False, indent=1)
        print(json.dumps(refusal, ensure_ascii=False, indent=1))
        print(f"[refused] {len(g.nodes)} nodes exceed the "
              f"{'capability ceiling' if a.allow_oversize else 'size limit'} "
              f"({limit}): structured refusal -> {rp} (split the graph by "
              "loops; see docs/agent-interface.md)", file=sys.stderr)
        sys.exit(3)

    # T14: deprecation warnings for the pixel-level parameters (kept working
    # this card; physical removal is the P3 subtraction card)
    _deprecated_used = []
    if a.pitch:
        _deprecated_used.append("--pitch")
    if a.column_order:
        _deprecated_used.append("--column-order")
    if a.hub_side:
        _deprecated_used.append("--hub-side")
    if _deprecated_used:
        print("[deprecated] " + ", ".join(_deprecated_used)
              + ": pixel-level parameter(s), kept working but scheduled for "
              "removal — prefer the DSL semantic hints @main / @order / @pair "
              "(docs/agent-interface.md)", file=sys.stderr)

    def w(fn, obj):
        p = os.path.join(a.outdir, fn)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        return p

    # Graph model + normalized DSL text
    p = w("graph.json", g.to_dict())
    with open(os.path.join(a.outdir, "graph.cld"), "w", encoding="utf-8") as f:
        f.write(dumps(g))
    print(f"[1/5] graph model OK: {len(g.nodes)} nodes / {len(g.edges)} edges / "
          f"{len(g.loops)} declared loops -> {p}")

    # Loop semantics audit (lint)
    lr = loops_audit(g)
    p = w("loops_audit.json", lr)
    print(f"[2/5] loop audit: declared {lr['summary']['declared']}, closed "
          f"{lr['summary']['closed']}, independently enumerated {lr['summary']['enumerated']}, "
          f"problems {lr['summary']['problems']} -> {p}")
    for pr in lr["problems"]:
        print("   lint:", pr)
    for _rh in lr.get("repair_hints") or []:
        print("   hint:", _rh["problem"], "->", _rh["fix"])

    # 2D layout
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
    if getattr(a, "mirror_symmetry", False):
        cfg.mirror_symmetry = True
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
    elif a.recipe == "candidate-v1":
        v4 = recipes_run("candidate-v1", g, cfg, a.linestyle)
    else:
        v4 = recipes_run("auto-v2", g, cfg, a.linestyle)
    labels = {n.id: n.label for n in g.nodes}
    values = {n.id: n.value for n in g.nodes if n.value}
    # Full CLI deliverable (demo-2d.html + certificate.json) is produced
    # below: the layout.json that ships with it is re-stamped as the CLI
    # deliverable (delivery="stdraw-cli", no warning) per the delivery
    # contract; `interactive` is true only when --interactive opted in.
    v4 = stamp_cli_deliverable(v4, interactive=a.interactive)
    p = w("layout.json", v4)
    meta = v4["meta"]
    print(f"[3/5] 2D layout (auto-v2, engine={meta['position_engine']}, "
          f"line kinds {line_kind_summary(v4)}): {v4['viewBox'][2]}x{v4['viewBox'][3]}, "
          f"{meta['rows']} rows -> {p}")
    rc = geometry_report_to_file(
        v4, os.path.join(a.outdir, "geometry_report.json"))
    exactness = None
    # D4 (jacky 2026-11-14): L1 planarized drawings default to
    # --exact (oracle cr UB participates in the three-account
    # check).  D4 fallback (jacky 2026-11-14 scope ruling, stdraw
    # range n<=20): --no-exact opts out; the certificate then stays
    # honestly 'uncertified' (three_account_consistent cannot pass
    # without the oracle cr UB).  Solve times over budget ->
    # report, never self-downgrade.
    _plz_meta = v4["meta"].get("planarization") or {}
    if (a.exact or _plz_meta.get("mode") == "L1") and not a.no_exact:
        # reuse the pipeline's oracle run (same computation; avoids a
        # duplicate B&B solve; falls back to a fresh run for direct
        # --exact on L0 drawings)
        exactness = _plz_meta.get("exactness")
        if exactness is None:
            from .crossing_exact import crossing_exact
            exactness = crossing_exact(g)
        print(f"      [exact] cr={exactness['crossing_number']} "
              f"proven_optimal={exactness['proven_optimal']} "
              f"lb={exactness['lb']} gap={exactness['gap']} "
              f"coverage={exactness['coverage']}")
    if _plz_meta.get("mode") == "L1":
        print(f"      [planarized] mode=L1 CAP={_plz_meta.get('cap')} "
              f"witnesses={_plz_meta.get('witness_count')} "
              f"(crossed-certified caliber, "
              "docs/planarization-degrade-contract.md)")
    cert = certificate_auto(scene_from_auto(v4), graph_name=name, layer="2D",
                            graph=g, exactness=exactness,
                            interactive="yes" if a.interactive else "no",
                            drag_layer="yes" if a.interactive else "no",
                            deliverable=True,
                            annotation_layer=a.loop_labels,
                            notes=(["deprecated pixel parameter(s) used: "
                                    + ", ".join(_deprecated_used)
                                    + " — prefer the DSL semantic hints "
                                      "@main / @order / @pair (removal planned)"]
                                   if _deprecated_used else None))
    p = w("certificate.json", cert)
    m = cert["metrics"]
    print(f"[4/5] certificate: crossings {m['crossings']} / box press {m['box_press_1px']} / "
          f"edge-box clearance {m['edge_box_min_clear']} / anchor violations {m['anchor_violations']} / "
          f"gap {m['min_card_gap']} / CV {m['spacing_cv']} -> "
          f"grade [{cert['grade']}] -> {p}")
    hp = os.path.join(a.outdir, "demo-2d.html")
    with open(hp, "w", encoding="utf-8") as f:
        f.write(render_html(v4, name, cert, lr, labels, values, a.theme,
                            loop_labels=a.loop_labels,
                            interactive=a.interactive))
    print(f"      demo -> {hp} (theme {a.theme}"
          + ("" if a.loop_labels else ", annotation layer off")
          + ("" if a.interactive else ", static (opt in with --interactive)") + ")")
    if rc:
        sys.exit(1)

    print("[5/5] done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
