# A 档双腿 sweep 漂移登记册

> Engineering doc, maintained in Chinese — English overview: README.md

## 0. 用途与边界

- A 档逐字节门（`docs/validation-tiers.md` §1 / §2.1）是「改前基线腿 vs 改后腿双跑 + 逐图比对 + 报漂移」的**流程门**：它没有可重祝福的存储基线，漂移只能被**逐项登记并经批准放行**，不存在「刷基线」这个动作。本册是登记落点。登记 = 承认字节变了 + 用逐图质量对比证明没有变差；登记不改任何门。
- 存储型冻结基线与本册分开处理、各自按再生协议：`tests/baselines/`（ortho-v1 冻结，改动须卡面明令 re-baselining）、`tests/golden/baseline.json`（金标准集，重祝福须经批准，命令 `python tests/golden_gate.py --update-baseline`）。
- 每条登记的前提：auto 配方硬门阈值与 grade 语义**零放宽**。发现需要放宽即停手回报，不得登记。
- 每条登记写明：批准来源 / 变更内容 / 两腿口径 / 汇总数字 / 漂移归因 / 逐图表 / 冻结基线处置 / byte-pinned 消费方影响。一条登记对应一次合入主干的默认行为变更。

## 1. 登记 #1：回路读图层 + lens-chain 布点 + 路由提速（2026-11-25）

### 1.1 批准来源与变更内容

- **批准**：owner 2026-11-25 对「A 档漂移按合法漂移逐项登记放行 → 合入主干」的显式批准（三个选项取「登记放行」）。金标准集基线的重祝福另有 operator 同日的裁决（收口时统一重祝福一次），见 §1.8。
- **变更内容**（`CHANGELOG.md` Unreleased）：① 回路中心标签默认显示（id + 名称 + 方向符号；极性仍只用颜色区分，不加 +/- 符号）；② 回路成员边默认顺回路方向弧线，直线 / 折线只在弧不可交付时按评分回退，证书 `loop_arcs.fallbacks` 逐边记实测原因；③ `@delay` 边标记（DSL 往返一致）与边中点双短线；④ lens-chain 布点（纯双环图）；⑤ 路由候选剪枝提速（精确下界剪枝 / 互指对分离 memo / bbox 间隙预检，输出逐字节不变）。
- **新增硬门**：`loop_labels_clear`（标签不压卡不压线不与他标签重叠）、`delay_marks_clear`、`lens_pairs_closed`、`lens_pair_min_sep_ge_12`——只加不减；既有门阈值与 grade 语义零改动。

### 1.2 两腿口径

- 基线腿 = 主干 `39830f9`（改前，2026-11-24 23:18 → 11-25 03:02）；改后腿 = 分支 `d96a2ce`（2026-11-25 04:23 → 07:40）。改后腿与最终树 `5fb5643` 引擎等价：`d96a2ce..5fb5643` 无引擎文件变更（只动测试 / 金标准基线 / 文档），另抽样 13 图 / 7 类引擎 / 91 个产物逐文件重渲比对 0 差异。
- 工具与口径：`benchmarks/tools/sweep_tiers.py --tier A`，`cp-sat-layered`（Python 3.12 + ortools），同机双腿；rc 语义同 `docs/validation-tiers.md` §0.1（rc=1 = `geometry_report.json` fail>0，交付物照常落盘；质量结论看证书 grade）。
- 比对面：layout.json / certificate.json / geometry_report.json / demo-2d.html（按 index 记录的 sha256）。

### 1.3 汇总

| 项 | 数 |
|---|---|
| 两腿 rc=0（进入逐字节比对） | 44 图 |
| 字节漂移 / 一致 | **44 / 15** |
| classic 20 图 | 4 个产物全漂 |
| random n10×19 + n20×5（24 图） | **只有 `demo-2d.html` 变**（layout / 证书 / 几何报告逐字节不变） |
| 双腿 rc=1（既有失败，两腿相同） | 15 图 |
| 基线腿 TIMEOUT → 改后腿 rc=1 | 1 图（random-n20-i18） |
| 丢门 / 删除门行 / 交叉增加 / 视觉交叉增加 | **0 / 0 / 0 / 0** |
| 新增门行 | 20 图（均为 `loop_labels_clear`） |
| grade 迁移 | best→best ×20、crossed-certified→同 ×8、uncertified→同 ×16（**0 图升降**） |
| 布点模式 / 卡间距 | 44 图全部不变 |
| 44 图 sweep 墙钟合计（含并发负载噪声，仅参考） | 4874.4s → 3677.7s（−24.6%） |
| `loops_audit.json` | 44 图逐字节一致 |

