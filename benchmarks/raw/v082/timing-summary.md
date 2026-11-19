# v0.8.2 auto re-measure — stage timing summary (STDRAW_TIMING=1)

Per-graph stage tables (stderr captures in `timing/<graph>.txt`),
then cross-graph aggregates. Percentages reconcile against the
reported per-run total (timing layer attributes every interval to
exactly one stage; engine determinism unaffected, REPORT §9).

## arms-race (n=4, m=4, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 87.7 | 3.8 |
| mode_detection_trials | 52.1 | 2.3 |
| route_final | 59.0 | 2.6 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 5.2 | 0.2 |
| repair:midband | 0.2 | 0.0 |
| repair:fan_spread | 0.3 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 5.2 | 0.2 |
| anchor_snap.snap | 2.0 | 0.1 |
| anchor_snap.gate_eval_post | 7.1 | 0.3 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 2066.2 | 90.4 |
| **total** | **2285** | 100.0 (stages sum 100.0%) |

## brand-flywheel (n=6, m=8, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 21.6 | 2.2 |
| mode_detection_trials | 219.5 | 22.2 |
| route_final | 202.7 | 20.5 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 14.2 | 1.4 |
| repair:midband | 1.3 | 0.1 |
| repair:fan_spread | 0.7 | 0.1 |
| repair:arrival_flip_pre | 0.4 | 0.0 |
| anchor_snap.gate_eval_pre | 17.1 | 1.7 |
| anchor_snap.snap | 17.1 | 1.7 |
| anchor_snap.gate_eval_post | 13.9 | 1.4 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 0.9 | 0.1 |
| delivery | 480.0 | 48.5 |
| **total** | **990** | 100.0 (stages sum 99.9%) |

## bullwhip (n=5, m=6, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 20.1 | 2.9 |
| mode_detection_trials | 109.0 | 15.8 |
| route_final | 94.2 | 13.6 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 6.5 | 0.9 |
| repair:midband | 0.2 | 0.0 |
| repair:fan_spread | 0.0 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 6.7 | 1.0 |
| anchor_snap.snap | 6.7 | 1.0 |
| anchor_snap.gate_eval_post | 7.3 | 1.1 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 440.8 | 63.7 |
| **total** | **692** | 100.0 (stages sum 99.9%) |

## burnout-attrition (n=5, m=6, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 18.4 | 2.8 |
| mode_detection_trials | 94.3 | 14.1 |
| route_final | 80.8 | 12.1 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 3.0 | 0.5 |
| repair:midband | 0.3 | 0.0 |
| repair:fan_spread | 0.2 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 3.6 | 0.5 |
| anchor_snap.snap | 2.9 | 0.4 |
| anchor_snap.gate_eval_post | 2.7 | 0.4 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 460.4 | 69.1 |
| **total** | **667** | 100.0 (stages sum 99.9%) |

## classic-cld-growth-and-burden (n=8, m=13, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 18.6 | 1.0 |
| mode_detection_trials | 523.7 | 27.1 |
| route_final | 508.5 | 26.3 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 61.9 | 3.2 |
| repair:midband | 52.4 | 2.7 |
| repair:fan_spread | 3.1 | 0.2 |
| repair:mutual_straight | 2.2 | 0.1 |
| repair:arrival_flip_pre | 0.8 | 0.0 |
| anchor_snap.gate_eval_pre | 67.1 | 3.5 |
| anchor_snap.snap | 20.8 | 1.1 |
| anchor_snap.gate_eval_post | 61.6 | 3.2 |
| repair:lens_joint_reassign | 181.7 | 9.4 |
| repair:arrival_flip_post | 1.0 | 0.1 |
| delivery | 428.5 | 22.2 |
| **total** | **1932** | 100.0 (stages sum 100.0%) |

## debt-spiral (n=5, m=6, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 19.1 | 2.8 |
| mode_detection_trials | 93.0 | 13.8 |
| route_final | 81.8 | 12.2 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 9.1 | 1.4 |
| repair:midband | 0.4 | 0.1 |
| repair:fan_spread | 0.5 | 0.1 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 10.2 | 1.5 |
| anchor_snap.snap | 3.8 | 0.6 |
| anchor_snap.gate_eval_post | 10.0 | 1.5 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 443.8 | 66.1 |
| **total** | **672** | 100.0 (stages sum 100.0%) |

