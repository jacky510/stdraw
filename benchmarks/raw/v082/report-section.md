## §10 v0.8.2 re-measure — current engine (pattern-chain era)

Full-corpus auto re-run on the v0.8.2 engine (main 310a6d9),
branch `p0/…-remeasure`; raw evidence in `raw/v082/` (per-graph JSON
+ `timing/<graph>.txt` stderr captures + `timing-summary.{md,json}`).
Driver: `tools/run_v082_auto.py`; aggregator: `tools/collect_v082_timing.py`.
Calibers unchanged from §2 (classic 300s / random n≤10 350s / n≥20 100s;
engine-side deterministic budgets, no wall-clock deadlines). Scope note:
the classic directory now holds **20** graphs (`success-to-the-successful`
joined 2026-11-11, after the 19-graph WS4 sweep); all 20 are re-measured
here. Per the n≤20 hard scope, random n30/n50 are **not re-run** — their
§4 rows keep the WS4/WS5 historical caliber. The timing layer is the
observational T3 layer (REPORT §9): layout bytes are unaffected.

### §10.1 classic corpus (20 graphs) — stdraw-auto, current engine

| Graph | n | m | Crossings | Box-press | Clearance viol. | CV | Row-align | Runtime(s) | Status |
|---|---|---|---|---|---|---|---|---|---|
| arms-race | 4 | 4 | 0 | 0 | 0 | 0.000 | 0.50 | 2.29 | ok |
| brand-flywheel | 6 | 8 | 0 | 0 | 0 | 0.000 | 0.67 | 0.99 | ok |
| bullwhip | 5 | 6 | 0 | 0 | 0 | 0.230 | 0.40 | 0.69 | ok |
| burnout-attrition | 5 | 6 | 0 | 0 | 0 | 0.230 | 0.40 | 0.67 | ok |
| classic-cld-growth-and-burden | 8 | 13 | 0 | 0 | 0 | 0.128 | 0.62 | 1.93 | ok |
| debt-spiral | 5 | 6 | 0 | 0 | 0 | 0.000 | 0.80 | 0.67 | ok |
| eroding-goals | 5 | 6 | 0 | 0 | 0 | 0.000 | 0.80 | 0.69 | ok |
| fishing-collapse | 6 | 9 | 0 | 0 | 0 | 0.264 | 0.67 | 1.23 | ok |
| fixes-that-fail | 4 | 5 | 0 | 0 | 0 | 0.266 | 0.50 | 0.56 | ok |
| induced-demand | 5 | 7 | 0 | 0 | 0 | 0.000 | 0.80 | 1.09 | ok |
| learning-flywheel | 4 | 5 | 0 | 0 | 0 | 0.308 | 0.50 | 0.63 | ok |
| limits-to-growth | 5 | 7 | 0 | 0 | 0 | 0.253 | 0.40 | 0.73 | ok |
| population-logistic | 4 | 6 | 0 | 0 | 0 | 0.242 | 0.50 | 0.88 | ok |
| renewable-resource | 5 | 7 | 0 | 0 | 0 | 0.000 | 0.40 | 0.91 | ok |
| shifting-the-burden | 5 | 8 | 0 | 0 | 0 | 0.000 | 0.80 | 1.13 | ok |
| soil-erosion | 6 | 8 | 0 | 0 | 0 | 0.272 | 0.67 | 2.41 | ok |
| success-to-the-successful | 6 | 10 | 0 | 0 | 0 | 0.250 | 0.00 | 108.89 | ok |
| tragedy-of-the-commons | 5 | 6 | 0 | 0 | 0 | 0.326 | 0.40 | 1.10 | ok |
| urban-migration | 6 | 8 | 0 | 0 | 0 | 0.275 | 0.50 | 0.88 | ok |
| wage-price-spiral | 5 | 6 | 0 | 0 | 0 | 0.000 | 0.80 | 0.73 | ok |

(Loop counts per graph: see the §3 headers — classic graph set
identical to the WS4 sweep apart from the added 20th graph.)

Classic means (current engine, n=20 ok / 20):

| Metric | mean |
|---|---|
| Crossings | 0.000 |
| Box-press | 0.000 |
| Clearance viol. | 0.000 |
| CV | 0.152 |
| Row-align | 0.556 |
| Runtime(s) | 6.46 |

### §10.2 The three historical 1-crossing graphs — confirmed 0

| Graph | WS4/WS5 crossings (§3) | v0.8.2 crossings | CV | runtime(s) |
|---|---|---|---|---|
| classic-cld-growth-and-burden | 1 | 0 | 0.128 | 1.93 |
| limits-to-growth | 1 | 0 | 0.253 | 0.73 |
| urban-migration | 1 | 0 | 0.275 | 0.88 |

Matches the plan-doc F1 claim (0 crossings, grade=best, CV
0.128/0.253/0.275) — the old §3 auto rows for these graphs are the
pre-pattern-chain engine and are superseded, not wrong-in-table.

