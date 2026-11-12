# Changelog

Notable user-visible changes to **stdraw**. Entries before 0.8.0 are not
reproduced here; the engineering version history lives in
[AGENTS.md](AGENTS.md) ("Version" section) — pointer, not a copy.

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
