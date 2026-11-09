# stdraw viewer — Causal Diagram Form Viewer

Once a causal diagram (CLD) is built, the user picks a display form; every form ships with a **live quality certificate**.

## Quick Start

Open `viewer/index.html` in a browser (zero dependencies, zero network — three.js is inlined; the sibling `themes.js` is the generated design-token file and must ship next to it).
Built-in example: the classic "Limits to Growth" archetype (5 nodes / 7 edges / 3 feedback loops).
**Theme**: the topbar `Theme` button toggles Light / Dark (default Dark, the shipped look); the preference persists in `localStorage` (`stdraw-theme`). Tokens for both themes are defined once in `stdraw/themes.py` and consumed here via the generated `themes.js` (byte-pinned by `tests/test_theme_tokens.py`).

## Four Display Forms

| Form | Content | Notes |
|---|---|---|
| 2D · Zero-crossing | Reference layout shipped with the data (`ref` field, optional) | Static, printable form with 0 crossings; nodes can be drag-tuned |
| 2D · Crossings allowed | Even grid placement: constant-spacing slots + total-edge-length-minimizing assignment | Placement first; crossing count reported honestly, not a hard constraint |
| 3D · Sphere | Sphere slots + deterministic total-edge-length-minimizing assignment | Regular 3D placement, rotatable from any angle |
| 3D · Force-directed | Deterministic force-directed (no RNG; same graph → same layout) | General-purpose reference form |

## Core Features

- **Placement first**: node placement (even spacing / symmetric regularity) is the primary objective function, line crossings second — when they conflict, keep placement, give up crossings.
- **Quality certificate (recomputed live on the page)**: crossings / card overlaps / minimum clearance / row alignment rate / spacing coefficient of variation (CV) / edges crossing unrelated cards. The numbers run on rendered coordinates, not pre-stored conclusions. Recomputed instantly when a dragged node is released.
- **Node dragging**: in the 2D forms, hold the left mouse button on a card and drag; lines and arrows follow in real time.
- **Loop panel**: automatically enumerates all directed simple cycles and classifies them by polarity product into reinforcing loops (R, an even number of negative edges) / balancing loops (B, an odd number of negative edges), ordered shortest-first (short loop = strong feedback). Click a loop: amber (R) / sky-blue (B) thick tubes highlight the whole loop + halos on its nodes, while everything else dims.
- **Single-bow arcs**: every curve is a quadratic Bézier with a single bow (one control point) — S-shapes never occur; bidirectional edge pairs are drawn as lens-shaped double arcs (one arc, one arrow).
- **3D depth readability**: labels of far nodes (greater depth) automatically fade (near 1.0 → far 0.30 opacity, linear, deterministic thresholds) so near labels always stay readable; 3D labels use deterministic decluttering on projected screen boxes — no overlapping text at any angle or zoom.
- **WebGL fallback notice**: when WebGL is disabled or fails to initialize, the page no longer goes black — it shows an explanatory card and points to `stdraw layout` for WebGL-free 2D SVG forms.
- **Determinism**: all automatic layouts use no RNG (or a fixed seed); same input, same output.

## Data Format

Graph data is JSON (see `data/example-limits-to-growth.json`):

```json
{
  "nodes": [ {"id": "rate", "l": "adoption rate"} ],
  "edges": [ {"a": "rate", "b": "adopters", "p": "+"} ],
  "ref": { "H": 26, "nodes": { "rate": {"x": 170, "y": 420} } }
}
```

- `p`: polarity, `"+"` same sign / `"−"` opposite sign (U+2212).
- `ref`: optional reference layout (card center coordinates + card height). If present, the "2D · Zero-crossing" form is enabled; without it, only the other three forms are available.

To load your own graph, replace the `GRAPH` / `LAYOUTS` constants embedded in `index.html`
(or generate the full deliverable set — layouts / certificates / loop audit — with `python -m stdraw layout`).

## Design Principles

1. **No lies**: every form's trade-offs are shown honestly by its certificate (e.g. a form with perfect placement but 4 crossings); nothing poses as optimal.
2. **Placement over crossings**: complex graphs aim for even placement (spacing CV metric); simple graphs aim for symmetry or geometric regularity (ring / grid / polygon).
3. **Deterministic output**: same input, same layout — clean diffs in version control.
4. **Verification runs on delivered coordinates**: every metric is recomputed live on rendered coordinates.

## Roadmap

- [x] Layout engine decoupled from the viewer (Python / CLI), DSL and planarity testing (see the `stdraw/` package at the repo root)
- [ ] Minimum-crossing solver for non-planar graphs + 3D metrics (occlusion count / projected edge separation / depth spread)
- [ ] Deep agent integration (MCP server form, self-correcting loop)

## License

MIT (see LICENSE at the repo root). three.js (inlined in index.html) is a third-party MIT-licensed library.
