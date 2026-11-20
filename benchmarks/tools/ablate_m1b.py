# -*- coding: utf-8 -*-
"""M1-B ablation runner: planarization candidate source vs the M1-A pool.

Runs the candidate-v1 recipe for every longtail acceptance graph in TWO
checkouts (M1-A baseline tree vs M1-B tree) and reports, per graph:

  - pool composition (source records; the planarized source's outcome);
  - delivery mode + delivered certificate metrics + guard tuple;
  - layout bytes sha256 of both trees (negative byte protection: identical
    bytes on every graph that does not trigger the new source);
  - DROP-SOURCE CONTROL (marginal contribution): for every source that
    actually generated on a graph, the candidate-v1 run is repeated with
    that source removed from SOURCE_ORDER at runtime; the delivered mode
    and node-coordinate digest with vs without the source give a measured
    per-source marginal contribution (attribution evidence -- a gain may
    only be credited to a source whose removal changes the delivery).

Usage:
  python benchmarks/tools/ablate_m1b.py \
      --m1a-root <main checkout> --m1b-root <branch checkout> \
      --outdir <evidence dir> [--python <interpreter>] \
      [--drop-scope {triggers,all}]

Zero-drift check across trees + a positive-gain table on the non-planar
members. Deterministic library runs only (no wall-clock in results).
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

RUNNER = """
import hashlib, io, json, os, sys, contextlib
sys.path.insert(0, r'{root}')
_drop = os.environ.get('STDRAW_DROP_SOURCE', '')
if _drop:
    import stdraw.candidate_orchestrator as _orch
    import stdraw.candidate_sources as _src
    _kept = [s for s in _src.SOURCE_ORDER if s != _drop]
    _src.SOURCE_ORDER = _kept
    _orch.SOURCE_ORDER = _kept
from stdraw.dsl import parse
from stdraw.layout_auto import AutoConfig
from stdraw.recipes import run as recipes_run
from stdraw.metrics import certificate_auto, scene_from_auto
path = sys.argv[1]
with open(path, encoding='utf-8') as f:
    g = parse(f.read())
cfg = AutoConfig()
auto = recipes_run('auto-v2', g, cfg, 'straight')
v4 = recipes_run('candidate-v1', g, cfg, 'straight')
cp = (v4.get('meta') or {{}}).get('candidate_pool') or {{}}
delivery = cp.get('delivery') or {{}}
records = {{r['source']: r['outcome'] for r in
           (cp.get('orchestration') or {{}}).get('source_records', [])}}
pl_recs = [r for r in (cp.get('orchestration') or {{}}).get('source_records', [])
           if r['source'] == 'planarized']
nodes = {{v: [v4['nodes'][v]['x'], v4['nodes'][v]['y']]
          for v in sorted(v4['nodes'])}}
try:
    m = certificate_auto(scene_from_auto(v4))['metrics']
    cert = {{k: m.get(k) for k in ('crossings', 'box_press_1px',
                                   'min_card_gap', 'spacing_cv',
                                   'visual_crossings')}}
except Exception as e:
    cert = {{'error': str(e)}}
