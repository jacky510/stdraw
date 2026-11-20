# -*- coding: utf-8 -*-
"""Aggregate v0.8.2 re-measure outputs: stage-timing summary + per-graph table.

Reads benchmarks/raw/v082/*.auto.json and benchmarks/raw/v082/timing/*.txt
(STDRAW_TIMING=1 stderr captures), writes:
  benchmarks/raw/v082/timing-summary.md  (per-graph stage tables + aggregates)
  benchmarks/raw/v082/timing-summary.json (machine-readable)

Percent reconciliation: per graph, each stage's share of the reported total;
cross-graph aggregate = sum(stage ms) / sum(total ms). The sum of stage
shares per graph must be ~100% (the timing layer attributes every interval
to exactly one stage; small residues are rounding).
"""
import glob
import json
import os
import re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.abspath(os.path.join(HERE, "..", "raw", "v082"))
TIM = os.path.join(RAW, "timing")

HDR = re.compile(r"total (\d+) ms")
ROW = re.compile(r"^\s+(\S+)\s+(\d+(?:\.\d+)?) ms\s+(\d+(?:\.\d+)?)%")


def parse_timing(path):
    stages = []
    total = None
    for line in open(path, encoding="utf-8"):
        m = HDR.search(line)
        if m:
            total = int(m.group(1))
            continue
        m = ROW.match(line.rstrip("\r\n"))
        if m:
            stages.append((m.group(1), float(m.group(2)), float(m.group(3))))
    return total, stages


def main():
    recs = {}
    for p in sorted(glob.glob(os.path.join(RAW, "*.auto.json"))):
        base = os.path.splitext(os.path.basename(p))[0].replace(".auto", "")
        recs[base] = json.load(open(p, encoding="utf-8"))

    agg = defaultdict(float)      # stage -> summed ms
    grand_total = 0.0
    lines = ["# v0.8.2 auto re-measure — stage timing summary (STDRAW_TIMING=1)",
             "",
             "Per-graph stage tables (stderr captures in `timing/<graph>.txt`),",
             "then cross-graph aggregates. Percentages reconcile against the",
             "reported per-run total (timing layer attributes every interval to",
             "exactly one stage; engine determinism unaffected, REPORT §9).",
             ""]
    jout = {"per_graph": {}, "aggregate_pct": {}, "grand_total_ms": 0.0}

    for base in sorted(recs):
        tp = os.path.join(TIM, f"{base}.txt")
        r = recs[base]
        lines.append(f"## {base} (n={r.get('n')}, m={r.get('m')}, "
                     f"crossings={r.get('crossings')}, status={r.get('status')})")
        if not os.path.exists(tp):
            lines.append("- no timing capture (DNF or missing)")
            lines.append("")
            continue
        total, stages = parse_timing(tp)
        if not total or not stages:
            lines.append("- no parseable stage table in timing capture (DNF or empty stderr)")
            lines.append("")
            continue
        ssum = sum(ms for _, ms, _ in stages)
        reconc = (ssum / total * 100.0) if total else 0.0
        lines.append("")
        lines.append("| stage | ms | % of total |")
        lines.append("|---|---|---|")
        for s, ms, pct in stages:
            lines.append(f"| {s} | {ms:.1f} | {pct:.1f} |")
        lines.append(f"| **total** | **{total}** | 100.0 (stages sum {reconc:.1f}%) |")
        lines.append("")
        st = {s: ms for s, ms, _ in stages}
        for s, ms in st.items():
            agg[s] += ms
        grand_total += total
        jout["per_graph"][base] = {"total_ms": total, "stages_ms": st,
                                   "stages_sum_over_total_pct": round(reconc, 2),
                                   "metrics": {k: r.get(k) for k in
                                               ("crossings", "box_press",
                                                "clear_violations", "spacing_cv",
                                                "row_align_rate", "runtime_s",
                                                "status")}}

    lines.append("## Cross-graph aggregate (all graphs with timing captures)")
    lines.append("")
    lines.append("| stage | summed ms | % of grand total |")
    lines.append("|---|---|---|")
    for s, ms in sorted(agg.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {s} | {ms:.1f} | {ms / grand_total * 100:.1f} |")
    lines.append(f"| **grand total** | **{grand_total:.1f}** | 100.0 |")
    lines.append("")
    jout["aggregate_pct"] = {s: round(ms / grand_total * 100, 2)
                             for s, ms in agg.items()}
    jout["aggregate_ms"] = {s: round(ms, 1) for s, ms in agg.items()}
    jout["grand_total_ms"] = round(grand_total, 1)

    with open(os.path.join(RAW, "timing-summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(RAW, "timing-summary.json"), "w", encoding="utf-8") as f:
        json.dump(jout, f, ensure_ascii=False, indent=1)
    print(f"graphs={len(recs)} grand_total_ms={grand_total:.0f}")
    for s, ms in sorted(agg.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {s:<36} {ms:10.1f} ms {ms / grand_total * 100:5.1f}%")


if __name__ == "__main__":
    main()