## eroding-goals (n=5, m=6, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 18.1 | 2.6 |
| mode_detection_trials | 91.4 | 13.2 |
| route_final | 79.8 | 11.5 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 13.2 | 1.9 |
| repair:midband | 0.0 | 0.0 |
| repair:fan_spread | 0.0 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 13.2 | 1.9 |
| anchor_snap.snap | 3.5 | 0.5 |
| anchor_snap.gate_eval_post | 13.5 | 2.0 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 461.4 | 66.5 |
| **total** | **694** | 100.0 (stages sum 100.0%) |

## fishing-collapse (n=6, m=9, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 19.7 | 1.6 |
| mode_detection_trials | 323.8 | 26.4 |
| route_final | 314.4 | 25.6 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 20.4 | 1.7 |
| repair:midband | 1.4 | 0.1 |
| repair:fan_spread | 1.0 | 0.1 |
| repair:arrival_flip_pre | 0.4 | 0.0 |
| anchor_snap.gate_eval_pre | 24.3 | 2.0 |
| anchor_snap.snap | 27.0 | 2.2 |
| anchor_snap.gate_eval_post | 22.5 | 1.8 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 1.1 | 0.1 |
| delivery | 471.0 | 38.4 |
| **total** | **1227** | 100.0 (stages sum 100.0%) |

## fixes-that-fail (n=4, m=5, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 20.8 | 3.7 |
| mode_detection_trials | 41.9 | 7.5 |
| route_final | 50.5 | 9.0 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 2.7 | 0.5 |
| repair:midband | 0.0 | 0.0 |
| repair:fan_spread | 0.0 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 3.4 | 0.6 |
| anchor_snap.snap | 13.3 | 2.4 |
| anchor_snap.gate_eval_post | 3.4 | 0.6 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 424.1 | 75.7 |
| **total** | **560** | 100.0 (stages sum 100.0%) |

## induced-demand (n=5, m=7, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 20.4 | 1.9 |
| mode_detection_trials | 204.6 | 18.7 |
| route_final | 215.4 | 19.7 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 13.3 | 1.2 |
| repair:midband | 1.1 | 0.1 |
| repair:fan_spread | 0.1 | 0.0 |
| repair:arrival_flip_pre | 1.5 | 0.1 |
| anchor_snap.gate_eval_pre | 13.4 | 1.2 |
| anchor_snap.snap | 37.6 | 3.4 |
| anchor_snap.gate_eval_post | 15.5 | 1.4 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 23.2 | 2.1 |
| delivery | 547.5 | 50.1 |
| **total** | **1094** | 100.0 (stages sum 100.0%) |

## learning-flywheel (n=4, m=5, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 26.5 | 4.2 |
| mode_detection_trials | 48.2 | 7.6 |
| route_final | 57.7 | 9.1 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 3.4 | 0.5 |
| repair:midband | 0.0 | 0.0 |
| repair:fan_spread | 0.0 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 3.6 | 0.6 |
| anchor_snap.snap | 13.9 | 2.2 |
| anchor_snap.gate_eval_post | 3.5 | 0.6 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 476.1 | 75.2 |
| **total** | **633** | 100.0 (stages sum 100.0%) |

## limits-to-growth (n=5, m=7, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 17.0 | 2.3 |
| mode_detection_trials | 119.1 | 16.4 |
| route_final | 102.3 | 14.1 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 10.1 | 1.4 |
| repair:midband | 0.5 | 0.1 |
| repair:fan_spread | 0.3 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 12.1 | 1.7 |
| anchor_snap.snap | 11.3 | 1.6 |
| anchor_snap.gate_eval_post | 10.8 | 1.5 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 442.0 | 60.9 |
| **total** | **726** | 100.0 (stages sum 99.9%) |

## population-logistic (n=4, m=6, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 17.0 | 1.9 |
| mode_detection_trials | 181.0 | 20.6 |
| route_final | 184.9 | 21.0 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 9.8 | 1.1 |
| repair:midband | 1.0 | 0.1 |
| repair:fan_spread | 1.0 | 0.1 |
| repair:arrival_flip_pre | 0.7 | 0.1 |
| anchor_snap.gate_eval_pre | 9.4 | 1.1 |
| anchor_snap.snap | 28.4 | 3.2 |
| anchor_snap.gate_eval_post | 10.1 | 1.1 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 7.9 | 0.9 |
| delivery | 429.4 | 48.8 |
| **total** | **881** | 100.0 (stages sum 100.0%) |