### 1.4 漂移归因

- **classic 20 图**：新增回路标签 1–6 个（变更①）、直线→弧线（变更②）、证书多 1 道硬门行（`loop_labels_clear`）。线型分布不变的 5 图：eroding-goals / shifting-the-burden / wage-price-spiral（bowtie-vertex 模板出图，回路边按布点模板交付直线，证书 `loop_arcs.fallbacks` 逐边记「mode template」）、fixes-that-fail / learning-flywheel（symmetric，基线腿已是弧线为主）。
- **random 24 图**：无声明回路，①②不触发；只有 `demo-2d.html` 内嵌脚本 / 样式常量（标签层 + Loops 开关）变。
- **净距变化 6 图**（边-盒最小净距 px，硬门 ≥16）：arms-race 147.0→171.4、soil-erosion 32.5→55.3、debt-spiral 55.7→67.6（升）；brand-flywheel 33.0→18.6、induced-demand 43.0→34.7、burnout-attrition 25.5→26.2（降但全部门内）。

### 1.5 逐图质量对比（44 图，两腿 rc=0）

表头：engine=布点引擎；gates=硬门通过数/总数；crossings / visual=图论交叉与视觉交叉；line kinds=交付线型分布；loop labels=回路标签数；min clear=边-盒最小净距 px；card gap=最小卡间距 px；placement=布点模式。b→n = 基线腿 → 改后腿。

