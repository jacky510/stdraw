# ring-cycle 主环候选 sweep（D3 决策输入，S2-2）

> 生成：`benchmarks/tools/ring_candidate_sweep.py`（WorkBuddy 优化任务书
> 2026-11-11 S2-2）。**只观测，不改排序**——`stdraw/ringlayout.py` 的选环
> key `(-k, chord_crossings, canonical)` 保持冻结（S2-3 待 jacky 对 D3 拍板），
> 本报告不产生任何引擎字节变化；未切换图的布局按构造逐字节不变。

- 语料：`benchmarks/corpus/classic/*.cld` + `benchmarks/corpus/random/*.cld`（n50 退役族排除；探针仅覆盖 n≤12）
- 探针覆盖 80 图；存在主环候选 38 图；**备选 key 下会切换主环 14 图**

备选 key = `(chord_crossings, -k, canonical)`（弦交叉数优先）。
切换图的完整对照含试验闸门后的布局级 crossings、grade 与硬门状态；
未切换图不重跑布局（同选择 ⇒ 同字节，零漂移）。

| 图 | n | 结果 | 现 key 选中 | 备选 key 选中 | 切换? | 明细 |
|---|---|---|---|---|---|---|
| `benchmarks/corpus/classic/arms-race.cld` | 4 | no ring candidates (not loop-dominated) | - | - | - | - |
| `benchmarks/corpus/classic/brand-flywheel.cld` | 6 | same winner k=6 chord_cross=0 (no drift by construction) | k6/x0 | k6/x0 | no | - |
| `benchmarks/corpus/classic/bullwhip.cld` | 5 | same winner k=4 chord_cross=0 (no drift by construction) | k4/x0 | k4/x0 | no | - |
| `benchmarks/corpus/classic/burnout-attrition.cld` | 5 | same winner k=4 chord_cross=0 (no drift by construction) | k4/x0 | k4/x0 | no | - |
| `benchmarks/corpus/classic/classic-cld-growth-and-burden.cld` | 8 | same winner k=4 chord_cross=0 (no drift by construction) | k4/x0 | k4/x0 | no | - |
| `benchmarks/corpus/classic/debt-spiral.cld` | 5 | same winner k=5 chord_cross=0 (no drift by construction) | k5/x0 | k5/x0 | no | - |
| `benchmarks/corpus/classic/eroding-goals.cld` | 5 | same winner k=3 chord_cross=0 (no drift by construction) | k3/x0 | k3/x0 | no | - |
| `benchmarks/corpus/classic/fishing-collapse.cld` | 6 | same winner k=5 chord_cross=0 (no drift by construction) | k5/x0 | k5/x0 | no | - |
| `benchmarks/corpus/classic/fixes-that-fail.cld` | 4 | same winner k=4 chord_cross=0 (no drift by construction) | k4/x0 | k4/x0 | no | - |
| `benchmarks/corpus/classic/induced-demand.cld` | 5 | same winner k=5 chord_cross=0 (no drift by construction) | k5/x0 | k5/x0 | no | - |
| `benchmarks/corpus/classic/learning-flywheel.cld` | 4 | same winner k=4 chord_cross=0 (no drift by construction) | k4/x0 | k4/x0 | no | - |
| `benchmarks/corpus/classic/limits-to-growth.cld` | 5 | same winner k=4 chord_cross=0 (no drift by construction) | k4/x0 | k4/x0 | no | - |
| `benchmarks/corpus/classic/population-logistic.cld` | 4 | same winner k=3 chord_cross=0 (no drift by construction) | k3/x0 | k3/x0 | no | - |
| `benchmarks/corpus/classic/renewable-resource.cld` | 5 | same winner k=3 chord_cross=0 (no drift by construction) | k3/x0 | k3/x0 | no | - |
| `benchmarks/corpus/classic/shifting-the-burden.cld` | 5 | same winner k=3 chord_cross=0 (no drift by construction) | k3/x0 | k3/x0 | no | - |
| `benchmarks/corpus/classic/soil-erosion.cld` | 6 | same winner k=5 chord_cross=0 (no drift by construction) | k5/x0 | k5/x0 | no | - |
| `benchmarks/corpus/classic/success-to-the-successful.cld` | 6 | k6->k4 (chord cross 1->0; layout crossings 1->1; grade uncertified->uncertified; FAILED gates: visual_crossings_zero; probe run 2s) | k6/x1 | k4/x0 | YES | FAILED gates: visual_crossings_zero |
| `benchmarks/corpus/classic/tragedy-of-the-commons.cld` | 5 | same winner k=4 chord_cross=0 (no drift by construction) | k4/x0 | k4/x0 | no | - |
| `benchmarks/corpus/classic/urban-migration.cld` | 6 | same winner k=4 chord_cross=0 (no drift by construction) | k4/x0 | k4/x0 | no | - |
| `benchmarks/corpus/classic/wage-price-spiral.cld` | 5 | same winner k=3 chord_cross=0 (no drift by construction) | k3/x0 | k3/x0 | no | - |
| `benchmarks/corpus/random/random-n10-i00.cld` | 10 | no ring candidates (not loop-dominated) | - | - | - | - |
| `benchmarks/corpus/random/random-n10-i01.cld` | 10 | k10->k9 (chord cross 3->1; layout crossings 2->2; grade uncertified->uncertified; FAILED gates: visual_crossings_zero; probe run 94s) | k10/x3 | k9/x1 | YES | FAILED gates: visual_crossings_zero |
| `benchmarks/corpus/random/random-n10-i02.cld` | 10 | same winner k=9 chord_cross=0 (no drift by construction) | k9/x0 | k9/x0 | no | - |
| `benchmarks/corpus/random/random-n10-i03.cld` | 10 | same winner k=7 chord_cross=0 (no drift by construction) | k7/x0 | k7/x0 | no | - |
| `benchmarks/corpus/random/random-n10-i04.cld` | 10 | k9->k8 (chord cross 3->0; layout crossings 2->2; grade uncertified->uncertified; FAILED gates: visual_crossings_zero; probe run 91s) | k9/x3 | k8/x0 | YES | FAILED gates: visual_crossings_zero |
| `benchmarks/corpus/random/random-n10-i05.cld` | 10 | k9->k8 (chord cross 5->0; layout crossings 1->2; grade uncertified->uncertified; FAILED gates: visual_crossings_zero; probe run 80s) | k9/x5 | k8/x0 | YES | FAILED gates: visual_crossings_zero |
| `benchmarks/corpus/random/random-n10-i06.cld` | 10 | same winner k=8 chord_cross=5 (no drift by construction) | k8/x5 | k8/x5 | no | - |
| `benchmarks/corpus/random/random-n10-i07.cld` | 10 | k9->k8 (chord cross 6->0; layout crossings 1->1; grade uncertified->uncertified; FAILED gates: visual_crossings_zero; probe run 46s) | k9/x6 | k8/x0 | YES | FAILED gates: visual_crossings_zero |
| `benchmarks/corpus/random/random-n10-i08.cld` | 10 | k9->k8 (chord cross 4->0; layout crossings 1->0; grade uncertified->uncertified; FAILED gates: visual_crossings_zero; probe run 3s) | k9/x4 | k8/x0 | YES | FAILED gates: visual_crossings_zero |
| `benchmarks/corpus/random/random-n10-i09.cld` | 10 | same winner k=8 chord_cross=9 (no drift by construction) | k8/x9 | k8/x9 | no | - |
| `benchmarks/corpus/random/random-n10-i10.cld` | 10 | k10->k8 (chord cross 8->0; layout crossings 1->1; grade uncertified->uncertified; FAILED gates: visual_crossings_zero; probe run 131s) | k10/x8 | k8/x0 | YES | FAILED gates: visual_crossings_zero |
| `benchmarks/corpus/random/random-n10-i11.cld` | 10 | k7->k6 (chord cross 1->0; layout crossings 0->0; grade uncertified->best; all hard gates pass; probe run 8s) | k7/x1 | k6/x0 | YES | all hard gates pass |
| `benchmarks/corpus/random/random-n10-i12.cld` | 10 | k9->k8 (chord cross 5->0; layout crossings 3->2; grade uncertified->uncertified; FAILED gates: anchors_standard,visual_crossings_zero; probe run 113s) | k9/x5 | k8/x0 | YES | FAILED gates: anchors_standard,visual_crossings_zero |
| `benchmarks/corpus/random/random-n10-i13.cld` | 10 | k10->k8 (chord cross 5->0; layout crossings 1->2; grade uncertified->uncertified; FAILED gates: visual_crossings_zero; probe run 5s) | k10/x5 | k8/x0 | YES | FAILED gates: visual_crossings_zero |
| `benchmarks/corpus/random/random-n10-i14.cld` | 10 | same winner k=8 chord_cross=3 (no drift by construction) | k8/x3 | k8/x3 | no | - |
| `benchmarks/corpus/random/random-n10-i15.cld` | 10 | k9->k8 (chord cross 2->0; layout crossings 0->2; grade uncertified->uncertified; FAILED gates: anchors_standard,lines_no_coincidence,visual_crossings_zero; probe run 4s) | k9/x2 | k8/x0 | YES | FAILED gates: anchors_standard,lines_no_coincidence,visual_crossings_zero |
| `benchmarks/corpus/random/random-n10-i16.cld` | 10 | k9->k8 (chord cross 5->2; layout crossings 3->1; grade uncertified->uncertified; FAILED gates: visual_crossings_zero; probe run 110s) | k9/x5 | k8/x2 | YES | FAILED gates: visual_crossings_zero |
| `benchmarks/corpus/random/random-n10-i17.cld` | 10 | k10->k8 (chord cross 2->0; layout crossings 2->1; grade uncertified->uncertified; FAILED gates: visual_crossings_zero; probe run 2s) | k10/x2 | k8/x0 | YES | FAILED gates: visual_crossings_zero |
| `benchmarks/corpus/random/random-n10-i18.cld` | 10 | same winner k=9 chord_cross=2 (no drift by construction) | k9/x2 | k9/x2 | no | - |
| `benchmarks/corpus/random/random-n10-i19.cld` | 10 | k9->k8 (chord cross 8->3; layout crossings 2->2; grade uncertified->uncertified; FAILED gates: lines_no_coincidence,visual_crossings_zero; probe run 186s) | k9/x8 | k8/x3 | YES | FAILED gates: lines_no_coincidence,visual_crossings_zero |
| `benchmarks/corpus/random/random-n20-i00.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i01.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i02.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i03.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i04.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i05.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i06.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i07.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i08.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i09.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i10.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i11.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i12.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i13.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i14.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i15.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i16.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i17.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i18.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n20-i19.cld` | 20 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i00.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i01.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i02.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i03.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i04.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i05.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i06.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i07.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i08.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i09.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i10.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i11.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i12.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i13.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i14.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i15.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i16.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i17.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i18.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |
| `benchmarks/corpus/random/random-n30-i19.cld` | 30 | skip (outside ring probe bound 3..12) | - | - | - | - |

## 结论摘要

备选 key 会改变 14 张图的主环选择；逐图切换明细见上表
（含切换后布局级 crossings 升降与硬门通过情况）。
是否调整排序（S2-3）由 jacky 依本表拍板。
