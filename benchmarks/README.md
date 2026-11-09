# benchmarks — stdraw benchmark suite and baseline comparison

Corpus: `corpus/classic/` (19 classic CLDs, lint all green) + `corpus/random/` (80 fixed-seed sparse graphs, n∈{10,20,30,50}×20). Listing: `manifest.json`.
Run: `tools/run_all.py` (re-entrant; budget and DNF protocol in `REPORT.md §2`).
Aggregate: `tools/collect.py` → `REPORT.md` (per-graph tables).

## Summary table (classic means; random family aggregated by n in REPORT §4)

| Tool | Crossings | Box-press | Clearance viol. | CV | Row-align | Runtime(s) |
|---|---|---|---|---|---|---|
| stdraw-ortho (constructive) | — | — | — | — | — | — |
| stdraw-auto (WS3 routing) | — | — | — | — | — | — |
| stdraw-auto+WS2 (exact layer) | — | — | — | — | — | — |
| Graphviz dot | — | — | — | — | — | — |
| Graphviz neato | — | — | — | — | — | — |
| Graphviz sfdp | — | — | — | — | — | — |
| ELK layered | — | — | — | — | — | — |

Honest boundary: the random-family n≥20 all-DNF was fixed by WS5 (CP-SAT deterministic time budget + exact-equivalence routing speedup; root cause and fix record in `REPORT.md §5`), but runtime remains 2–3 orders of magnitude slower than the baselines and random-family box-press/clearance are not 0; OGDF was not run on the same problem (§6). "Best"-claim wording follows REPORT §8 and is written into the repo README only after default's review.

