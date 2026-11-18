# Verification Chain — Independent Replay

Status: proposal delivered 2026-11-18 closure batch (DeepSeek external-review
follow-up: make the AGENTS.md contract verification independently replayable
by any role — implementer, visual reviewer, final reviewer — offline, with no
single-point dependency on the implementing agent's environment).

## Goal

"aiengineerbot implements -> uidesignerbot accepts -> default final-reviews"
is a role chain inside one pipeline. The contract's verification must not
depend on any role's private state: every acceptance claim must be
re-derivable from the repository alone by a single command sequence.

## Already independently replayable (no work needed)

1. **Byte-pinned frozen baselines** — `tests/baselines/` + gate A in
   `tests/ci_checks.py` (phase A): `python tests/ci_checks.py` re-renders and
   byte-compares; any machine with the repo + deps reproduces the verdict.
2. **Certificate schema / grading contract** — `stdraw check.py` + certificate
   assertions in ci_checks: certificate JSON is validated against the
   documented caliber, not against a stored opinion.
3. **Full CI check battery** — `python tests/ci_checks.py` (phases A..L,
   splittable via `STDRAW_CI_PHASES=A,B,...` for slow environments; phase
   timing table is printed at the end).
4. **Unit/property suite** — `pytest tests/` (ortools-less environments get
   honest SKIPs on solver-gated tests, e.g. scalability/complexity budget).
5. **Leak gate** — `python scripts/check_internal_leaks.py` (CI-authoritative)
   + the pre-push hook second layer (`core.hooksPath=scripts/hooks`).

## Replay procedure (any role, any machine)

```bash
git clone <this repo> && cd stdraw
python -m venv .venv && .venv/Scripts/pip install -e .[dev]   # solver extra included on CI
python tests/ci_checks.py          # exit 0 required
pytest tests/ -q                   # no FAIL; SKIPs listed honestly
python scripts/check_internal_leaks.py
```

## Gaps + plan (what is NOT yet fully independent)

1. **CI freshness stock reds** — two freshness checks are red on stock
   (pre-existing, same on the pre-closure baseline); tracked on their own
   follow-up card. Until they land, a replaying reviewer must compare against
   the recorded baseline state, not expect a bare exit-0.
2. **Browser-layer (phase C)** — playwright is optional; replay environments
   without it get honest SKIPs. A full visual replay needs the publishing-face
   rendering pass (`demos/` re-render), which is part of the publishing-face
   acceptance flow, not the offline battery.
3. **Evidence packaging convention** (to adopt on every closure batch): the
   implementer attaches one `evidence.txt` containing raw command outputs +
   file sha256 table + copy-paste replay commands, so any reviewer verifies by
   re-running, not by trusting prose.

No code change is proposed in this batch; items 1-2 are tracked work, item 3
is a convention this batch itself follows.
