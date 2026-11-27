# A 档 61 图 逐图漂移登记（base cda021c vs 本卡分支）

逐字节相同 46 图 / 变化 14 图（变化=本卡预期效果）；质量门按分支腿 certificate.json 判读

| 图 | engine | 变化文件 | base(grade/x/vx) | branch(grade/x/vx) | 判读 |
|---|---|---|---|---|---|
| classic/arms-race | ring-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/brand-flywheel | ring-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/bullwhip | column-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/burnout-attrition | column-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/classic-cld-growth-and-burden | spine-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/debt-spiral | ring-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/eroding-goals | bowtie-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/fishing-collapse | ring-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/fixes-that-fail | sym-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/induced-demand | ring-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/learning-flywheel | sym-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/limits-to-growth | column-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/population-logistic | column-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/renewable-resource | column-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/shifting-the-burden | bowtie-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/soil-erosion | ring-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/success-to-the-successful | ring-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/tragedy-of-the-commons | column-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/urban-migration | column-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| classic/wage-price-spiral | bowtie-construct | (identical) | best, x 0, vx 0 | grade best, x 0, vx 0, gates all true | OK |
| random/random-n10-i00 | cp-sat | (identical) | uncertified, x 2, vx 2, BAD ['topology_form_fallback', 'visual_crossings_zero'] | grade uncertified, x 2, vx 2, BAD ['topology_form_fallback', 'visual_crossings_zero'] | CHECK |
| random/random-n10-i01 | cp-sat | certificate.json,demo-2d.html | uncertified, x 2, vx 3, BAD ['anchors_standard', 'topology_form_fallback', 'visual_crossings_zero'] | grade uncertified, x 2, vx 3, BAD ['topology_form_fallback', 'visual_crossings_zero'] | CHECK |
| random/random-n10-i02 | ring-construct | (identical) | uncertified, x 1, vx 2, BAD ['visual_crossings_zero'] | grade uncertified, x 1, vx 2, BAD ['visual_crossings_zero'] | CHECK |
| random/random-n10-i03 | ring-construct | certificate.json,demo-2d.html | uncertified, x 0, vx 3, BAD ['anchors_standard', 'lines_no_coincidence', 'topology_form_fallback', 'visual_crossings_zero'] | grade uncertified, x 0, vx 3, BAD ['lines_no_coincidence', 'topology_form_fallback', 'visual_crossings_zero'] | CHECK |
| random/random-n10-i04 | cp-sat | (identical) | uncertified, x 2, vx 2, BAD ['topology_form_fallback', 'visual_crossings_zero'] | grade uncertified, x 2, vx 2, BAD ['topology_form_fallback', 'visual_crossings_zero'] | CHECK |
| random/random-n10-i05 | cp-sat | (identical) | uncertified, x 1, vx 1, BAD ['topology_form_fallback', 'visual_crossings_zero'] | grade uncertified, x 1, vx 1, BAD ['topology_form_fallback', 'visual_crossings_zero'] | CHECK |
| random/random-n10-i06 | cp-sat | certificate.json,demo-2d.html | uncertified, x 1, vx 2, BAD ['anchors_standard', 'topology_form_fallback', 'visual_crossings_zero'] | grade uncertified, x 1, vx 2, BAD ['topology_form_fallback', 'visual_crossings_zero'] | CHECK |
| random/random-n10-i07 | cp-sat | (identical) | uncertified, x 1, vx 2, BAD ['topology_form_fallback', 'visual_crossings_zero'] | grade uncertified, x 1, vx 2, BAD ['topology_form_fallback', 'visual_crossings_zero'] | CHECK |
| random/random-n10-i08 | ring-construct | (identical) | uncertified, x 1, vx 2, BAD ['topology_form_fallback', 'visual_crossings_zero'] | grade uncertified, x 1, vx 2, BAD ['topology_form_fallback', 'visual_crossings_zero'] | CHECK |
| random/random-n10-i09 | planarized | certificate.json | crossed-certified, x 1, vx 1 | grade crossed-certified, x 1, vx 1, gates all true | CHECK |
| random/random-n10-i10 | planarized | certificate.json | crossed-certified, x 1, vx 1 | grade crossed-certified, x 1, vx 1, gates all true | CHECK |
| random/random-n10-i11 | ring-construct | (identical) | uncertified, x 0, vx 0, BAD ['topology_form_fallback'] | grade uncertified, x 0, vx 0, BAD ['topology_form_fallback'] | CHECK |
| random/random-n10-i12 | ? | (identical) | uncertified, x 3, vx 6, BAD ['anchors_standard', 'lines_no_coincidence', 'topology_form_fallback', 'visual_crossings_zero'] | grade uncertified, x 3, vx 6, BAD ['lines_no_coincidence', 'topology_form_fallback', 'visual_crossings_zero'] | CHECK |
| random/random-n10-i13 | ring-construct | certificate.json,demo-2d.html | uncertified, x 1, vx 3, BAD ['anchors_standard', 'visual_crossings_zero'] | grade uncertified, x 1, vx 3, BAD ['visual_crossings_zero'] | CHECK |
| random/random-n10-i14 | cp-sat | (identical) | uncertified, x 2, vx 2, BAD ['topology_form_fallback', 'visual_crossings_zero'] | grade uncertified, x 2, vx 2, BAD ['topology_form_fallback', 'visual_crossings_zero'] | CHECK |
| random/random-n10-i15 | ring-construct | certificate.json,demo-2d.html | uncertified, x 0, vx 1, BAD ['anchors_standard', 'visual_crossings_zero'] | grade uncertified, x 0, vx 1, BAD ['visual_crossings_zero'] | CHECK |
| random/random-n10-i16 | planarized | certificate.json | crossed-certified, x 1, vx 1 | grade crossed-certified, x 1, vx 1, gates all true | CHECK |
| random/random-n10-i17 | ring-construct | (identical) | uncertified, x 2, vx 2, BAD ['visual_crossings_zero'] | grade uncertified, x 2, vx 2, BAD ['visual_crossings_zero'] | CHECK |
| random/random-n10-i18 | ring-construct | (identical) | uncertified, x 2, vx 2, BAD ['topology_form_fallback', 'visual_crossings_zero'] | grade uncertified, x 2, vx 2, BAD ['topology_form_fallback', 'visual_crossings_zero'] | CHECK |
| random/random-n10-i19 | planarized | certificate.json | crossed-certified, x 1, vx 1 | grade crossed-certified, x 1, vx 1, gates all true | CHECK |
| random/random-n20-i00 | ? | (identical) | uncertified, x 30, vx 39, BAD ['anchors_standard', 'box_press_zero', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | grade uncertified, x 30, vx 39, BAD ['box_press_zero', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | CHECK |
| random/random-n20-i01 | ? | (identical) | uncertified, x 38, vx 46, BAD ['anchors_standard', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | grade uncertified, x 38, vx 45, BAD ['edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | CHECK |
| random/random-n20-i02 | ? | (identical) | uncertified, x 34, vx 42, BAD ['anchors_standard', 'box_press_zero', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | grade uncertified, x 34, vx 42, BAD ['box_press_zero', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | CHECK |
| random/random-n20-i03 | ? | (identical) | uncertified, x 15, vx 28, BAD ['anchors_standard', 'box_press_zero', 'column_snap24_ge_060', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | grade uncertified, x 15, vx 28, BAD ['box_press_zero', 'column_snap24_ge_060', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | CHECK |
| random/random-n20-i04 | ? | (identical) | uncertified, x 39, vx 49, BAD ['anchors_standard', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | grade uncertified, x 39, vx 48, BAD ['edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | CHECK |
| random/random-n20-i05 | ? | (identical) | uncertified, x 28, vx 38, BAD ['anchors_standard', 'column_snap24_ge_060', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | grade uncertified, x 28, vx 38, BAD ['column_snap24_ge_060', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | CHECK |
| random/random-n20-i06 | ? | (identical) | uncertified, x 40, vx 51, BAD ['anchors_smooth', 'anchors_standard', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'routing_consistent', 'visual_crossings_zero'] | grade uncertified, x 40, vx 51, BAD ['anchors_smooth', 'anchors_standard', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'routing_consistent', 'visual_crossings_zero'] | CHECK |
| random/random-n20-i07 | ? | (identical) | uncertified, x 37, vx 53, BAD ['anchors_standard', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | grade uncertified, x 37, vx 52, BAD ['edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | CHECK |
| random/random-n20-i08 | ? | (identical) | uncertified, x 33, vx 40, BAD ['anchors_standard', 'box_press_zero', 'column_snap24_ge_060', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | grade uncertified, x 33, vx 40, BAD ['box_press_zero', 'column_snap24_ge_060', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | CHECK |
| random/random-n20-i09 | ? | (identical) | uncertified, x 22, vx 32, BAD ['anchors_smooth', 'anchors_standard', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | grade uncertified, x 22, vx 32, BAD ['anchors_smooth', 'anchors_standard', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | CHECK |
| random/random-n20-i10 | planarized | certificate.json | uncertified, x 7, vx 7, BAD ['min_gap_ge_16'] | grade uncertified, x 7, vx 7, BAD ['min_gap_ge_16'] | CHECK |
| random/random-n20-i11 | planarized | certificate.json | crossed-certified, x 2, vx 2 | grade crossed-certified, x 2, vx 2, gates all true | CHECK |
| random/random-n20-i12 | planarized | certificate.json | crossed-certified, x 3, vx 3 | grade crossed-certified, x 3, vx 3, gates all true | CHECK |
| random/random-n20-i13 | planarized | certificate.json | crossed-certified, x 6, vx 6 | grade crossed-certified, x 6, vx 6, gates all true | CHECK |
| random/random-n20-i14 | ? | (identical) | uncertified, x 32, vx 40, BAD ['anchors_standard', 'column_snap24_ge_060', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'routing_consistent', 'visual_crossings_zero'] | grade uncertified, x 32, vx 40, BAD ['column_snap24_ge_060', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'routing_consistent', 'visual_crossings_zero'] | CHECK |
| random/random-n20-i15 | ? | (identical) | uncertified, x 19, vx 29, BAD ['anchors_standard', 'box_press_zero', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | grade uncertified, x 19, vx 29, BAD ['box_press_zero', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | CHECK |
| random/random-n20-i16 | ? | (identical) | uncertified, x 28, vx 43, BAD ['anchors_smooth', 'anchors_standard', 'box_press_zero', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | grade uncertified, x 28, vx 43, BAD ['anchors_smooth', 'anchors_standard', 'box_press_zero', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | CHECK |
| random/random-n20-i17 | planarized | certificate.json | crossed-certified, x 2, vx 2 | grade crossed-certified, x 2, vx 2, gates all true | CHECK |
| random/random-n20-i18 | ? | (identical) | - | - | CHECK |
| random/random-n20-i19 | ? | (identical) | uncertified, x 30, vx 52, BAD ['anchors_smooth', 'anchors_standard', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | grade uncertified, x 30, vx 52, BAD ['anchors_smooth', 'anchors_standard', 'edge_box_clear_ge_16', 'lines_no_coincidence', 'visual_crossings_zero'] | CHECK |