## random-n10-i00 (n=10, m=16, crossings=2, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 19.3 | 0.1 |
| mode_detection_trials | 492.5 | 1.6 |
| layering | 0.0 | 0.0 |
| placement_cp_sat | 660.0 | 2.2 |
| polish_gated_reorder | 26543.5 | 87.7 |
| route_final | 2197.9 | 7.3 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 51.4 | 0.2 |
| repair:midband | 4.9 | 0.0 |
| repair:fan_spread | 1.4 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 62.1 | 0.2 |
| anchor_snap.snap | 145.8 | 0.5 |
| anchor_snap.gate_eval_post | 66.6 | 0.2 |
| repair:lens_joint_reassign | 0.1 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 8.3 | 0.0 |
| **total** | **30254** | 100.0 (stages sum 100.0%) |

## random-n10-i01 (n=10, m=16, crossings=2, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 41.0 | 0.1 |
| mode_detection_trials | 1227.9 | 2.3 |
| layering | 0.0 | 0.0 |
| placement_cp_sat | 1668.7 | 3.2 |
| polish_gated_reorder | 35723.2 | 67.5 |
| route_final | 8964.8 | 16.9 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 435.2 | 0.8 |
| repair:midband | 6.4 | 0.0 |
| repair:fan_spread | 6.5 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 106.4 | 0.2 |
| anchor_snap.snap | 4649.7 | 8.8 |
| anchor_snap.gate_eval_post | 90.1 | 0.2 |
| delivery | 6.8 | 0.0 |
| **total** | **52927** | 100.0 (stages sum 100.0%) |

## random-n10-i02 (n=10, m=16, crossings=1, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 26.2 | 1.4 |
| mode_detection_trials | 456.4 | 24.0 |
| route_final | 417.8 | 22.0 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 93.1 | 4.9 |
| repair:midband | 2.9 | 0.2 |
| repair:fan_spread | 3.0 | 0.2 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 102.0 | 5.4 |
| anchor_snap.snap | 28.6 | 1.5 |
| anchor_snap.gate_eval_post | 104.7 | 5.5 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 666.6 | 35.1 |
| **total** | **1901** | 100.0 (stages sum 100.0%) |

## random-n10-i03 (n=10, m=16, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 29.8 | 0.8 |
| mode_detection_trials | 928.5 | 24.5 |
| route_final | 448.6 | 11.9 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 205.3 | 5.4 |
| repair:midband | 5.1 | 0.1 |
| repair:fan_spread | 4.0 | 0.1 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 224.0 | 5.9 |
| anchor_snap.snap | 681.5 | 18.0 |
| anchor_snap.gate_eval_post | 421.9 | 11.1 |
| delivery | 836.5 | 22.1 |
| **total** | **3785** | 100.0 (stages sum 100.0%) |

## random-n10-i04 (n=10, m=16, crossings=2, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 24.3 | 0.1 |
| mode_detection_trials | 524.5 | 1.2 |
| layering | 0.0 | 0.0 |
| placement_cp_sat | 850.2 | 1.9 |
| polish_gated_reorder | 38862.5 | 86.3 |
| route_final | 3467.3 | 7.7 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 576.8 | 1.3 |
| repair:midband | 8.7 | 0.0 |
| repair:fan_spread | 4.8 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 181.9 | 0.4 |
| anchor_snap.snap | 232.1 | 0.5 |
| anchor_snap.gate_eval_post | 281.9 | 0.6 |
| repair:lens_joint_reassign | 0.1 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 10.7 | 0.0 |
| **total** | **45026** | 100.0 (stages sum 100.0%) |

## random-n10-i05 (n=10, m=16, crossings=1, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 22.4 | 0.1 |
| mode_detection_trials | 488.8 | 1.2 |
| layering | 0.0 | 0.0 |
| placement_cp_sat | 641.6 | 1.6 |
| polish_gated_reorder | 33657.9 | 85.7 |
| route_final | 3294.1 | 8.4 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 411.5 | 1.0 |
| repair:midband | 4.7 | 0.0 |
| repair:fan_spread | 5.5 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 94.5 | 0.2 |
| anchor_snap.snap | 530.1 | 1.4 |
| anchor_snap.gate_eval_post | 100.0 | 0.3 |
| repair:lens_joint_reassign | 0.1 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 6.6 | 0.0 |
| **total** | **39258** | 100.0 (stages sum 100.0%) |