| graph | engine | grade b->n | gates b->n | crossings b->n | visual b->n | line kinds b -> n | loop labels b->n | min clear b->n | card gap b->n | placement b->n |
|---|---|---|---|---|---|---|---|---|---|---|
| classic/arms-race | ring-construct | best->best | 11/11 -> 12/12 | 0 -> 0 | 0 -> 0 | {"line": 4} -> {"arc": 4} | 0 -> 1 | 147.0 -> 171.4 | 113.3 -> 113.3 | ring-cycle -> ring-cycle |
| classic/brand-flywheel | ring-construct | best->best | 11/11 -> 12/12 | 0 -> 0 | 0 -> 0 | {"arc": 2, "line": 6} -> {"arc": 8} | 0 -> 3 | 33.0 -> 18.6 | 56.6 -> 56.6 | ring-cycle -> ring-cycle |
| classic/bullwhip | column-construct | best->best | 12/12 -> 13/13 | 0 -> 0 | 0 -> 0 | {"arc": 2, "line": 4} -> {"arc": 5, "line": 1} | 0 -> 2 | 21.8 -> 21.8 | 36.0 -> 36.0 | column-chain -> column-chain |
| classic/burnout-attrition | column-construct | best->best | 12/12 -> 13/13 | 0 -> 0 | 0 -> 0 | {"arc": 1, "line": 5} -> {"arc": 6} | 0 -> 2 | 25.5 -> 26.2 | 36.0 -> 36.0 | column-chain -> column-chain |
| classic/classic-cld-growth-and-burden | spine-construct | best->best | 13/13 -> 14/14 | 0 -> 0 | 0 -> 0 | {"arc": 2, "line": 11} -> {"arc": 8, "line": 5} | 0 -> 6 | 20.0 -> 20.0 | 35.0 -> 35.0 | spine-wing -> spine-wing |
| classic/debt-spiral | ring-construct | best->best | 11/11 -> 12/12 | 0 -> 0 | 0 -> 0 | {"line": 6} -> {"arc": 6} | 0 -> 2 | 55.7 -> 67.6 | 75.6 -> 75.6 | ring-cycle -> ring-cycle |
| classic/eroding-goals | bowtie-construct | best->best | 11/11 -> 12/12 | 0 -> 0 | 0 -> 0 | {"line": 6} -> {"line": 6} | 0 -> 2 | 124.0 -> 124.0 | 108.2 -> 108.2 | bowtie-vertex -> bowtie-vertex |
| classic/fishing-collapse | ring-construct | best->best | 11/11 -> 12/12 | 0 -> 0 | 0 -> 0 | {"arc": 2, "line": 7} -> {"arc": 7, "line": 2} | 0 -> 5 | 18.4 -> 18.4 | 22.0 -> 22.0 | ring-cycle -> ring-cycle |
| classic/fixes-that-fail | sym-construct | best->best | 11/11 -> 12/12 | 0 -> 0 | 0 -> 0 | {"arc": 4, "line": 1} -> {"arc": 4, "line": 1} | 0 -> 2 | 44.2 -> 44.2 | 36.0 -> 36.0 | symmetric -> symmetric |
| classic/induced-demand | ring-construct | best->best | 11/11 -> 12/12 | 0 -> 0 | 0 -> 0 | {"arc": 2, "line": 5} -> {"arc": 7} | 0 -> 4 | 43.0 -> 34.7 | 68.0 -> 68.0 | ring-cycle -> ring-cycle |
| classic/learning-flywheel | sym-construct | best->best | 11/11 -> 12/12 | 0 -> 0 | 0 -> 0 | {"arc": 4, "line": 1} -> {"arc": 4, "line": 1} | 0 -> 2 | 44.3 -> 44.3 | 36.0 -> 36.0 | symmetric -> symmetric |
| classic/limits-to-growth | column-construct | best->best | 12/12 -> 13/13 | 0 -> 0 | 0 -> 0 | {"arc": 2, "line": 5} -> {"arc": 6, "vg": 1} | 0 -> 3 | 17.7 -> 17.7 | 36.0 -> 36.0 | column-chain -> column-chain |
| classic/population-logistic | column-construct | best->best | 12/12 -> 13/13 | 0 -> 0 | 0 -> 0 | {"arc": 3, "line": 2, "poly": 1} -> {"arc": 5, "poly": 1} | 0 -> 3 | 16.7 -> 16.7 | 36.0 -> 36.0 | column-chain -> column-chain |
| classic/renewable-resource | column-construct | best->best | 12/12 -> 13/13 | 0 -> 0 | 0 -> 0 | {"arc": 3, "line": 3, "poly": 1} -> {"arc": 5, "line": 1, "poly": 1} | 0 -> 3 | 23.5 -> 23.5 | 36.0 -> 36.0 | column-chain -> column-chain |
| classic/shifting-the-burden | bowtie-construct | best->best | 11/11 -> 12/12 | 0 -> 0 | 0 -> 0 | {"line": 8} -> {"line": 8} | 0 -> 4 | 110.0 -> 110.0 | 95.1 -> 95.1 | bowtie-vertex -> bowtie-vertex |
| classic/soil-erosion | ring-construct | best->best | 11/11 -> 12/12 | 0 -> 0 | 0 -> 0 | {"arc": 2, "line": 6} -> {"arc": 8} | 0 -> 3 | 32.5 -> 55.3 | 66.0 -> 66.0 | ring-cycle -> ring-cycle |
| classic/success-to-the-successful | ring-construct | best->best | 11/11 -> 12/12 | 0 -> 0 | 0 -> 0 | {"arc": 3, "line": 5, "poly": 2} -> {"arc": 4, "line": 4, "poly": 2} | 0 -> 3 | 23.5 -> 23.5 | 32.0 -> 32.0 | ring-cycle -> ring-cycle |
| classic/tragedy-of-the-commons | column-construct | best->best | 12/12 -> 13/13 | 0 -> 0 | 0 -> 0 | {"arc": 2, "line": 4} -> {"arc": 5, "line": 1} | 0 -> 2 | 18.1 -> 18.1 | 35.0 -> 35.0 | column-chain -> column-chain |
| classic/urban-migration | column-construct | best->best | 12/12 -> 13/13 | 0 -> 0 | 0 -> 0 | {"arc": 1, "line": 7} -> {"arc": 8} | 0 -> 3 | 17.7 -> 17.7 | 36.0 -> 36.0 | column-chain -> column-chain |
| classic/wage-price-spiral | bowtie-construct | best->best | 11/11 -> 12/12 | 0 -> 0 | 0 -> 0 | {"line": 6} -> {"line": 6} | 0 -> 2 | 116.0 -> 116.0 | 100.7 -> 100.7 | bowtie-vertex -> bowtie-vertex |
| random/random-n10-i00 | cp-sat | uncertified->uncertified | 11/12 -> 11/12 | 2 -> 2 | 2 -> 2 | {"arc": 3, "line": 10, "vg": 3} -> {"arc": 3, "line": 10, "vg": 3} | 0 -> 0 | 16.7 -> 16.7 | 24.0 -> 24.0 | layered -> layered |
| random/random-n10-i01 | cp-sat | uncertified->uncertified | 10/12 -> 10/12 | 2 -> 2 | 3 -> 3 | {"arc": 1, "line": 11, "poly": 2, "vg": 2} -> {"arc": 1, "line": 11, "poly": 2, "vg": 2} | 0 -> 0 | 17.4 -> 17.4 | 36.0 -> 36.0 | layered -> layered |
| random/random-n10-i02 | ring-construct | uncertified->uncertified | 10/11 -> 10/11 | 1 -> 1 | 2 -> 2 | {"arc": 2, "line": 14} -> {"arc": 2, "line": 14} | 0 -> 0 | 20.1 -> 20.1 | 53.0 -> 53.0 | ring-cycle -> ring-cycle |
| random/random-n10-i03 | ring-construct | uncertified->uncertified | 8/11 -> 8/11 | 0 -> 0 | 3 -> 3 | {"arc": 2, "line": 14} -> {"arc": 2, "line": 14} | 0 -> 0 | 18.7 -> 18.7 | 50.0 -> 50.0 | ring-cycle -> ring-cycle |
| random/random-n10-i04 | cp-sat | uncertified->uncertified | 11/12 -> 11/12 | 2 -> 2 | 2 -> 2 | {"arc": 2, "line": 11, "poly": 1, "vg": 2} -> {"arc": 2, "line": 11, "poly": 1, "vg": 2} | 0 -> 0 | 16.8 -> 16.8 | 24.0 -> 24.0 | layered -> layered |
| random/random-n10-i05 | cp-sat | uncertified->uncertified | 11/12 -> 11/12 | 1 -> 1 | 1 -> 1 | {"arc": 2, "line": 12, "vg": 2} -> {"arc": 2, "line": 12, "vg": 2} | 0 -> 0 | 16.6 -> 16.6 | 36.0 -> 36.0 | layered -> layered |
| random/random-n10-i06 | cp-sat | uncertified->uncertified | 10/12 -> 10/12 | 1 -> 1 | 2 -> 2 | {"arc": 3, "line": 11, "poly": 2} -> {"arc": 3, "line": 11, "poly": 2} | 0 -> 0 | 18.0 -> 18.0 | 20.0 -> 20.0 | layered -> layered |
| random/random-n10-i07 | cp-sat | uncertified->uncertified | 11/12 -> 11/12 | 1 -> 1 | 2 -> 2 | {"arc": 6, "line": 9, "vg": 1} -> {"arc": 6, "line": 9, "vg": 1} | 0 -> 0 | 17.9 -> 17.9 | 20.0 -> 20.0 | layered -> layered |
| random/random-n10-i08 | ring-construct | uncertified->uncertified | 10/11 -> 10/11 | 1 -> 1 | 2 -> 2 | {"arc": 1, "line": 14, "vg": 1} -> {"arc": 1, "line": 14, "vg": 1} | 0 -> 0 | 20.7 -> 20.7 | 31.2 -> 31.2 | ring-cycle -> ring-cycle |
| random/random-n10-i09 | planarized | crossed-certified->crossed-certified | 8/8 -> 8/8 | 1 -> 1 | 1 -> 1 | {"polyline": 16} -> {"polyline": 16} | 0 -> 0 | 40.0 -> 40.0 | 98.0 -> 98.0 | layered -> layered |
| random/random-n10-i10 | planarized | crossed-certified->crossed-certified | 8/8 -> 8/8 | 1 -> 1 | 1 -> 1 | {"polyline": 16} -> {"polyline": 16} | 0 -> 0 | 46.3 -> 46.3 | 94.0 -> 94.0 | layered -> layered |
| random/random-n10-i11 | ring-construct | uncertified->uncertified | 11/11 -> 11/11 | 0 -> 0 | 0 -> 0 | {"arc": 3, "line": 12, "vg": 1} -> {"arc": 3, "line": 12, "vg": 1} | 0 -> 0 | 18.5 -> 18.5 | 24.0 -> 24.0 | ring-cycle -> ring-cycle |
| random/random-n10-i13 | ring-construct | uncertified->uncertified | 9/11 -> 9/11 | 1 -> 1 | 3 -> 3 | {"arc": 1, "line": 13, "poly": 2} -> {"arc": 1, "line": 13, "poly": 2} | 0 -> 0 | 18.5 -> 18.5 | 54.1 -> 54.1 | ring-cycle -> ring-cycle |
| random/random-n10-i14 | cp-sat | uncertified->uncertified | 11/12 -> 11/12 | 2 -> 2 | 2 -> 2 | {"arc": 2, "line": 12, "vg": 2} -> {"arc": 2, "line": 12, "vg": 2} | 0 -> 0 | 17.4 -> 17.4 | 20.0 -> 20.0 | layered -> layered |
| random/random-n10-i15 | ring-construct | uncertified->uncertified | 9/11 -> 9/11 | 0 -> 0 | 1 -> 1 | {"arc": 3, "line": 12, "poly": 1} -> {"arc": 3, "line": 12, "poly": 1} | 0 -> 0 | 17.8 -> 17.8 | 34.0 -> 34.0 | ring-cycle -> ring-cycle |
| random/random-n10-i16 | planarized | crossed-certified->crossed-certified | 8/8 -> 8/8 | 1 -> 1 | 1 -> 1 | {"polyline": 16} -> {"polyline": 16} | 0 -> 0 | 49.1 -> 49.1 | 96.0 -> 96.0 | layered -> layered |
| random/random-n10-i17 | ring-construct | uncertified->uncertified | 10/11 -> 10/11 | 2 -> 2 | 2 -> 2 | {"line": 14, "vg": 2} -> {"line": 14, "vg": 2} | 0 -> 0 | 23.6 -> 23.6 | 54.1 -> 54.1 | ring-cycle -> ring-cycle |
| random/random-n10-i18 | ring-construct | uncertified->uncertified | 10/11 -> 10/11 | 2 -> 2 | 2 -> 2 | {"arc": 1, "line": 15} -> {"arc": 1, "line": 15} | 0 -> 0 | 23.4 -> 23.4 | 53.0 -> 53.0 | ring-cycle -> ring-cycle |
| random/random-n10-i19 | planarized | crossed-certified->crossed-certified | 8/8 -> 8/8 | 1 -> 1 | 1 -> 1 | {"polyline": 16} -> {"polyline": 16} | 0 -> 0 | 70.2 -> 70.2 | 529.6 -> 529.6 | layered -> layered |
| random/random-n20-i10 | planarized | uncertified->uncertified | 7/8 -> 7/8 | 7 -> 7 | 7 -> 7 | {"polyline": 32} -> {"polyline": 32} | 0 -> 0 | 35.6 -> 35.6 | 14.0 -> 14.0 | layered -> layered |
| random/random-n20-i11 | planarized | crossed-certified->crossed-certified | 8/8 -> 8/8 | 2 -> 2 | 2 -> 2 | {"polyline": 32} -> {"polyline": 32} | 0 -> 0 | 26.5 -> 26.5 | 96.0 -> 96.0 | layered -> layered |
| random/random-n20-i12 | planarized | crossed-certified->crossed-certified | 8/8 -> 8/8 | 3 -> 3 | 3 -> 3 | {"polyline": 32} -> {"polyline": 32} | 0 -> 0 | 27.7 -> 27.7 | 565.7 -> 565.7 | layered -> layered |
| random/random-n20-i13 | planarized | crossed-certified->crossed-certified | 8/8 -> 8/8 | 6 -> 6 | 6 -> 6 | {"polyline": 32} -> {"polyline": 32} | 0 -> 0 | 36.1 -> 36.1 | 330.8 -> 330.8 | layered -> layered |
| random/random-n20-i17 | planarized | crossed-certified->crossed-certified | 8/8 -> 8/8 | 2 -> 2 | 2 -> 2 | {"polyline": 32} -> {"polyline": 32} | 0 -> 0 | 17.2 -> 17.2 | 47.1 -> 47.1 | layered -> layered |

