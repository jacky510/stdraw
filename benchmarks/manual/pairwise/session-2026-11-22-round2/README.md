# Pairwise blind-choice session ROUND 2 (adaptive selection) — 2026-11-22-round2

- `viewer.html` — the round-2 annotation page (self-contained, works from
  file://; mirrored under `~/Downloads/stdraw-pref-round2/pairwise/`).
- `questions.json` — deterministic question pack (LCG seed recorded inside;
  re-running benchmarks/aesthetic/pref_round2.py reproduces it
  byte-identically).
- `candidates.json` — SOURCE LABELS (source / recipe / gate metrics per
  opaque candidate id).  Deliberately NOT referenced by viewer.html:
  blinding depends on this separation (review-consensus red line).

## What changed vs round 1

- Adaptive selection driven by the committed round-1 LOSO results:
  P1 model-uncertain unasked pairs first, P2 weighted supplements for the
  folds that read 0% held-out (nonplanar-credit M1/M2; nested-ring
  brand-flywheel + classic-cld M0/M1), P3 three of the seven round-1
  both-good pairs re-asked (tie stability), P4 new information pairs via the
  post-spotfix synthetic perturbation candidates (zero score weight).
- Byte-faithful rendering: every picture is an engine --from-layout replay
  of the candidate's stored geometry (anchors / waypoints / styles kept) —
  the round-1 slim-doc anchor-stripping defect does not apply here.
- Cross-session retest mix: 3 of 20 questions re-ask round-1 answered pairs
  (15.0%) — stricter than round-1's within-session repeats.
- Selection list with per-question principle annotations:
  benchmarks/aesthetic/pref-round2-selection.json.

## How to annotate

1. Open `viewer.html`, answer all 20 questions (17 new + 3 cross-session
   retests; keyboard 1-4 works; progress persists in localStorage).
2. Click "导出 JSON" — the downloaded `pairwise-session-2026-11-22-round2.json`
   goes into THIS directory.
3. Record fields per item are identical to round 1: qid / graph /
   candidate_a / candidate_b / left_is_a / is_retest / pair_key /
   model_version / choice / duration_ms.
