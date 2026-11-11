# Tiered byte-gate sweep tool (docs/validation-tiers.md, rulings D0/D1/D4).
#
# Tiers:
#   A    full byte-gate leg, 61 graphs: classic 21 (corpus/classic 19 + the
#        2 example rendering entries examples/limits-to-growth.cld +
#        examples/classic-cld-growth-and-burden.cld — the docs quickstart
#        commands; hdd-supply-chain.cld is not a rendering entry) +
#        random n10 x20 + random n20 x20
#   B    tier-B sample leg, 5 graphs: random n30 i00/i04/i09/i14/i19
#   full the card-closure gate (ruling D4) = A + B, 66 graphs; run once per
#        card at closure, never on CI
#   C    retired (random n50) — refused by design, never swept; the corpus
#        stays in place with "tier": "retired" metadata in manifest.json
#
# Each invocation runs one leg: for every graph, `python -m stdraw layout
# <cld> --outdir <legdir>/<base> --skip-3d` under a wall-clock budget, then
# records sha256 of every produced file into <legdir>/sweep_index.json.
# Re-enterable (T6 discipline): graphs already recorded in the index are
# skipped; progress is appended to <legdir>/sweep.log.
#
# Dual-leg compare (byte-zero-drift gate): run one leg on the before-change
# baseline and one on the after-change tree, then
#   python sweep_tiers.py --tier <T> --outdir <leg2> --compare <leg1>/sweep_index.json
# Exit 0 only when every recorded file matches byte-for-byte.
import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

SAMPLE_N30 = ("i00", "i04", "i09", "i14", "i19")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def graph_list(tier):
    graphs = []  # (label, cld_path)
    if tier in ("A", "full"):
        classic = sorted(glob.glob(os.path.join(REPO, "benchmarks", "corpus", "classic", "*.cld")))
        # the 2 example rendering entries (docs quickstart commands) — see header note
        for name in ("limits-to-growth.cld", "classic-cld-growth-and-burden.cld"):
            classic.append(os.path.join(REPO, "examples", name))
        for p in classic:
            graphs.append(("classic", p))
    random_dir = os.path.join(REPO, "benchmarks", "corpus", "random")
    for p in sorted(glob.glob(os.path.join(random_dir, "*.cld"))):
        base = os.path.splitext(os.path.basename(p))[0]  # random-nXX-iYY
        parts = base.split("-")
        n = int(parts[1][1:])
        idx = parts[2]
        if tier in ("A", "full") and n <= 20:
            graphs.append(("random", p))
        elif tier in ("B", "full") and n == 30 and idx in SAMPLE_N30:
            graphs.append(("random", p))
    return graphs


def engine_caliber():
    """Which placement engine the sweep interpreter actually exercises.

    The child renders run `sys.executable -m stdraw layout ...` — the same
    interpreter as this process — so ortools availability HERE decides
    whether the layered cp-sat engine or the construct fallback engine
    produces every recorded result.  Recorded into sweep_index.json so a
    zero-regression table can never again silently compare two different
    engine calibers (blind spot measured on card t_875e2949's sweep vs
    the ortools-path visual acceptance t_47e514bb).
    """
    try:
        import ortools  # noqa: F401
        return "cp-sat-layered"
    except Exception:
        return "fallback-construct"