## random-n10-i06 (n=10, m=16, crossings=1, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 21.7 | 0.1 |
| mode_detection_trials | 558.4 | 2.0 |
| layering | 0.0 | 0.0 |
| placement_cp_sat | 547.9 | 1.9 |
| polish_gated_reorder | 16203.0 | 57.4 |
| route_final | 6496.8 | 23.0 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 192.2 | 0.7 |
| repair:midband | 6.1 | 0.0 |
| repair:fan_spread | 3.6 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 188.4 | 0.7 |
| anchor_snap.snap | 3853.6 | 13.6 |
| anchor_snap.gate_eval_post | 175.5 | 0.6 |
| delivery | 5.4 | 0.0 |
| **total** | **28253** | 100.0 (stages sum 100.0%) |

## random-n10-i07 (n=10, m=16, crossings=1, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 18.8 | 0.1 |
| mode_detection_trials | 16.4 | 0.1 |
| layering | 0.0 | 0.0 |
| placement_cp_sat | 447.0 | 2.2 |
| polish_gated_reorder | 15975.3 | 77.2 |
| route_final | 3314.6 | 16.0 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 568.3 | 2.7 |
| repair:midband | 8.2 | 0.0 |
| repair:fan_spread | 4.9 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 99.6 | 0.5 |
| anchor_snap.snap | 129.1 | 0.6 |
| anchor_snap.gate_eval_post | 97.0 | 0.5 |
| repair:lens_joint_reassign | 0.1 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 8.2 | 0.0 |
| **total** | **20688** | 100.0 (stages sum 100.0%) |

## random-n10-i08 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n10-i09 (n=10, m=16, crossings=1, status=ok)

| stage | ms | % of total |
|---|---|---|
| planarized_l1 | 4409.5 | 100.0 |
| **total** | **4409** | 100.0 (stages sum 100.0%) |

## random-n10-i10 (n=10, m=16, crossings=1, status=ok)

| stage | ms | % of total |
|---|---|---|
| planarized_l1 | 1744.9 | 100.0 |
| **total** | **1745** | 100.0 (stages sum 100.0%) |

## random-n10-i11 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n10-i12 (n=10, m=16, crossings=3, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 18.8 | 0.0 |
| mode_detection_trials | 467.0 | 1.0 |
| layering | 0.1 | 0.0 |
| placement_cp_sat | 678.7 | 1.4 |
| polish_gated_reorder | 37745.5 | 78.9 |
| route_final | 5761.9 | 12.0 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 161.0 | 0.3 |
| repair:midband | 7.5 | 0.0 |
| repair:fan_spread | 8.5 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 197.1 | 0.4 |
| anchor_snap.snap | 2549.4 | 5.3 |
| anchor_snap.gate_eval_post | 224.4 | 0.5 |
| delivery | 5.6 | 0.0 |
| **total** | **47825** | 100.0 (stages sum 100.0%) |

## random-n10-i13 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n10-i14 (n=10, m=16, crossings=2, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 19.0 | 0.0 |
| mode_detection_trials | 598.2 | 1.5 |
| layering | 0.0 | 0.0 |
| placement_cp_sat | 596.4 | 1.5 |
| polish_gated_reorder | 37072.0 | 91.2 |
| route_final | 2167.5 | 5.3 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 52.7 | 0.1 |
| repair:midband | 3.7 | 0.0 |
| repair:fan_spread | 3.3 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 45.1 | 0.1 |
| anchor_snap.snap | 44.7 | 0.1 |
| anchor_snap.gate_eval_post | 39.9 | 0.1 |
| repair:lens_joint_reassign | 0.1 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 2.2 | 0.0 |
| **total** | **40645** | 100.0 (stages sum 100.0%) |

## random-n10-i15 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n10-i16 (n=10, m=16, crossings=1, status=ok)

| stage | ms | % of total |
|---|---|---|
| planarized_l1 | 1359.8 | 100.0 |
| **total** | **1360** | 100.0 (stages sum 100.0%) |

