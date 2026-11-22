# Pairwise blind-choice session ROUND 3 (new topologies + anchor pairs) — 2026-11-22-round3

- `viewer.html` — the round-3 annotation page (self-contained, works from
  file://; mirrored under `~/Downloads/stdraw-pref-round3/pairwise/`).
- `questions.json` — deterministic question pack (LCG seed recorded inside;
  re-running benchmarks/aesthetic/pref_round3.py reproduces it
  byte-identically).
- `candidates.json` — SOURCE LABELS (source / recipe / gate metrics per
  opaque candidate id).  Deliberately NOT referenced by viewer.html:
  blinding depends on this separation (review-consensus red line).

## What changed vs round 2

- ZERO dose pairs: the synthetic perturbation ladder is not loaded at all
  (hard-asserted in the self-check).
- New topology sources under benchmarks/manual/pref-round3/sources/
  (n=8-10 each): pure nested-ring variant (inner ring shares ONE node with
  the outer ring), chain+ring hybrid, asymmetric dual-hub.  Each got 4-6
  diverse engine candidates from a fixed recipe x pitch ladder, all
  passing the hard viability gate (min card gap >= 16px, zero box-press).
- The old-graph pools were widened with the same ladder (rounds 1-2 left
  ZERO unasked pool pairs); new pairs are anchor-vs-engine (the user's
  human anchor vs fresh engine candidates, same graph) and
  model-disagreement pairs (committed arms M0/M1/M2 scored OFFLINE for
  selection only; committed analysis artifacts untouched).
- Byte-faithful rendering: every picture is an engine --from-layout replay
  of the candidate's stored geometry (anchors / waypoints / styles kept).
- Cross-session retests: 2 round-2-only both-good ties + 1 tie already
  asked in both rounds (a third observation on the noise-baseline pairs).

## How to annotate

1. Open `viewer.html`, answer all 37 questions (keyboard 1-4
   works; progress persists in localStorage).
2. Click "导出 JSON" — the downloaded `pairwise-session-2026-11-22-round3.json`
   goes into THIS directory.
3. Record fields per item are identical to rounds 1-2: qid / graph /
   candidate_a / candidate_b / left_is_a / is_retest / pair_key /
   model_version / choice / duration_ms.