### 1.6 逐图门变化（仅有变化的图）

- classic/arms-race: gained ['loop_labels_clear']; removed []; lost []
- classic/brand-flywheel: gained ['loop_labels_clear']; removed []; lost []
- classic/bullwhip: gained ['loop_labels_clear']; removed []; lost []
- classic/burnout-attrition: gained ['loop_labels_clear']; removed []; lost []
- classic/classic-cld-growth-and-burden: gained ['loop_labels_clear']; removed []; lost []
- classic/debt-spiral: gained ['loop_labels_clear']; removed []; lost []
- classic/eroding-goals: gained ['loop_labels_clear']; removed []; lost []
- classic/fishing-collapse: gained ['loop_labels_clear']; removed []; lost []
- classic/fixes-that-fail: gained ['loop_labels_clear']; removed []; lost []
- classic/induced-demand: gained ['loop_labels_clear']; removed []; lost []
- classic/learning-flywheel: gained ['loop_labels_clear']; removed []; lost []
- classic/limits-to-growth: gained ['loop_labels_clear']; removed []; lost []
- classic/population-logistic: gained ['loop_labels_clear']; removed []; lost []
- classic/renewable-resource: gained ['loop_labels_clear']; removed []; lost []
- classic/shifting-the-burden: gained ['loop_labels_clear']; removed []; lost []
- classic/soil-erosion: gained ['loop_labels_clear']; removed []; lost []
- classic/success-to-the-successful: gained ['loop_labels_clear']; removed []; lost []
- classic/tragedy-of-the-commons: gained ['loop_labels_clear']; removed []; lost []
- classic/urban-migration: gained ['loop_labels_clear']; removed []; lost []
- classic/wage-price-spiral: gained ['loop_labels_clear']; removed []; lost []

