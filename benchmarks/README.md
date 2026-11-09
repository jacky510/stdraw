# benchmarks — stdraw benchmark suite and baseline comparison

Corpus: `corpus/classic/` (19 classic CLDs, lint all green) + `corpus/random/` (80 fixed-seed sparse graphs, n∈{10,20,30,50}×20). Listing: `manifest.json`.
Run: `tools/run_all.py` (re-entrant; budget and DNF protocol in `REPORT.md §2`).
Aggregate: `tools/collect.py` → `REPORT.md` (per-graph tables).

## Summary table (classic means; random family aggregated by n in REPORT §4)

| Tool | Crossings | Box-press | Clearance viol. | CV | Row-align | Runtime(s) |
|---|---|---|---|---|---|---|
| stdraw-ortho (constructive) | 0.0 | 1.4 | 1.7 | 0.296 | 0.48 | 0.01 |
| stdraw-auto (WS3 routing) | 0.2 | 0.0 | 0.0 | 0.133 | 0.34 | 10.02 |
| stdraw-auto+WS2 (exact layer) | 0.2 | 0.0 | 0.0 | 0.133 | 0.34 | 10.42 |
| Graphviz dot | 0.2 | 0.1 | 2.6 | 0.139 | 0.34 | 0.03 |
| Graphviz neato | 0.1 | 1.2 | 3.1 | 0.080 | 0.05 | 0.06 |
| Graphviz sfdp | 0.3 | 0.0 | 0.0 | 0.131 | 0.37 | 0.03 |
| ELK layered | 0.1 | 0.0 | 3.0 | 0.208 | 0.41 | 0.07 |

Honest boundary: the random-family n≥20 all-DNF was fixed by WS5 (CP-SAT deterministic time budget + exact-equivalence routing speedup; root cause and fix record in `REPORT.md §5`), but runtime remains 2–3 orders of magnitude slower than the baselines and random-family box-press/clearance are not 0; OGDF was not run on the same problem (§6). "Best"-claim wording follows REPORT §8 and is written into the repo README only after default's review.