## random-n10-i17 (n=10, m=16, crossings=2, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 19.7 | 0.0 |
| mode_detection_trials | 497.1 | 0.2 |
| route_final | 270309.4 | 99.1 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 331.3 | 0.1 |
| repair:midband | 12.4 | 0.0 |
| repair:fan_spread | 13.3 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 346.8 | 0.1 |
| anchor_snap.snap | 236.4 | 0.1 |
| anchor_snap.gate_eval_post | 318.6 | 0.1 |
| repair:lens_joint_reassign | 0.1 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 781.0 | 0.3 |
| **total** | **272866** | 100.0 (stages sum 100.0%) |

## random-n10-i18 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n10-i19 (n=10, m=16, crossings=1, status=ok)

| stage | ms | % of total |
|---|---|---|
| planarized_l1 | 5164.7 | 100.0 |
| **total** | **5165** | 100.0 (stages sum 100.0%) |

## random-n20-i00 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n20-i01 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n20-i02 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n20-i03 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n20-i04 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n20-i05 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n20-i06 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n20-i07 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n20-i08 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n20-i09 (n=None, m=None, crossings=None, status=dnf)
- no parseable stage table in timing capture (DNF or empty stderr)

## random-n20-i10 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n20-i11 (n=20, m=32, crossings=2, status=ok)

| stage | ms | % of total |
|---|---|---|
| planarized_l1 | 15469.3 | 100.0 |
| **total** | **15469** | 100.0 (stages sum 100.0%) |

## random-n20-i12 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n20-i13 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n20-i14 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n20-i15 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n20-i16 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n20-i17 (n=20, m=32, crossings=2, status=ok)

| stage | ms | % of total |
|---|---|---|
| planarized_l1 | 13104.1 | 100.0 |
| **total** | **13104** | 100.0 (stages sum 100.0%) |

## random-n20-i18 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## random-n20-i19 (n=None, m=None, crossings=None, status=dnf)
- no timing capture (DNF or missing)

## renewable-resource (n=5, m=7, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 18.7 | 2.0 |
| mode_detection_trials | 195.5 | 21.5 |
| route_final | 197.8 | 21.7 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 8.1 | 0.9 |
| repair:midband | 1.1 | 0.1 |
| repair:fan_spread | 0.6 | 0.1 |
| repair:arrival_flip_pre | 0.7 | 0.1 |
| anchor_snap.gate_eval_pre | 9.6 | 1.0 |
| anchor_snap.snap | 9.3 | 1.0 |
| anchor_snap.gate_eval_post | 9.2 | 1.0 |
| repair:lens_joint_reassign | 1.1 | 0.1 |
| repair:arrival_flip_post | 0.8 | 0.1 |
| delivery | 457.9 | 50.3 |
| **total** | **910** | 100.0 (stages sum 100.0%) |

## shifting-the-burden (n=5, m=8, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 18.2 | 1.6 |
| mode_detection_trials | 300.8 | 26.6 |
| route_final | 284.9 | 25.1 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 18.8 | 1.7 |
| repair:midband | 0.0 | 0.0 |
| repair:fan_spread | 0.0 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 17.9 | 1.6 |
| anchor_snap.snap | 12.3 | 1.1 |
| anchor_snap.gate_eval_post | 20.0 | 1.8 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 459.9 | 40.6 |
| **total** | **1133** | 100.0 (stages sum 100.0%) |

## soil-erosion (n=6, m=8, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 21.6 | 0.9 |
| mode_detection_trials | 248.0 | 10.3 |
| route_final | 231.8 | 9.6 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 14.7 | 0.6 |
| repair:midband | 0.9 | 0.0 |
| repair:fan_spread | 0.3 | 0.0 |
| repair:arrival_flip_pre | 1.1 | 0.0 |
| anchor_snap.gate_eval_pre | 18.4 | 0.8 |
| anchor_snap.snap | 7.1 | 0.3 |
| anchor_snap.gate_eval_post | 18.3 | 0.8 |
| repair:lens_joint_reassign | 1407.7 | 58.5 |
| repair:arrival_flip_post | 1.3 | 0.1 |
| delivery | 436.1 | 18.1 |
| **total** | **2407** | 100.0 (stages sum 100.0%) |

