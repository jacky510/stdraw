# Round-3 pairwise session provenance (2026-11-22)

- Built by aiengineerbot worker (t_3f10f23d): script `benchmarks/aesthetic/pref_round3.py`
  (this branch's version), 3 new topology sources (`benchmarks/manual/pref-round3/sources/`,
  base + alt each), candidate docs in `pref-synthetic/_render_cache/round3/cand.*/layout.json`
  (recipe x pitch ladder, hard gate min-card-gap >= 16). Worker delivered the self-contained
  package to ~/Downloads/stdraw-pref-round3/pairwise/ at 19:02, then crashed x3 on gateway
  restarts before committing/reporting; operator committed this work post-crash on the
  worker's branch, byte-identical to what was delivered (questions.json diffed clean
  against the Downloads package).
- jacky answered 37/37 (2026-11-22 evening): `answers-2026-11-22.json`
  (choices: 4 a / 7 b / 7 both-good / 19 both-bad; 3 cross-session retests, all
  consistent with earlier rounds).
- Superseded: operator independently rebuilt a 34-question session on main
  (5e78563/d51d452) without knowing the worker package had landed; jacky answered the
  worker's 37-question version, so the operator draft is archived as
  `session-2026-11-22-round3-operator-draft/` in the merge commit and NOT annotated.
- Zero dose pairs (hard-asserted); byte-faithful rendering (stored geometry replay);
  source labels separated from viewer (blinding red line).
