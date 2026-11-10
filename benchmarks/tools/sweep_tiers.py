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


def run_leg(tier, legdir, budget, log):
    os.makedirs(legdir, exist_ok=True)
    index_path = os.path.join(legdir, "sweep_index.json")
    index = {}
    if os.path.exists(index_path):
        index = json.load(open(index_path, encoding="utf-8"))
    graphs = graph_list(tier)
    log.write(f"=== sweep tier={tier} start {time.strftime('%F %T')} "
              f"graphs={len(graphs)} (resume: {len(index)} already done) ===\n")
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
    log = open(os.path.join(args.outdir, "sweep.log"), "a", encoding="utf-8")
    run_leg(args.tier, args.outdir, args.budget, log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