### 1.7 双腿未交付图（rc 差异；不进入逐字节比对，两腿一致）

- random/random-n10-i12: rc base=1 new=1 (engine None)
- random/random-n20-i00: rc base=1 new=1 (engine None)
- random/random-n20-i01: rc base=1 new=1 (engine None)
- random/random-n20-i02: rc base=1 new=1 (engine None)
- random/random-n20-i03: rc base=1 new=1 (engine None)
- random/random-n20-i04: rc base=1 new=1 (engine None)
- random/random-n20-i05: rc base=1 new=1 (engine None)
- random/random-n20-i06: rc base=1 new=1 (engine None)
- random/random-n20-i07: rc base=1 new=1 (engine None)
- random/random-n20-i08: rc base=1 new=1 (engine None)
- random/random-n20-i09: rc base=1 new=1 (engine None)
- random/random-n20-i14: rc base=1 new=1 (engine None)
- random/random-n20-i15: rc base=1 new=1 (engine None)
- random/random-n20-i16: rc base=1 new=1 (engine None)
- random/random-n20-i18: rc base=TIMEOUT new=1 (engine None)
- random/random-n20-i19: rc base=1 new=1 (engine None)

`random-n20-i18`：基线腿在 sweep 的 900s 上限处超时（rc=TIMEOUT），改后腿 844.2s 落盘、rc=1（fail>0）；两腿都不是 rc=0，rc 分布两腿一致（44 / 15 / 1 → 44 / 16）。