## success-to-the-successful (n=6, m=10, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 19.1 | 0.0 |
| mode_detection_trials | 358.6 | 0.3 |
| ring_reposition | 104211.1 | 95.7 |
| route_final | 865.9 | 0.8 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 459.0 | 0.4 |
| repair:midband | 7.2 | 0.0 |
| repair:fan_spread | 4.0 | 0.0 |
| repair:arrival_flip_pre | 1.4 | 0.0 |
| anchor_snap.gate_eval_pre | 167.8 | 0.2 |
| anchor_snap.snap | 105.0 | 0.1 |
| anchor_snap.gate_eval_post | 176.4 | 0.2 |
| repair:lens_joint_reassign | 1390.1 | 1.3 |
| repair:arrival_flip_post | 6.4 | 0.0 |
| delivery | 1121.5 | 1.0 |
| **total** | **108893** | 100.0 (stages sum 100.0%) |

## tragedy-of-the-commons (n=5, m=6, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 94.1 | 8.6 |
| mode_detection_trials | 127.1 | 11.6 |
| route_final | 97.5 | 8.9 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 12.6 | 1.1 |
| repair:midband | 0.3 | 0.0 |
| repair:fan_spread | 0.0 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 11.3 | 1.0 |
| anchor_snap.snap | 7.3 | 0.7 |
| anchor_snap.gate_eval_post | 8.7 | 0.8 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 737.5 | 67.3 |
| **total** | **1096** | 100.0 (stages sum 100.0%) |

## urban-migration (n=6, m=8, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 28.5 | 3.2 |
| mode_detection_trials | 118.2 | 13.4 |
| route_final | 106.2 | 12.0 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 10.4 | 1.2 |
| repair:midband | 0.6 | 0.1 |
| repair:fan_spread | 0.5 | 0.1 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 14.7 | 1.7 |
| anchor_snap.snap | 7.8 | 0.9 |
| anchor_snap.gate_eval_post | 9.6 | 1.1 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 587.2 | 66.4 |
| **total** | **884** | 100.0 (stages sum 100.0%) |

## wage-price-spiral (n=5, m=6, crossings=0, status=ok)

| stage | ms | % of total |
|---|---|---|
| card_metrics | 20.9 | 2.9 |
| mode_detection_trials | 92.7 | 12.7 |
| route_final | 80.6 | 11.1 |
| manual_injection | 0.0 | 0.0 |
| repair:coincide | 11.5 | 1.6 |
| repair:midband | 0.0 | 0.0 |
| repair:fan_spread | 0.0 | 0.0 |
| repair:arrival_flip_pre | 0.0 | 0.0 |
| anchor_snap.gate_eval_pre | 11.4 | 1.6 |
| anchor_snap.snap | 3.8 | 0.5 |
| anchor_snap.gate_eval_post | 12.2 | 1.7 |
| repair:lens_joint_reassign | 0.0 | 0.0 |
| repair:arrival_flip_post | 0.0 | 0.0 |
| delivery | 496.0 | 68.0 |
| **total** | **729** | 100.0 (stages sum 100.0%) |

## Cross-graph aggregate (all graphs with timing captures)

| stage | summed ms | % of grand total |
|---|---|---|
| route_final | 310737.4 | 41.2 |
| polish_gated_reorder | 241782.9 | 32.1 |
| ring_reposition | 104211.1 | 13.8 |
| planarized_l1 | 41252.3 | 5.5 |
| delivery | 14205.2 | 1.9 |
| anchor_snap.snap | 13421.9 | 1.8 |
| mode_detection_trials | 9798.2 | 1.3 |
| placement_cp_sat | 6090.5 | 0.8 |
| repair:coincide | 3786.7 | 0.5 |
| repair:lens_joint_reassign | 2981.2 | 0.4 |
| anchor_snap.gate_eval_post | 2356.9 | 0.3 |
| anchor_snap.gate_eval_pre | 2088.3 | 0.3 |
| card_metrics | 807.1 | 0.1 |
| repair:midband | 139.5 | 0.0 |
| repair:fan_spread | 71.4 | 0.0 |
| repair:arrival_flip_post | 42.6 | 0.0 |
| repair:arrival_flip_pre | 7.0 | 0.0 |
| repair:mutual_straight | 2.2 | 0.0 |
| layering | 0.1 | 0.0 |
| manual_injection | 0.0 | 0.0 |
| **grand total** | **753785.0** | 100.0 |