### §10.3 Stage timing — bottleneck reconciliation

Timing-capture inclusion rule: `raw/v082/timing/` holds 38 stderr
captures for the 60-graph re-run scope (20 classic + 20 random n10 +
20 random n20); a capture enters the aggregation only when it carries
a parseable `total N ms` header line. 37 captures qualify and form
the 37-graph timing caliber aggregated below; `random-n20-i09`
(killed at the 100s n20 budget) captured a stderr fragment without
a total line and is excluded; the 22 DNF graphs produced no capture
at all and are likewise not aggregated. Full per-graph tables in
`raw/v082/timing-summary.md`; aggregate shares:

| stage | summed ms | % of grand total |
|---|---|---|
| route_final | 310737.4 | 41.2 |
| polish_gated_reorder | 241782.9 | 32.1 |
| ring_reposition | 104211.1 | 13.8 |
| planarized_l1 | 41252.3 | 5.5 |
| delivery | 14205.2 | 1.9 |
| anchor_snap.snap | 13421.9 | 1.8 |
| mode_detection_trials | 9798.2 | 1.3 |
| placement_cp_sat | 6090.5 | 0.8 |
| repair:coincide | 3786.7 | 0.5 |
| repair:lens_joint_reassign | 2981.2 | 0.4 |
| anchor_snap.gate_eval_post | 2356.9 | 0.3 |
| anchor_snap.gate_eval_pre | 2088.3 | 0.3 |
| card_metrics | 807.1 | 0.1 |
| repair:midband | 139.5 | 0.0 |
| repair:fan_spread | 71.4 | 0.0 |
| repair:arrival_flip_post | 42.6 | 0.0 |
| repair:arrival_flip_pre | 7.0 | 0.0 |
| repair:mutual_straight | 2.2 | 0.0 |
| layering | 0.1 | 0.0 |
| manual_injection | 0.0 | 0.0 |
| **grand total** | **753785.0** | 100.0 |

Reconciliation answer (which side is the bottleneck):

- Stage-class split: routing/other 99.2% + CP-SAT 0.8%.
- Single dominant stage: `route_final` at 41.2% of the
  grand total. **The bottleneck is NOT the CP-SAT proof segment** —
  placement_cp_sat is 0.8% of the wall;
  the wall sits in the routing/reposition/polish side (§9.3 finding 1
  already pointed there; this full-corpus sweep confirms it corpus-wide).

Timing variance caveat: same-machine re-runs of identical graphs
scatter 0.49-0.90x wall-to-wall, so absolute-runtime comparisons
against this table should carry a ±2x noise band.

### §10.4 random family re-measure (n10 + n20; n30/n50 not re-run)

| family | graphs ok | mean crossings | mean box-press | mean clearance viol. | mean CV | mean row-align | median runtime(s) | DNF |
|---|---|---|---|---|---|---|---|---|
| n10 | 15/20 | 1.4 | 0.00 | 0.00 | 0.224 | 0.73 | 28.25 | 5 |
| n20 | 2/20 | 2.0 | 0.00 | 0.00 | 0.818 | 0.30 | 14.29 | 18 |

Baselines (Graphviz/ELK) and stdraw-ortho rows are unchanged from §4
(outside this card's re-run scope; engine unchanged for them).

Honest notes on the DNF counts (wall-budget timeouts, §2 protocol):
- n10: 5/20 DNF at the 350s budget — the WS4/WS5 sweep recorded 0% DNF
  for n10 (§4); the gated-reorder path's wall on the slowest graphs now
  exceeds 350s on this machine. This is a real wall-clock regression
  signal on the layered-path tail, registered for the next optimization
  target (§10.3 already localizes the wall: routing/polish, not CP-SAT).
- n20: 2/20 ok at the 100s budget — consistent with the §4 runtime-caliber
  note (current-engine n20 median 97.1s, per-graph max ~144s, i.e. the
  wall median sits at the budget line; any wall-budgeted sweep yields a
  majority DNF on the slower half of the family). The two ok graphs are
  structural-engine path graphs (13-16s). Quality metrics for the ok
  subset are real measurements; the DNF rows mean exactly 'no layout
  produced within the budget', not a quality verdict.
- Engine-side determinism is unaffected: budgets here are the harness
  wall-clock protocol of §2; the engine itself carries deterministic
  operation-count budgets only (REPORT §2/§5).

### §10.5 Manual truth fixture inventory

Full inventory with provenance pointers: `benchmarks/manual-truths.md`
(7 hand-drawn fixtures: 6 under `benchmarks/manual/`, 1 under
`tests/data/`; paths + origin pointers only, no coordinate copies).

### §10.6 Historical-caliber annotations applied to this report

Per the re-measure card: the pre-pattern-chain stdraw-auto numbers in
§1/§3/§4/§7 are retained verbatim and annotated **WS4/WS5 historical caliber**;
this §10 is the current-engine caliber and supersedes them for all
future comparisons (including the Phase 0 ε-Pareto normalization ranges).

