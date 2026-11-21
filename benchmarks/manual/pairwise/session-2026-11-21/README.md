# Pairwise blind-choice session 2026-11-21

- `viewer.html` — the annotation page (self-contained, works from file://,
  also mirrored under `~/Downloads/stdraw-pref-pipeline/pairwise/`).
- `questions.json` — the deterministic question pack (LCG seed recorded
  inside; re-running the pipeline reproduces it byte-identically).
- `candidates.json` — SOURCE LABELS (source / recipe / grade / gate metrics
  per opaque candidate id).  Deliberately NOT referenced by viewer.html:
  blinding depends on this separation (review-consensus red line).

## How to annotate

1. Open `viewer.html` in a browser, answer all 30 questions (24 first-round
   + 6 retest repeats; keyboard 1-4 works; progress persists in localStorage).
2. Click "导出 JSON" — the downloaded `pairwise-session-2026-11-21.json`
   goes into THIS directory.
3. Retest pairs are auto-identifiable: every exported item carries
   `is_retest` and a `pair_key` shared with its first-round twin.

Record fields per item: qid / graph / candidate_a / candidate_b / left_is_a /
is_retest / pair_key / model_version / choice / duration_ms.