### 1.8 冻结基线处置（与流程门分开报）

- `tests/baselines/`（ortho-v1 冻结 layout.json ×2）：ortho 配方未动，**逐字节零漂移、无需重祝福**（CI 相位 A 两例 fail=0）。
- `tests/golden/baseline.json`（金标准集 8 图）：按批准**统一重祝福一次**（提交 `5fb5643`）。语义零改动：8 图 `.cld` 与 `loops_audit` 三阶段 sha 全不变、8 图全 `best`、crossings 0、geo fail 0；「首次 → 最终」再变的 4 图 = 回路标签放置策略升级（门限未动）。三阶段 sha（前 8 位）：

| 图 | certificate（原始 → 首次 → 最终） | layout（原始 → 首次 → 最终） | 最终 门/模式 |
|---|---|---|---|
| eroding-goals | 7d9247af → f2a51ba3 → f2a51ba3 | ccf7c34c → bc79bfd9 → bc79bfd9 | 12/12 best bowtie-vertex（原 11/11 bowtie-vertex） |
| escalation | 3f3e8d49 → 85bf22ce → 85bf22ce | 7ebca7dd → 62f4d9f7 → 62f4d9f7 | 12/12 best ring-cycle（原 11/11 ring-cycle） |
| fixes-that-fail | 0a0a3d58 → 35111491 → 782b3f02 | d9e2824e → 66b67260 → 06d8d85b | 12/12 best ring-cycle（原 11/11 ring-cycle） |
| growth-and-underinvestment | 71cd636b → d66862ab → 3fed3a92 | 04289143 → 607c7125 → 9ed56e99 | 13/13 best column-chain（原 12/12 column-chain） |
| limits-to-growth | aad86759 → 8086fa7e → 40f1a1b1 | 4f3cbfc8 → 26b85c57 → 471faf6d | 12/12 best ring-cycle（原 11/11 ring-cycle） |
| shifting-the-burden | 26e3d37d → 7b965f47 → 7b965f47 | 9e23a836 → 9697587b → 9697587b | 12/12 best ring-cycle（原 11/11 ring-cycle） |
| success-to-the-successful | 8adc486a → 1d456cae → 1d456cae | 4708bb8d → 60986c80 → 60986c80 | 15/15 best lens-chain（原 12/12 layered） |
| tragedy-of-the-commons | 8e921bf6 → 1d1b841d → 0140239e | a2b7dff1 → 45cd6fd3 → 74da7074 | 12/12 best ring-cycle（原 11/11 ring-cycle） |

