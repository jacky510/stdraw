# Changelog

Notable user-visible changes to **stdraw**. Entries before 0.8.0 are not
reproduced here; the engineering version history lives in
[AGENTS.md](AGENTS.md) ("Version" section) — pointer, not a copy.

## 0.8.2 — 2026-11-17

- **Ring form battery manual-calibrated + reverse-form gate widened to
  spine-wing / ring-cycle**: ring regularity gate thresholds re-derived
  from hand-pulled ring truth fixtures (a certified good ring measured
  chord spacing CV 0.0802 / template fit 0.1197 — the old 0.05 gate
  rejected it; the free-hand upper bound measured CV 0.4626 / fit 0.6922),
  landing at RING_SPACING_CV_MAX = 0.50 / RING_TEMPLATE_FIT_MAX = 0.70
  with a single source in `stdraw/ringlayout.py` (metrics / check /
  ci_checks / tests all consume it). Certificate gate rows renamed
  le_005 -> le_050 / le_070.
- **Trial-gate fallback is no longer silent for radial / spine-wing /
  ring-cycle**: layout meta records `form_fallback` (mode + reason) and
  the certificate gains a `topology_form_fallback` gate row with an
  honest grade downgrade — form misfit precedes every hygiene metric.
  The 42-graph A-tier stock certificate records were regenerated at this
  closure: 23 graphs byte-drifted (11 ring gate-row renames with grades
  unchanged; 11 `form_fallback` meta faces with grades unchanged), with
  exactly one grade flip — random-n10-i11 ring-cycle best -> uncertified
  (spine-wing detected but its trial discarded; approved 2026-11-17).
- Also since 0.8.1: exact content-keyed memoization across polish
  candidate worlds (byte-identical outputs, faster sweeps), and the
  interactive L1 tooltip overlay now emits after the `</svg>` element so
  cross markers keep their node cards inside the svg.
- Consumer note: `certificate.json` `version` and `layout.json`
  `engine_version` advance to 0.8.2 on every render — byte-pinned
  consumers (STDRAW_PIN) must regenerate their artifacts and advance the
  pin per their own release discipline.

## 0.8.1 — 2026-11-13

- **Interactive toolbar hint condensed and overridable**: the English
  chrome hint (340+ chars) is condensed and exposed as a new keyword
  parameter `hint` on `render_html` / `render_auto_html` (default `None`
  = built-in English chrome, per the repo language policy: the engine
  EN face stays CJK-free). Byte-pinned consumers pass their own face
  copy (the Chinese-domain consumer passes Chinese). No geometry or
  interaction-contract change; default output changes only in the hint
  string itself.
- **Dark-tier hint contrast fix (ui-design D1)**: `hint_text` #64748b →
  #94a3b8 on the #0f172a toolbar (WCAG 3.75:1 → 6.96:1, AA-passing).
  viewer/themes.js regenerated from themes.py via write_viewer_js
  (generated-artifact channel, byte-pinned by tests).
- Consumer note: render output bytes change → the byte-pinned consumer
  (investment-advisor HDD chain, STDRAW_PIN 0.8.0/261a34e) must
  regenerate its three artifacts from this release and advance the pin
  (deterministic double-run + CDP regression before the lock moves).

## 0.8.0 — 2026-11-11

UI-A theme baseline (drawing-office style, spec:
[docs/ui-theme-spec-a.md](docs/ui-theme-spec-a.md)) — a declared
major-version visual baseline. Engine behavior (parsing, placement,
routing, certificates, gates) is unchanged by this release; what changes
is the delivered look, in both tiers:

### 2D

- **Light tier redefined — "tracing paper"**: parchment page ground with a
  dotted canvas grid and ink-line cards, replacing the amber-carded look;
  the amber / sky-blue polarity inks remain the only two chromatic accents
  on the canvas.
- **Dark tier redefined — "midnight ink"**: faint blue-black ground with
  neutral steel-gray containers and grid, replacing the slate look; the
  polarity inks stay the sole color carriers.
- **Card corner radius 14** (large step of the three-step corner scale).
- **Canvas grid backdrop**: dotted grid rendered under the diagram
  (render-layer only; the edge hit layer remains un-occluded).
- **Certificate as engineering title block**: the quality-certificate
  panel is styled as a drawing title block and deliberately keeps square
  corners (it does not follow the card radius).

### 3D

- **Light stage added**: first light theme for the 3D layer — structure
  and placement unchanged, colors derived from the A light tokens.
- **Dark tier frozen**: the existing dark 3D values are frozen
  byte-for-byte — zero changes.

No routing, placement, certificate-gate or API changes are included in
this entry.
