# Validate the classic corpus: every graph gets parse + lint audit (closure/polarity parity); zero problems required to enter the benchmark set
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from stdraw.dsl import parse          # noqa: E402
from stdraw.loops import loops_audit  # noqa: E402

bad = 0
for path in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "corpus", "classic", "*.cld"))):
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
print("BAD files:", bad)
sys.exit(1 if bad else 0)