- **二次重祝福（回路标签药丸宽度改为解析式；主干 CI 红后的修复）**：批准 = owner 2026-11-25 对「修复前进」的显式批准，范围只限 8 图 layout 指纹。起因 = 回路 id（`R1` / `B1` 粗体拉丁）的药丸宽度原取「字体实测与解析式二者取大」，装了量宽字体的机器与无字体机器交付字节不同（主干 CI 的 demo 新鲜度门 + 金标准 layout 指纹 ×8 红；grade 与门 0 变化）；现改为只按解析式宽度（`textmetrics.analytic_width`，新增回归测试）。结果 = 8 图只有 layout 指纹变（下表，程序取自基线 JSON 新旧对照），certificate / loops_audit / `.cld` 指纹不变，grade / 门数 / 模式 / crossings 全不变：

| 图 | layout（原 → 现） | certificate | 门 / grade / 模式 |
|---|---|---|---|
| eroding-goals | bc79bfd9 → aaee6321 | f2a51ba3（不变） | 12/12 best bowtie-vertex |
| escalation | 62f4d9f7 → 6c86a2f1 | 85bf22ce（不变） | 12/12 best ring-cycle |
| fixes-that-fail | 06d8d85b → 1636f01c | 782b3f02（不变） | 12/12 best ring-cycle |
| growth-and-underinvestment | 9ed56e99 → 92e383e3 | 3fed3a92（不变） | 13/13 best column-chain |
| limits-to-growth | 471faf6d → 791991be | 40f1a1b1（不变） | 12/12 best ring-cycle |
| shifting-the-burden | 9697587b → d556fd37 | 7b965f47（不变） | 12/12 best ring-cycle |
| success-to-the-successful | 60986c80 → cf52211a | 1d456cae（不变） | 15/15 best lens-chain |
| tragedy-of-the-commons | 74da7074 → 09f848ef | 0140239e（不变） | 12/12 best ring-cycle |

  重祝福后的 8 个 layout 指纹与无字体机重渲结果逐张相同；`--update-baseline` 同时刷新计时参考（avg 1.02s / max 2.14s，WARN-only，不作门）。`demos/` 三个页面与 `docs/gallery/` 三张截图同引擎重渲（药丸窄 2–3px，证书面板截图不变）。

