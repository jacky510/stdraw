# Refactor move map (T17 split of the giant functions)

Machine-readable map: old fully-qualified name (or function section) -> new
location. Purpose: cross-line porting / reconciliation between `main` and the
stdraw20 line (z.code) — the three most-diverged source files
(`layout_auto.py` / `routing.py` / `metrics.py`) are exactly the ones this
card restructured, so future ports locate code through this table instead of
line numbers.

Commit discipline: every move/split is its own commit with the message
prefix `refactor(move): <old fq> -> <new fq>` / `refactor(split): <fn> -> a,
b, c`. All moves are pure (bodies verbatim); first-version behavior is
byte-identical by acceptance (golden 8-figure set + A-tier frozen baselines).

## __main__.py (from `__main__.main`, 264 lines -> orchestrator + 5 helpers)

| old (section of `__main__.main`)        | new |
|-----------------------------------------|-----|
| argparse surface                        | `__main__._build_arg_parser` |
| graph load / validation / T14 hints / T15 size refusal / deprecation warnings | `__main__._prepare_graph` |
| CLI flags -> `AutoConfig`               | `__main__._build_config` |
| manual replay / candidate-v1 / auto-v2 dispatch | `__main__._run_layout_request` |
| exact-layer resolution (D4) + progress prints | `__main__._resolve_exactness` |

## check.py (from `check.auto_geometry_report`, 536 lines -> context + 20 helpers)

Shared context (`chk` closure, `polys()`, mode flags) stays in
`auto_geometry_report`; each numbered check is now a function:

| old (section of `check.auto_geometry_report`) | new |
|---|---|
| check 1 crossings (+ planarized witness match) | `check._agr_01_line_crossings` |
| check 2 box press                             | `check._agr_02_box_press` |
| check 3 edge-box clearance                    | `check._agr_03_edge_box_clearance` |
| check 4 anchor smoothness                     | `check._agr_04_anchor_smoothness` |
| check 5 cards pairwise non-overlapping        | `check._agr_05_cards_non_overlapping` |
| check 6a/6b row pitch + 2px grid (returns `pitch_ok`) | `check._agr_06_grid_row_pitch` |
| check 7 viewBox containment                   | `check._agr_07_viewbox_containment` |
| check 8 rendering scale (returns `s`)         | `check._agr_08_render_scale` |
| check 9 dispatcher (mode elif order unchanged)| `check._agr_09_placement_regularities` |
| check 9 ring branch                           | `check._agr9_ring` |
| check 9 column branch                         | `check._agr9_column` |
| check 9 comb branch                           | `check._agr9_comb` |
| check 9 symmetric branch                      | `check._agr9_sym` |
| check 9 bowtie branch                         | `check._agr9_bowtie` |
| check 9 spine-wing branch                     | `check._agr9_spine_wing` |
| check 9 radial branch                         | `check._agr9_radial` |
| check 9 lens branch                           | `check._agr9_lens` |
| check 9 layered fallback branch               | `check._agr9_layered` |
| check 10 metadata completeness                | `check._agr_10_metadata_complete` |
| check 11 dual crossing accounting (uses check-1 `bad`) | `check._agr_11_dual_crossing_accounting` |
| check 12 mutual-pair min distance             | `check._agr_12_mutual_pair_min_dist` |
| check 13 path_d render/verify consistency     | `check._agr_13_path_d_consistency` |
| checks 14/15 annotation layer                 | `check._agr_14_annotation_layer` |