payload = {{
    'delivery_mode': delivery.get('mode'),
    'reason': delivery.get('reason'),
    'delivered_ids': delivery.get('ranked_ids'),
    'incumbent_planarization_mode':
        delivery.get('incumbent_planarization_mode'),
    'incumbent_guard_tuple': delivery.get('incumbent_guard_tuple'),
    'guard_tuple': (delivery.get('attempts') or [{{}}])[0].get('guard_tuple'),
    'source_outcomes': records,
    'planarized_record': pl_recs[0] if pl_recs else {{}},
    'auto_sha256': hashlib.sha256(json.dumps(
        auto, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest(),
    'cand_nodes_sha256': hashlib.sha256(json.dumps(
        nodes, sort_keys=True).encode('utf-8')).hexdigest(),
    'cand_full_sha256': hashlib.sha256(json.dumps(
        v4, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest(),
    'cert_metrics': cert,
}}
print('RESULT_JSON:' + json.dumps(payload, ensure_ascii=False))
"""


def run_tree(python, root, cld, timeout=600, drop_source=""):
    code = RUNNER.format(root=root)
    env = {**os.environ, "PYTHONUNBUFFERED": "1",
           "STDRAW_DROP_SOURCE": drop_source}
    r = subprocess.run([python, "-c", code, cld], capture_output=True,
                       text=True, timeout=timeout, cwd=root, env=env)
    line = next((l for l in r.stdout.splitlines()
                 if l.startswith("RESULT_JSON:")), None)
    if line is None:
        return {"error": f"rc={r.returncode}",
                "stderr_tail": r.stderr.strip()[-400:]}
    return json.loads(line[len("RESULT_JSON:"):])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--m1a-root", required=True)
    ap.add_argument("--m1b-root", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--corpus-dir", default=None,
                    help="defaults to <m1b-root>/benchmarks/corpus/longtail")
    ap.add_argument("--negatives", default="classic-cld,limits,hdd",
                    help="comma keys of the negative fixture graphs")
    ap.add_argument("--drop-scope", choices=("triggers", "all"),
                    default="triggers",
                    help="which graphs get the per-source drop-source "
                         "control reruns (triggers = graphs where the "
                         "planarized source generated; all = every graph)")
    args = ap.parse_args()

    corpus = args.corpus_dir or os.path.join(
        args.m1b_root, "benchmarks", "corpus", "longtail")
    os.makedirs(args.outdir, exist_ok=True)

    negatives_map = {
        "classic-cld": os.path.join(args.m1b_root,
                                    "examples/classic-cld-growth-and-burden.cld"),
        "limits": os.path.join(args.m1b_root,
                               "examples/limits-to-growth.cld"),
        "hdd": os.path.join(args.m1b_root,
                            "tests/data/hdd-wide-tickers.cld"),
    }
    clds = sorted(os.path.join(corpus, f)
                  for f in os.listdir(corpus) if f.endswith(".cld"))
    neg_clds = [negatives_map[k] for k in args.negatives.split(",")
                if k in negatives_map]

    rows = []
    for cld in clds + neg_clds:
        name = os.path.basename(cld)[:-4]
        is_negative = cld in neg_clds
        a = run_tree(args.python, args.m1a_root, cld)
        b = run_tree(args.python, args.m1b_root, cld)
        auto_same = (not a.get("error") and not b.get("error")
                     and a["auto_sha256"] == b["auto_sha256"])
        coords_same = (not a.get("error") and not b.get("error")
                       and a["cand_nodes_sha256"] == b["cand_nodes_sha256"])
        rows.append({"graph": name, "negative_fixture": is_negative,
                     "cld_path": cld,
                     "m1a": a, "m1b": b, "auto_bytes_identical": auto_same,
                     "cand_coords_identical": coords_same})
        print(f"[{name}] auto_identical={auto_same} "
              f"coords_identical={coords_same} "
              f"m1a_mode={a.get('delivery_mode')} "
              f"m1b_mode={b.get('delivery_mode')} "
              f"m1b_planarized={b.get('source_outcomes', {}).get('planarized')}")

    # ---- drop-source control: measured per-source marginal contribution ----
    # For every source that actually generated, rerun candidate-v1 on the
    # M1-B tree with that source removed from SOURCE_ORDER at runtime and
    # record whether the delivery changes (mode and/or delivered node
    # coordinates). A gain may only be credited to a source whose removal
    # changes the delivery -- this column is the attribution evidence.
    drop_rows = []
    for r in rows:
        gen = sorted(s for s, outcome
                     in (r["m1b"].get("source_outcomes") or {}).items()
                     if outcome == "generated")
        if not gen:
            continue
        if args.drop_scope == "triggers" \
                and r["m1b"].get("source_outcomes", {}).get("planarized") \
                != "generated":
            continue
        for src in gen:
            d = run_tree(args.python, args.m1b_root, r["cld_path"],
                         drop_source=src)
            changed = (not d.get("error") and not r["m1b"].get("error")
                       and (d.get("delivery_mode")
                            != r["m1b"].get("delivery_mode")
                            or d.get("cand_nodes_sha256")
                            != r["m1b"].get("cand_nodes_sha256")))
            drop_rows.append({
                "graph": r["graph"], "dropped_source": src,
                "delivery_mode_with": r["m1b"].get("delivery_mode"),
                "delivered_ids_with": r["m1b"].get("delivered_ids"),
                "delivery_mode_without": d.get("delivery_mode"),
                "delivered_ids_without": d.get("delivered_ids"),
                "reason_without": d.get("reason"),
                "nodes_sha256_with": r["m1b"].get("cand_nodes_sha256"),
                "nodes_sha256_without": d.get("cand_nodes_sha256"),
                "delivery_changed": changed,
                "error": d.get("error"),
            })
            print(f"[drop] {r['graph']} -{src}: "
                  f"{r['m1b'].get('delivery_mode')} -> "
                  f"{d.get('delivery_mode')} changed={changed}")

    out = {"rows": rows, "m1a_root": args.m1a_root, "m1b_root": args.m1b_root,
           "drop_scope": args.drop_scope, "drop_rows": drop_rows,
           "protection_caliber":
               "auto-v2 recipe bytes identical + candidate-v1 delivered "
               "node coordinates identical on no-trigger graphs "
               "(candidate-v1 provenance honestly records the new source's "
               "disabled_by_rule record, so full-layout bytes differ there "
               "by design — same caliber as the M1-A acceptance)"}
    with open(os.path.join(args.outdir, "ablation-raw.json"), "w",
              encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    triggers = [r for r in rows if not r["negative_fixture"]
                and r["m1b"].get("source_outcomes", {}).get("planarized")
                == "generated"]
    print("\n== summary ==")
    print("graphs:", len(rows), "| negative fixtures:",
          sum(1 for r in rows if r["negative_fixture"]))
    neg_rows = [r for r in rows if r["negative_fixture"]]
    planar_neg = [r for r in rows if not r["negative_fixture"]
                  and r["m1b"].get("source_outcomes", {}).get("planarized")
                  != "generated"]
    no_trigger = neg_rows + planar_neg
    print("auto-v2 recipe bytes identical (all graphs):",
          f"{sum(1 for r in rows if r['auto_bytes_identical'])}/{len(rows)}")
    print("candidate-v1 coords identical (no-trigger graphs):",
          f"{sum(1 for r in no_trigger if r['cand_coords_identical'])}"
          f"/{len(no_trigger)}")
    print("planarized-source trigger graphs:", len(triggers))
    for r in triggers:
        am, bm = r["m1a"].get("cert_metrics") or {}, \
            r["m1b"].get("cert_metrics") or {}
        print(f"  {r['graph']}: crossings {am.get('crossings')} -> "
              f"{bm.get('crossings')} | visual {am.get('visual_crossings')} -> "
              f"{bm.get('visual_crossings')} | press "
              f"{am.get('box_press_1px')} -> {bm.get('box_press_1px')} | "
              f"mode {r['m1a'].get('delivery_mode')} -> "
              f"{r['m1b'].get('delivery_mode')} | planarized_cands="
              f"{r['m1b'].get('planarized_record', {}).get('candidates')}")
    print("\n== per-source marginal contribution (drop-source control) ==")
    by_source = {}
    for d in drop_rows:
        by_source.setdefault(d["dropped_source"], []).append(d)
    for src in sorted(by_source):
        entries = by_source[src]
        winning = [d["graph"] for d in entries if d["delivery_changed"]]
        print(f"  {src}: {len(entries)} graph(s) controlled, "
              f"delivery changes on {len(winning)}: {winning or 'none'} "
              f"-> measured marginal contribution "
              f"{'>0' if winning else '=0'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
