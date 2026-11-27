# stdraw environment variables (`STDRAW_*`)

Reference for every `STDRAW_*` environment variable, verified against the
source tree (each entry cites its read sites). Engine variables (1-5) are
read by the `stdraw` package itself; the appendix lists variables read only
by test/benchmark harness scripts.

## Engine variables

### 1. `STDRAW_TIMING`

| | |
|---|---|
| Read at | `stdraw/timing.py:45` (`start()`); surfaced via `stdraw/layout_auto.py` (T3 observational stage timing) |
| Values | `"1"` enables; anything else is off |
| Effect | Emits per-stage wall-clock timing for one `layout()` call to **stderr** (`[stdraw] stage timing ...`), one line per marked stage plus a total |
| Scope | Observational only — zero output drift on/off (the classic 21-input + random-n4 sweeps were verified sha-identical with the flag on and off) |

### 2. `STDRAW_SNAP_DEBUG`

| | |
|---|---|
| Read at | `stdraw/routing.py:45` (central `_dbg()` printer) and `stdraw/routing.py:4075` (anchor-snap stage) |
| Values | Any truthy (non-empty) string enables; unset/empty is off |
| Effect | Snap-stage debug prints to stderr (anchor-snap candidate/reject traces). Messages are built lazily via callables, so the off state costs nothing |
| Scope | Debug only; does not alter layout results or delivery bytes |

### 3. `STDRAW_L1_PINNED`

| | |
|---|---|
| Read at | `stdraw/planarized_layout.py:154` (guard) and `:173` (set for the worker) |
| Values | `"1"` |
| Effect | Internal **recursion guard** for the planarized-L1 determinism rule: `networkx` planar deposition is `PYTHONHASHSEED`-sensitive, so the L1 computation re-enters the module in a pinned worker subprocess (`PYTHONHASHSEED=0`); the guard makes the worker run in-process instead of spawning itself again |
| Scope | **Engine-managed.** Setting it externally to `"1"` skips the pinned subprocess and computes in-process — byte output may then vary across runs (hash-seed sensitivity); not a public knob |

### 4. `STDRAW_PKG_PARENT`

| | |
|---|---|
| Read at | `stdraw/planarized_layout.py:169` (worker bootstrap code) and `:174` (engine sets it) |
| Values | A directory path: the parent of the installed `stdraw` package |
| Effect | Allows the pinned L1 worker subprocess (`sys.executable -c ...`) to `sys.path.insert(0, ...)` and import `stdraw.planarized_layout` from the *calling* checkout rather than whatever is on the default path |
| Scope | **Engine-managed** (set automatically at each L1 spawn); no user action needed or expected |

### 5. `STDRAW_PIN`

| | |
|---|---|
| Read at | **Nowhere in the engine** — the name never appears in an `os.environ` / `getenv` read inside `stdraw/`. In-repo mentions are consumer-contract commentary only: `stdraw/layout_auto.py` (symmetrize guard comment) and `stdraw/symmetrize.py` module docstring |
| Values | n/a (defined and set by downstream byte-pinned consumers, e.g. an embedding service that pins an engine version and requires byte-identical delivered coordinates across upgrades) |
| Effect | None on the engine. It is the *consumer-side* byte-pin contract: when a pinned consumer upgrades the engine, any auto-output byte drift must be registered with that consumer, never delivered silently |

## Appendix: harness-only variables (not read by the `stdraw` package)

| Variable | Read at | Purpose |
|---|---|---|
| `STDRAW_CI_PHASES` | `tests/ci_checks.py:64` | Comma-separated phase selector for the CI iron-gate script (e.g. `B,C` runs only those phases; unset = all) |
| `STDRAW_CI_UNITS_PARALLEL` | `tests/ci_checks.py:540` | `1` = the three CI unit scripts share one parallel batch instead of sequential runs |
| `STDRAW_SKIP_NODE` | `tests/test_mutual_lens_rebuild.py:150` | Set = skip that test module (node/browser-dependent) |
| `STDRAW_MANUAL_SWEEP_DIR` | `tests/probe_drag_follow.py:81` | Path to a manual-sweep directory, injected via env to keep machine-specific paths out of the repo |
| `STDRAW_DROP_SOURCE` | `benchmarks/tools/ablate_m1b.py:37` | Ablation switch for the planarization M1b benchmark (drops one source stage) |
| `STDRAW_NODE` | `benchmarks/tools/run_elk.py:15` | Node executable for the ELK baseline harness (defaults to `node` on PATH) |