Note: `_agr_12`'s function-local routing import now reads
`from .routing import min_pair_dist, sample_polyline` (the body samples both
polylines; previously the sample came from the enclosing function's import).

## metrics.py + cert_gates.py (from `metrics.certificate_auto`, 1114 lines)

### Gate registry (the certificate gate assembly)

| old (section of `metrics.certificate_auto`) | new |
|---|---|
| the 9-branch mode gate `if ring_mode: ... elif ... else:` chain | `cert_gates.MODE_GATE_SETS` (data; order = the old elif order, first match wins) driven by `cert_gates.build_gates` |
| ring gate set | `cert_gates._gates_ring` (+ `g_ring_spacing_cv_le_050`, `g_ring_template_fit_le_070`) |
| radial gate set | `cert_gates._gates_radial` (+ `g_radial_*` per-gate functions; battery prep `_gates_radial_prep`) |
| column gate set | `cert_gates._gates_column` |
| comb gate set | `cert_gates._gates_comb` (+ `_gates_comb_prep` hub-edge scan) |
| symmetric/bowtie gate set | `cert_gates._gates_sym_bowtie` |
| spine-wing gate set | `cert_gates._gates_spine` |
| lens gate set | `cert_gates._gates_lens` (+ arc audit `_gates_lens_prep`) |
| planarized-L1 gate set (N/A slots) | `cert_gates._gates_plz_l1` |
| layered gate set | `cert_gates._gates_layered` |
| shared core gate expressions | `cert_gates.g_box_press_zero`, `g_edge_box_clear_ge_16`, `g_anchors_smooth`, `g_anchors_standard`, `g_min_gap_ge_16`, `g_cv_le_035`, `g_pitch_uniform`, `g_column_snap24_ge_060`, `g_mutual_pairs_separated`, `g_mutual_pairs_closed`, `g_lines_no_coincidence`, `g_visual_crossings_zero` |
| visual-crossings overlay + L1 witness replacement | `cert_gates._overlay_visual_crossings` |
| annotation gates (loop labels / delay marks) | `cert_gates._overlay_annotations` |
| routing-consistency gate | `cert_gates._overlay_routing_consistent` |
| external `gates` param merge | `cert_gates._overlay_external_gates` |
| manual-mode N/A slots (P1-2) | `cert_gates._overlay_manual_na` |
| per-entry effect policy (applicability) | `cert_gates._entry(..., when=...)` — first version `when=None` everywhere = "applies whenever the mode set applies" (replicates the historical branches); N/A slots are applicability facts, not thresholds. A future downgrade (e.g. regularity gates -> report items for n>10) is a one-line `when=` data change, owner-gated |

Repair hints stay single-source in `repair.GATE_HINTS` (keyed by gate key);
the registry deliberately does not copy the wording —
`certificate_repair_hints` consumes it unchanged.

### Measurement scans

| old (section of `metrics.certificate_auto`) | new |
|---|---|
| crossings scan (shared-endpoint exempt) | `metrics._cert_crossing_scan` |
| visual crossings scan (fan pairs included) | `metrics._cert_visual_crossing_scan` |
| mutual-pair separation + closed-ring accounting rows | `metrics._cert_mutual_scan` |
| line-line coincidence scan | `metrics._cert_coincide_scan` |
| box press / own-box / anchor smoothness / 16-anchor membership | `metrics._cert_press_clear_scan` |
| avg edge length / row alignment / card gap / spacing CV | `metrics._cert_distribution` |
| per-mode regularity calibers | `metrics._cert_regularity` |
| mode-triggered metrics rows | `metrics._cert_metrics_extensions` |
| mode caliber honest-notes + `out` extensions | `metrics._cert_out_extensions` |

### Duplicate-copy cleanup (follow-up to this split)

The split left `metrics.py` carrying the module twice: the refactored body
(metrics helpers + the nine `_cert_*` helpers above) followed by the full text
of the same module. Last-definition-wins made the live namespace a mix — the
nine helpers from the first copy, `certificate_auto` and 13 redefinitions from
the second — so tests stayed green while the file said every shared definition
twice. The duplicate is gone: one definition per top-level name, spliced by AST
node ranges (no source text retyped), module namespace and every function's
compiled code unchanged. Guard when touching this file: the coding-cookie line
must appear once (`grep -c 'coding: utf-8' stdraw/metrics.py` -> `1`) and no
top-level name may be defined twice (probe pattern: parse the file with `ast`,
count names, compare per-name `ast.dump` against the pre-change copy).

## layout_auto.py + mode_registry.py (from `layout_auto._layout_candidates`, 530 lines)

| old (section of `layout_auto._layout_candidates`) | new |
|---|---|
| mode priority chain (symmetric -> bowtie-vertex -> spine-wing -> [column/comb/ring coupled tier] -> radial -> lens -> layered record; n>12 cap record) | `mode_registry.MODE_CHAIN` (data) driven by `mode_registry.run_mode_chain`; generic steps `_run_generic` (detect -> trial -> trace with hit policies `always` / `on_detect` / `on_activity`); the coupled column/comb/ring tier keeps its historical cross-conditions verbatim in `mode_registry._run_trio`; cap-skip record `_record_cap_skip`; per-run state `mode_registry.ChainState` |
| placement consumption elif chain (sym -> bw -> sw -> comb -> column -> ring -> radial -> lens; layered fallback) | `mode_registry.PLACE_CHAIN` driven by `mode_registry.apply_place_chain`; place bodies `layout_auto._place_sym`, `_place_bw`, `_place_sw`, `_place_comb`, `_place_column`, `_place_ring`, `_place_radial`, `_place_lens`, `_place_layered` |

The three-interface unification per mode: `detect` = the existing
`stdraw.<mode>layout.detect_*` functions (unchanged), `place` = the
`_place_*` functions above, `gates` = `cert_gates.MODE_GATE_SETS` (same
placement vocabulary). Extension points (design-only, declared in the
`mode_registry` module docstring): detect-level layout-family output;
routing-feedback hook into placement; multi-slot anchor vocabulary
(n/s/e/w x 1..k, src/dst split) — no signature hard-codes the 16-anchor set.

## layout_auto.py (from `_layout_optimize_routes`, 639 lines -> 45-line orchestrator + 6 stage helpers)

Continuation of T17 (the first card parked this function at 619 lines;
main grew it to 639 with the DSL-anchor channel, and the continuation
retired that entry on the current body).  `router` / `routes` are threaded through the stages in
call order -- the execution order is unchanged.

| old (section of `layout_auto._layout_optimize_routes`) | new |
|---|---|
| edgerules preset assignment + the hard-gate drop list | `layout_auto._route_stage_presets` |
| `Router` construction, `route_all`, manual pre-injection snapshot, the bounded preset re-enumeration rounds, graph-level legacy exemption | `layout_auto._route_stage_primary` |
| constructed-route freeze, waypoint / style / user-anchor overrides, manual hard-gate fallback | `layout_auto._route_stage_manual` |
| frozen set, coincide reroute, midband reanchor, fan spread, mutual-straight, pre-snap arrival flip | `layout_auto._route_stage_repair` |
| anchor snap + the density-gated probe / revert accounting | `layout_auto._route_stage_anchor_snap` |
| joint anchor re-assign, enhanced arrival flip, mutual lens construct, final crossing pairs | `layout_auto._route_stage_lens_post` |
| former nested `_er_gate_tuple` / `_er_involved_edges` closures | module-level `layout_auto._er_gate_tuple` (now takes `cfg`) / `layout_auto._er_involved_edges` |

## planarized_layout.py (from `_planarized_l1`, 538 lines -> 16-line orchestrator + 5 stage helpers)

Coordinates are threaded through the stages in call order -- the execution
order is unchanged.  A test-first commit pins the L1 output surface (four
corpus L1 fixtures, structural assertions over all five stages) before any
code moves.

| old (section of `planarized_layout._planarized_l1`) | new |
|---|---|
| per-core oracle + exactness aggregation + admission budget checks | `planarized_layout._l1_exactness` |
| card geometry + one Tutte band per core | `planarized_layout._l1_core_bands` |
| attachment-tree placement (escape-ray BFS) | `planarized_layout._l1_attach_trees` |
| clearance scale ladder + deg0 parking lane + global shift | `planarized_layout._l1_normalize` |
| edges_out + witness payload + viewBox + meta block + coordinate stamp | `planarized_layout._l1_assemble` |
| former nested `_defer` closure | module-level `planarized_layout._l1_defer` |
| former nested `_build_polys` | module-level `planarized_layout._l1_build_polys` (inputs explicit) |

Stage helpers return their state dict, or the `("L2", record)` defer tuple;
`_l1_deferred` tells the two apart.

## Deliberately NOT split in this card (honest scope record)

| function | lines at card start | reason |
|---|---|---|
| `render.render_auto_html` (443) / `layout_auto._layout_assemble_delivery` (364) / the routing lens-fan family (`fan_spread` 351, `anchor_snap` 270, `lens_joint_reassign` 248, `_lens_pair_joint_snap` 235, `mutual_lens_construct` 226, `_candidates` 215, `_snap_retry_conflicts` 212) / `edgerules.assign` (238) / `candidate_pipeline.layout` (230) / `planarized_layout._verify` (200) | — | not in the card's named top-6; cohesive geometry/delivery units where splitting adds indirection without a registry payoff; park for follow-up cards |

## Effect-policy reconciliation (gate registry <-> code)

The reconciliation table posted on the card at start of work is enforced by
`tests/test_gate_registry.py`: per-mode gate key ORDER and the N/A slots are
asserted against the historical layout (key order matters — certificate
bytes depend on dict insertion order). Mode registry order is asserted
against the historical elif order in the same test module.
