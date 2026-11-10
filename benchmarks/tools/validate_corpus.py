# Validate the corpus by validation tier (docs/validation-tiers.md).
#   Tier A (n<=20): classic corpus gets parse + lint audit (closure/polarity
#     parity); zero problems required. random n10/n20 get parse + tier listing.
#   Tier B (21<=n<=30): random n30 gets parse + tier listing (byte-gate is
#     sample-based; see sweep_tiers.py).
#   Tier C (n>30): retired — listed with tier: retired, NOT validated, never
#     enters any sweep (manifest.json carries the same "tier": "retired"
#     metadata; files stay in place, nothing deleted or moved).
# Exit code is driven by tier-A problems only (classic audit), as before.
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from stdraw.dsl import parse          # noqa: E402
from stdraw.loops import loops_audit  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

SAMPLE = {30: ("i00", "i04", "i09", "i14", "i19")}  # tier-B byte-gate sample


def tier_of(n):
    if n <= 20:
        return "A"
    if n <= 30:
        return "B"
    return "C"


bad = 0
print("== tier A: classic (full parse + lint audit) ==")
for path in sorted(glob.glob(os.path.join(REPO, "benchmarks", "corpus", "classic", "*.cld"))):
    g = parse(open(path, encoding="utf-8").read())
    lr = loops_audit(g)
    s = lr["summary"]
    status = "OK " if s["problems"] == 0 else "BAD"
    if s["problems"]:
        bad += 1
    print(f"{status} {os.path.basename(path):42s} n={len(g.nodes):2d} m={len(g.edges):2d} "
          f"declared={s['declared']} closed={s['closed']} enumerated={s['enumerated']} problems={s['problems']}")
    for p in lr["problems"]:
        print("     -", p)

manifest = json.load(open(os.path.join(REPO, "benchmarks", "manifest.json"), encoding="utf-8"))
print("== tier A: random n10/n20 (parse) ==")
print("== tier B: random n30 (parse; byte-gate sample: %s; full sweep only at ZCODE acceptance) ==" %
      " ".join(SAMPLE[30]))
print("== tier C: random n50 — retired, not validated, never swept ==")
for e in manifest["random_family"]["entries"]:
    path = os.path.join(REPO, "benchmarks", "corpus", "random", e["file"])
    t = e.get("tier") or tier_of(e["n"])
    if t == "C":
        declared = "retired" if e.get("tier") == "retired" else "MISSING-RETIRE-MARK"
        print(f"RETIRED {e['file']:42s} n={e['n']:2d} manifest_tier={declared}")
        if e.get("tier") != "retired":
            bad += 1
        continue
    g = parse(open(path, encoding="utf-8").read())
    status = "OK " if len(g.nodes) == e["n"] else "BAD"
    if status == "BAD":
        bad += 1
    mark = ""
    if t == "B" and os.path.splitext(e["file"])[0].rsplit("-", 1)[-1] in SAMPLE[30]:
        mark = " (byte-gate sample)"
    print(f"{status} tier-{t} {e['file']:42s} n={len(g.nodes):2d} m={len(g.edges):2d}{mark}")

print("BAD files:", bad)
sys.exit(1 if bad else 0)