def run_leg(tier, legdir, budget, log):
    os.makedirs(legdir, exist_ok=True)
    index_path = os.path.join(legdir, "sweep_index.json")
    index = {}
    if os.path.exists(index_path):
        index = json.load(open(index_path, encoding="utf-8"))
    graphs = graph_list(tier)
    calib = engine_caliber()
    prev_meta = index.get("_meta") or {}
    mixed = (bool(prev_meta)
             and prev_meta.get("engine_caliber") not in (None, calib))
    index["_meta"] = {
        "engine_caliber": calib,
        "interpreter": sys.executable,
        "recorded_at": time.strftime("%F %T"),
        "mixed_caliber_resume": mixed or bool(prev_meta.get("mixed_caliber_resume")),
        "prev_caliber": prev_meta.get("engine_caliber"),
        "note": ("per-graph engine in rec['engine'] (layout.json meta.position_engine); "
                 "byte-compare only walks graph keys, _meta is annotation-only"),
    }
    if mixed:
        print(f"WARNING: leg resumed under caliber {calib} but earlier graphs were "
              f"recorded under {prev_meta.get('engine_caliber')} — this index mixes "
              f"engine calibers; do NOT byte-compare it as one caliber.")
        log.write(f"WARNING mixed-caliber resume: now={calib} prev={prev_meta.get('engine_caliber')}\n")
    if calib == "fallback-construct":
        banner = ("DEGRADED ENGINE CALIBER: ortools absent in %s — every graph below renders "
                  "with the construct FALLBACK engine; the cp-sat layered path is NOT covered "
                  "by this leg (known blind spot: t_875e2949 sweep vs t_47e514bb acceptance). "
                  "Rerun under an ortools interpreter before quoting zero-regression numbers."
                  % sys.executable)
        print("!" * 24 + " DEGRADED " + "!" * 24)
        print(banner)
        log.write(banner + "\n")
    else:
        print(f"engine caliber: {calib} (layered engine real path covered)")
    log.write(f"=== sweep tier={tier} start {time.strftime('%F %T')} "
              f"graphs={len(graphs)} caliber={calib} interpreter={sys.executable} "
              f"(resume: {len(index)} already done) ===\n")
    log.flush()
    for fam, cld in graphs:
        base = os.path.splitext(os.path.basename(cld))[0]
        key = f"{fam}/{base}"  # family-qualified: example entries share stems with corpus classic
        if key in index:
            log.write(f"skip {key} (recorded)\n")
            continue
        outdir = os.path.join(legdir, fam, base)
        t0 = time.time()
        cmd = [sys.executable, "-m", "stdraw", "layout", cld,
               "--outdir", outdir, "--skip-3d"]
        try:
            p = subprocess.run(cmd, capture_output=True, cwd=REPO, timeout=budget)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc = "TIMEOUT"
        rec = {"tier": tier, "family": fam, "src": cld, "rc": rc, "elapsed_s": round(time.time() - t0, 1),
               "files": {}}
        if rc == 0 and os.path.isdir(outdir):
            lay_p = os.path.join(outdir, "layout.json")
            if os.path.isfile(lay_p):
                try:
                    rec["engine"] = (json.load(open(lay_p, encoding="utf-8"))
                                     .get("meta", {}).get("position_engine", "unknown"))
                except Exception:
                    rec["engine"] = "unknown"
                if rec["engine"] != "cp-sat" and calib == "cp-sat-layered":
                    log.write(f"WARN {key}: engine caliber cp-sat-layered expected "
                              f"but layout delivered position_engine={rec['engine']}\n")
            for f in sorted(os.listdir(outdir)):
                fp = os.path.join(outdir, f)
                if os.path.isfile(fp):
                    rec["files"][f] = sha256_file(fp)
        index[key] = rec
        with open(index_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(index, f, indent=1, sort_keys=True)
            f.write("\n")
        log.write(f"{key} rc={rc} {rec['elapsed_s']}s files={len(rec['files'])}\n")
        log.flush()
    log.write(f"=== sweep tier={tier} done {time.strftime('%F %T')} ===\n")
    log.close()
    return index


def compare(index_path_a, index_path_b):
    a = json.load(open(index_path_a, encoding="utf-8"))
    b = json.load(open(index_path_b, encoding="utf-8"))
    # annotation keys (caliber/interpreter) are not graph records — never compared
    meta_a, meta_b = a.pop("_meta", None), b.pop("_meta", None)
    for label, m in (("leg1", meta_a), ("leg2", meta_b)):
        if m:
            print(f"{label} caliber: {m.get('engine_caliber')} interpreter: {m.get('interpreter')}")
    if (meta_a and meta_b
            and meta_a.get("engine_caliber") != meta_b.get("engine_caliber")):
        print("WARNING: the two legs were produced under DIFFERENT engine calibers "
              "(%s vs %s) — byte comparisons across calibers are meaningless "
              "(t_875e2949 blind spot). Re-run both legs under the same interpreter."
              % (meta_a.get("engine_caliber"), meta_b.get("engine_caliber")))
    missing = sorted(set(a) - set(b)) + sorted(set(b) - set(a))
    drift = []
    for base in sorted(set(a) & set(b)):
        fa, fb = a[base]["files"], b[base]["files"]
        if set(fa) != set(fb):
            drift.append((base, "file-set differs", sorted(set(fa) ^ set(fb))))
            continue
        for f in sorted(fa):
            if fa[f] != fb[f]:
                drift.append((base, f, f"{fa[f][:12]} != {fb[f][:12]}"))
    print(f"graphs: leg1={len(a)} leg2={len(b)}")
    print(f"byte-drift entries: {len(drift)}")
    for base, f, detail in drift[:50]:
        print(f"  DRIFT {base} :: {f} :: {detail}")
    for base in missing:
        print(f"  MISSING {base}")
    ok = not drift and not missing
    print("RESULT:", "ZERO-DRIFT (PASS)" if ok else "DRIFT/MISSING (FAIL)")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="tiered byte-gate sweep (A/B/full; C retired)")
    ap.add_argument("--tier", required=True, choices=["A", "B", "full", "C"],
                    help="A=61 graphs, B=n30 sample 5, full=A+B closure gate (D4), "
                         "C=retired, refused")
    ap.add_argument("--outdir", required=True, help="leg output dir (holds sweep_index.json)")
    ap.add_argument("--budget", type=int, default=900,
                    help="per-graph wall-clock budget seconds (default 900)")
    ap.add_argument("--compare", default="",
                    help="another leg's sweep_index.json: byte-compare and exit")
    args = ap.parse_args(argv)

    if args.tier == "C":
        print("tier C (n>30, random n50) is RETIRED by ruling D1: never swept. "
              "Corpus stays in place with tier: retired metadata.")
        return 2
    if args.compare:
        return compare(os.path.join(args.outdir, "sweep_index.json"), args.compare)
    os.makedirs(args.outdir, exist_ok=True)   # pre-existing crash fix: log open() before run_leg's makedirs
    log = open(os.path.join(args.outdir, "sweep.log"), "a", encoding="utf-8")
    run_leg(args.tier, args.outdir, args.budget, log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
