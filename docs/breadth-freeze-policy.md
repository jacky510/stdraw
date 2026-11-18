# Breadth Freeze Policy

Status: adopted 2026-11-14 (jacky ruling), codified 2026-11-18 closure batch.

## Policy

With the P3 planarization contract delivered (non-planar degrade ladder,
L0/L1/L2), stdraw **freezes breadth expansion** and enters a depth-closure
era: performance budgets, maintenance-surface compression, caliber
consistency. **Every new-capability card is triaged first** and only opens
if the triage shows a concrete consumer need that depth work cannot cover.
The engine capability envelope stays n<=20 (n30 capability lives on the
stdraw20 line, not this repository).

## Layout mode family posture (2026-11-18 consumer inventory)

The external review asked for a per-mode real-consumer inventory with
non-consumed modes demoted to frozen baselines (ortho-v1 precedent). Inventory
result (evidence = code dispatch paths, per-mode test files, docs sections;
see `docs/layout-modes.md` audit tables for corpus hit records):

| Mode | Dispatcher-reachable | Tests | Docs | Verdict |
|---|---|---|---|---|
| column-chain | yes (linear topologies) | yes | yes | frozen baseline posture |
| comb-bilateral | yes (wide graphs) | yes | yes | frozen baseline posture |
| bowtie-vertex | yes (co-point symmetry) | yes | yes | frozen baseline posture |
| symmetric | yes (mirror symmetry) | yes | yes | frozen baseline posture |
| spine-wing | yes (vertical-column + wing form) | yes | yes | frozen baseline posture (form-fallback gated since the reverse-form gate) |
| ring-cycle | yes (cycle topologies) | yes | yes | frozen baseline posture (form-fallback gated since the reverse-form gate) |

**Verdict: no mode is demoted for non-consumption.** Every mode is reachable
by the deterministic dispatcher (a future corpus graph may hit it) and is
exercised by tests; none is dead code. The mode family as a whole therefore
moves into **frozen baseline posture** (per ortho-v1 precedent): placement
math stops evolving — bugfixes only, protected by the existing byte gates
(gate A / frozen baselines / certificate regeneration protocol); any new
mode or new capability class goes through the triage gate above.