### 1.9 byte-pinned 消费方（STDRAW_PIN）

- 消费方现网 pin = `0.8.1`（提交 `4c3cfb4`），**未随本次合入移动**（pin 升级另有流程）；推主干不影响其现网产物。消费方按 `docs/consumer-repro.md` 用 pin 归档 + 独立环境复现。
- 代理对拍（无声明回路图 ×2：`hdd-wide-tickers`、`comb-supply-demand`）：layout / certificate / geometry_report / graph.cld 两树逐字节相同，仅 `demo-2d.html` 外壳变。
- **升级 pin 时的预期变化**：消费方真图声明 8 条回路，三件产物会变（回路标签 + 弧线 + 新门行），届时须走消费侧复现重验；A 档语料没有「comb-bilateral × 声明回路」组合（消费方图正是这个形态），建议 pin 升级时把它纳入回归夹具。

### 1.10 计时（同机、机器安静、5 轮中位，`python -m stdraw layout` 子进程墙钟，秒）

| 图 | 主干（改前） | 仅路由提速 | 最终树 | 最终树·无 OR-Tools |
|---|---|---|---|---|
| eroding-goals | 0.920 | 0.776 | 0.785 | 0.407 |
| escalation | 0.838 | 0.740 | 0.749 | 0.380 |
| fixes-that-fail | 0.972 | 0.770 | 0.795 | 0.402 |
| growth-and-underinvestment | 1.213 | 0.876 | 0.953 | 0.559 |
| limits-to-growth | 1.899 | 1.733 | 2.106 | 1.701 |
| shifting-the-burden | 1.285 | 0.827 | 0.863 | 0.467 |
| success-to-the-successful | 4.785 | 2.045 | 0.791 | 0.381 |
| tragedy-of-the-commons | 1.138 | 0.819 | 0.865 | 0.465 |
| **均值 / 最大** | **1.631 / 4.785** | **1.073 / 2.045** | **0.988 / 2.106** | **0.595 / 1.701** |

「仅路由提速」列 = 只含变更⑤ 的提交（精确等价剪枝，输出逐字节不变）；其后四项变更合计再降约 8%，但不是每图都降：success-to-the-successful 2.045 → 0.791（lens-chain 布点替代分层），limits-to-growth 1.733 → 2.106（弧线候选评分的代价）。金标准集（3–8 节点）全部 <2.1s。边界如实：「≤10 节点 2s 内」只在金标准集成立——10 节点随机稠密图仍有 12–450s 的既有慢例（非本次引入，另有卡跟进）。金标准门的耗时基线 `timing_ref` 只作 WARN 参考（>2 倍才告），不作门。

### 1.11 既有口径备注（非本登记引入，未改）

- `docs/validation-tiers.md` 写「A 档 61 图（classic 21）」，而 `sweep_tiers.graph_list("A")` 实际返回 62 个条目（classic 20 + examples 2 个同名条目 + random 40），同名条目在 index 里不单独留记录（两腿 index 各 60 条）。文档计数与工具不一致属既有问题，另卡对齐。

- **字体独立性只覆盖 CI 逐字节门的产物，不是全量**：回路标签药丸宽度已是解析式；节点卡片宽度仍走 `card_size()` → `text_width()`（字体实测与解析式取大），拉丁字母标签的卡片在装了量宽字体的机器上更宽 —— `examples/hdd-supply-chain`、`examples/longtail-coupled-loops` 有 / 无字体渲染字节不同。这是本登记之前的既有行为（改前主干同样如此），这两张不在 CI 逐字节门覆盖内，本次未改。
