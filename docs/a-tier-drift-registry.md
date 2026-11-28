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

## 2. 登记 #2：demo 页 / CLI 摘要改为交付线型事实口径 + `--no-loop-labels`（2026-11-25）

### 2.1 批准来源与变更内容

- **来源**：登记 #1 收口时发现的「请求值 ≠ 交付事实」错位——demo 页 H1 与 CLI 摘要取 `meta.line_style`（CLI `--linestyle` 的请求值，默认 straight）印成「line style straight」，而 T10 之后回路成员边默认交付 loop-side 弧线（classic-cld 9 条边全弧线、页面标题却写 straight）。owner 实现卡跟进，卡面明令：改口径 + 新增 `--no-loop-labels` + 抽样证明页面文案漂移。属文案事实化修正，不是渲染行为变更。
- **变更内容**：① H1 与 CLI 摘要改按证书 `metrics.line_kind_counts` 印交付线型分布（如 `line kinds arc 8 / line 5`，确定性排序：计数降序、键名升序）；透镜链 H1 的「(lens arcs constructed)」特判随之退役——交付事实口径下 H1 不再可能误述线型；② 新增 CLI `--no-loop-labels`（整个标识层一个开关：回路标签 + `@delay` 延迟标记），关闭时证书 `loop_labels_clear` / `delay_marks_clear` 如实记 `N/A`（排出门计数、永不阻断、grade 语义不变，口径同 §3.1 manual N/A）；`honest_notes` 追加一条如实说明。
- **不放宽**：门阈值与 grade 语义零改动；默认腿全部产物（layout / certificate / loops_audit / graph / geometry_report）逐字节不变；`tests/baselines/`（ortho）与金标准集零漂移。

### 2.2 两腿口径与抽样证明

- 本次未跑全量 sweep：改动面只有 demo-2d.html 的 H1 一行与 CLI 控制台文案，按引擎类型抽样证明。两腿 = 主干 `9b33fde`（改前）vs 分支树（改后），同机同解释器（Python 3.12 + OR-Tools），每图逐文件比对 7 个产物（graph.json / graph.cld / layout.json / geometry_report.json / certificate.json / loops_audit.json / demo-2d.html）。
- 抽样 7 图覆盖登记 #1 逐图表出现过的全部 7 类引擎；结果（程序取自两腿比对输出）：

| 引擎类型 | 图 | rc 前/后 | 漂移产物 | 其余 6 产物 |
|---|---|---|---|---|
| ring-construct | classic-cld-growth-and-burden | 0/0 | `demo-2d.html`（仅 H1 一行） | 逐字节一致 |
| column-construct | bullwhip | 0/0 | `demo-2d.html`（仅 H1 一行） | 逐字节一致 |
| bowtie-construct | wage-price-spiral | 0/0 | `demo-2d.html`（仅 H1 一行） | 逐字节一致 |
| sym-construct | fixes-that-fail | 0/0 | `demo-2d.html`（仅 H1 一行） | 逐字节一致 |
| ring-construct（第 2 图） | arms-race | 0/0 | `demo-2d.html`（仅 H1 一行） | 逐字节一致 |
| cp-sat-layered | random-n10-i00 | 0/0 | `demo-2d.html`（仅 H1 一行） | 逐字节一致 |
| planarized-L1 | random-n10-i09 | 0/0 | `demo-2d.html`（仅 H1 一行） | 逐字节一致 |

- **7/7 图：唯一漂移产物 = `demo-2d.html`，且 diff 恰好只有 H1 一行**（请求值 → 交付计数）；其余 6 个产物逐字节一致，rc 两腿相同。据此外推：全量 sweep 影响面 = A 档 60 图各自的 `demo-2d.html` H1 一行（纯页面文案），下次全量 sweep 后腿自然覆盖复核。

### 2.3 冻结基线处置

- `tests/baselines/`（ortho-v1 冻结 layout.json ×2）：ortho 分支未动，零漂移。
- `tests/golden/baseline.json`（金标准集 8 图）：金标准钉的是 certificate / loops_audit（原始字节）与 layout 指纹，不钉 demo 页——引擎几何零改动，指纹不变（CI 金标准门实测复核）。

### 2.4 byte-pinned 消费方（STDRAW_PIN）

- 现网 pin 仍为 `0.8.1`，未随本登记移动。默认腿全部非 demo 产物逐字节不变；唯一漂移 = `demo-2d.html` 的 H1 一行。消费方若逐字节 pin demo-2d.html 需重对齐（现 pin 代际产物本就不含回路标签层）。

### 2.5 publishing face 同步

- `demos/` 三页同配方重渲（配方先在改前主干逐字节复现已提交产物 5/5，再换新引擎渲）：每页唯一 diff = H1 一行；`demos/classic-certificate.json` / `demos/classic-loops-audit.json` 逐字节不变。
- `docs/gallery/` 三张截图按既有配方重截（1280×860 / 1280×920）；`certificate.png` 不涉及本次改动面，未动。
- README.md / README_zh-CN.md / skills/stdraw/SKILL.md 补 `--no-loop-labels` 与交付线型口径说明；docs/grading-contract.md 附录 B 新增两节（`--no-loop-labels` N/A 口径、`line_style` 请求 vs 交付语义）；CHANGELOG Unreleased 两则。

## 3. 登记 #3：回路方向符号随绘制环流 + 药丸文字居中 + 透镜收窄 + 互指对记账（2026-11-26）

### 3.1 批准来源与变更内容

- **来源**：P1 画图质量视觉验收（2026-11-25 终审）的 A1（MAJOR）/ A2 / A3（MINOR）/ B6。owner 拍板四项一卡、同批重祝福；金标准 8 图指纹重祝福为预先批准（本卡交付时一次登记，无须再批）。
- **变更内容**：
  - ① 方向符号（A1）：原按回路种类写死（R = 顺时针、B = 逆时针）。现读绘制环流：≥3 成员按成员顺序的有向面积（成员中心多边形）；2 成员、或成员中心共线时按交付环（成员路由按回路序拼接）的有向面积；交付环保留每条路由的全部点，两条平行直线（互指对按直线交付）读作细环；判不出如实记录并退回种类默认。每枚标签记 `dir` / `dir_source`，证书 `metrics.loop_labels[].dir` 同步。
  - ② 药丸文字居中（A2）：`text-anchor: middle`，锚点取图标墨迹右缘与药丸右内缘的中点；药丸宽度解析式不变，布局指纹不因居中而动。
  - ③ 透镜收窄（A3）：`LENS_K` 0.6 → 0.32（每弧鼓出 0.30 → 0.16 × 弦长）。
  - ④ 记账（B6）：互指对里的非弧线成员记入 `loop_arcs.fallbacks`，单列 `mutual_pair_non_arc`，不评分、不动 `loop_edges_arced` 与 grade。
- **不放宽**：门阈值、grade 语义、模式链、锚点口径零改动；`lens_pair_min_sep_ge_12` 未动（靶图实测 28.4，成功致成功 38.0）；`LENS_BULGE_MIN` 0.15 未动。
- **提交**：`a948e89`（方向符号）`d429d8b`（居中）`63a31d8`（记账）`a845af3`（透镜）`0013928`（金标准重祝福）`31f0b27`（demos + gallery）`a1b0e61`（docs）`484be8d`（两成员回路的成员为直线时的环读数）；基线 = 主干 `78d75fe`。

### 3.2 验收数字（改前主干 vs 改后，同机同解释器，程序现读）

| 项 | 口径 | 改前 | 改后 |
|---|---|---|---|
| A1 反向回路：金标准 8 图 + 四节点靶图 + 延迟变体 | 符号扫掠标志 vs 绘制环流（验收报告算法） | 10 / 22（判不出 1） | 0 / 22（判不出 1） |
| A1 反向回路：去延迟变体 | 同上 | 9 / 20（判不出 1） | 0 / 20（判不出 1） |
| A2 药丸左右留白差 | 每枚 \|左留白 − 右留白\| 的最大值（22 枚） | 13.86 px | 0.52 px |
| A3 透镜宽 / 宽弦比：四节点靶图 eff~perf | 两弧同向重采样的最大间距 / 两锚点弦长 159.0 px | 133.4 px / 0.84 | 88.8 px / 0.56 |
| A3 透镜宽 / 宽弦比：四节点靶图 perf~lim | 同上（弦长 156.1 px） | 126.0 px / 0.81 | 82.2 px / 0.53 |
| A3 透镜宽 / 宽弦比：成功致成功（两个透镜同值） | 同上（弦长 150.0 px） | 128.0 px / 0.85 | 86.0 px / 0.57 |
| A3 鼓度 / 两弧最小间距（靶图） | lens_pair_min_bulge / lens_pair_min_sep | 0.3 / 28.4 | 0.16 / 28.4 |
| A3 画布（靶图 viewBox） | 宽 × 高 | 720 × 424 | 720 × 384 |

- **A3 未达验收值 ≤ 0.4，如实登记**：`LENS_K` 0.32 是现约束下的可达最优（靶图 0.56 / 0.53）。约束链（`LENS_K` × `LENS_GAP` 实测扫描，各 8 档）：
  - 鼓度下限门 `lens_pairs_closed`（`LENS_BULGE_MIN` 0.15）要求 `LENS_K` ≥ 约 0.32——`LENS_K` 0.30 时靶图落在门界上，14/15、grade 降为 uncertified。
  - 宽/弦 ≈ `LENS_K` + 两端锚点间距 / 弦长；44px 卡的对称角锚两端间距固定 38px，弦长 159.0 px 时下限即 0.56。要 ≤ 0.40 需弦长 ≥ 约 475px（`LENS_GAP` ≥ 约 470），而 `LENS_GAP` ≥ 360 时靶图退出 lens-chain（placement 为空、12/13）。
  - 验收报告给的配方（锚点间距 24 + 每弧鼓出 20）鼓度 = 20 / 159.0 = 0.126，低于 0.15 门界，同样过不了门。
  - 再窄只能动门、改锚点口径或放宽模式链——均不在本登记授权内，留 owner 决策。折中选项（未采纳，供决策）：`LENS_GAP` 330 时靶图宽/弦 0.44 / 0.42、门仍 15/15，但画布 888 × 608（现 720 × 384）、透镜绝对宽约 147px（现 89px）。

- **B6**：成功致增长的「绩效 ↔ 极限」互指对有 2 条非弧线成员（折线 1 + 直线 1）。改前 `loop_arcs.fallbacks = []`（与 `line_kind_counts` 的 `line 1 / poly 1` 对不上）；改后 `fallbacks` 列出这 2 条（`delivered` = poly / line，`preferred_arc` = not scored: mutual pair），`mutual_pair_non_arc = 2`，note 追加一句单列说明；`line_kind_counts`、`loop_edges_arced`、grade、13/13 全不变。

### 3.3 A 档两腿口径

- 本次改的是默认渲染（标签层 + 透镜几何），故跑**A 档两腿**：基线腿 = 主干 `78d75fe`（改前），新腿 = 分支（改后）。两腿都跑完 classic 20 图 + random-n10 20 图后停；random-n20 20 图未比对（单图 670–780 s：基线腿跑完前 2 张后停，两张 rc=1、引擎未记录；新腿该族无产出；该族无回路标签、无透镜）。同机同解释器，每图逐文件比对 7 个产物。
- 新腿起跑于 `a845af3`；其后引擎还有 1 个提交（`484be8d`，两成员回路的成员为直线时的环读数）。classic 20 图已在最终树重渲并覆盖腿内产物：17 图 7 产物逐字节全等，3 图有变且均在预期内（classic-cld / shifting-the-burden 只变 `layout.json` 的 `dir_source`；fishing-collapse 另变 `certificate.json` 与 `demo-2d.html`，B1 符号改向）。random 族无回路标签，抽 8 图（ring-construct 2 / cp-sat 2 / planarized 4）在最终树重渲，7 产物全等。
- 基线腿记录于 2026-11-26 01:54:56，新腿记录于 2026-11-26 02:24:09；引擎口径两腿同为 `cp-sat-layered`。
- **汇总**：条目 基线 42 / 新 40；逐字节 SAME 20 / DRIFT 20 / rc 差异 0 / 缺腿 2；丢门 0、门行被移除 0；crossings 变多 0、visual crossings 变多 0；placement 变 0；min clear 变小 0；回路标签数变 0；改后未放置标签的图 0；grade best 改前 20 → 改后 20；best 丢失 0。
- grade 迁移：{best->best × 20, crossed-certified->crossed-certified × 4, uncertified->None × 2, uncertified->uncertified × 16}。
- 漂移产物（图数）：{<leg missing> × 2, certificate.json × 20, demo-2d.html × 20, layout.json × 20}。
- 引擎类型（新腿）：{None × 3, bowtie-construct × 3, column-construct × 7, cp-sat × 7, planarized × 4, ring-construct × 15, spine-construct × 1, sym-construct × 2}。

### 3.4 逐图表（rc 两腿一致的已交付图）

| graph | engine | grade 前→后 | 门 前→后 | crossings | visual | 线型 前→后 | 回路标签 | 反向符号 前→后 | min clear | 卡间距 | placement |
|---|---|---|---|---|---|---|---|---|---|---|---|
| classic/arms-race | ring-construct | `best` | `12/12` | `0` | `0` | `arc 4` | `1` | 1/1 → 0/1 | `171.4` | `113.3` | `ring-cycle` |
| classic/brand-flywheel | ring-construct | `best` | `12/12` | `0` | `0` | `arc 8` | `3` | 1/3 → 0/3 | `18.6` | `56.6` | `ring-cycle` |
| classic/bullwhip | column-construct | `best` | `13/13` | `0` | `0` | `arc 5 / line 1` | `2` | 2/2 → 0/2 | `21.8` | `36.0` | `column-chain` |
| classic/burnout-attrition | column-construct | `best` | `13/13` | `0` | `0` | `arc 6` | `2` | 1/2 → 0/2 | `26.2` | `36.0` | `column-chain` |
| classic/classic-cld-growth-and-burden | spine-construct | `best` | `14/14` | `0` | `0` | `arc 8 / line 5` | `6` | 3/6 → 0/6 | `20.0` | `35.0` | `spine-wing` |
| classic/debt-spiral | ring-construct | `best` | `12/12` | `0` | `0` | `arc 6` | `2` | 0/2 → 0/2 | `67.6` | `75.6` | `ring-cycle` |
| classic/eroding-goals | bowtie-construct | `best` | `12/12` | `0` | `0` | `line 6` | `2` | 1/2 → 0/2 | `124.0` | `108.2` | `bowtie-vertex` |
| classic/fishing-collapse | ring-construct | `best` | `12/12` | `0` | `0` | `arc 7 / line 2` | `5` | 2/5 → 0/5 | `18.4` | `22.0` | `ring-cycle` |
| classic/fixes-that-fail | sym-construct | `best` | `12/12` | `0` | `0` | `arc 4 / line 1` | `2` | 2/2 → 0/2 | `44.2` | `36.0` | `symmetric` |
| classic/induced-demand | ring-construct | `best` | `12/12` | `0` | `0` | `arc 7` | `4` | 1/4 → 0/4 | `34.7` | `68.0` | `ring-cycle` |
| classic/learning-flywheel | sym-construct | `best` | `12/12` | `0` | `0` | `arc 4 / line 1` | `2` | 1/2 → 0/2 | `44.3` | `36.0` | `symmetric` |
| classic/limits-to-growth | column-construct | `best` | `13/13` | `0` | `0` | `arc 6 / vg 1` | `3` | 2/3 → 0/3 | `17.7` | `36.0` | `column-chain` |
| classic/population-logistic | column-construct | `best` | `13/13` | `0` | `0` | `arc 5 / poly 1` | `3` | 0/3 → 0/3 | `16.7` | `36.0` | `column-chain` |
| classic/renewable-resource | column-construct | `best` | `13/13` | `0` | `0` | `arc 5 / line 1 / poly 1` | `3` | 1/3 → 0/3 | `23.5` | `36.0` | `column-chain` |
| classic/shifting-the-burden | bowtie-construct | `best` | `12/12` | `0` | `0` | `line 8` | `4` | 0/4 → 0/4 | `110.0` | `95.1` | `bowtie-vertex` |
| classic/soil-erosion | ring-construct | `best` | `12/12` | `0` | `0` | `arc 8` | `3` | 2/3 → 0/3 | `55.3` | `66.0` | `ring-cycle` |
| classic/success-to-the-successful | ring-construct | `best` | `12/12` | `0` | `0` | `arc 4 / line 4 / poly 2` | `3` | 2/3 → 0/3 | `23.5` | `32.0` | `ring-cycle` |
| classic/tragedy-of-the-commons | column-construct | `best` | `13/13` | `0` | `0` | `arc 5 / line 1` | `2` | 0/2 → 0/2 | `18.1` | `35.0` | `column-chain` |
| classic/urban-migration | column-construct | `best` | `13/13` | `0` | `0` | `arc 8` | `3` | 1/3 → 0/3 | `17.7` | `36.0` | `column-chain` |
| classic/wage-price-spiral | bowtie-construct | `best` | `12/12` | `0` | `0` | `line 6` | `2` | 0/2 → 0/2 | `116.0` | `100.7` | `bowtie-vertex` |
| random/random-n10-i00 | cp-sat | `uncertified` | `11/12` | `2` | `2` | `arc 3 / line 10 / vg 3` | `0` | 0/0 → 0/0 | `16.7` | `24.0` | `layered` |
| random/random-n10-i01 | cp-sat | `uncertified` | `10/12` | `2` | `3` | `arc 1 / line 11 / poly 2 / vg 2` | `0` | 0/0 → 0/0 | `17.4` | `36.0` | `layered` |
| random/random-n10-i02 | ring-construct | `uncertified` | `10/11` | `1` | `2` | `arc 2 / line 14` | `0` | 0/0 → 0/0 | `20.1` | `53.0` | `ring-cycle` |
| random/random-n10-i03 | ring-construct | `uncertified` | `8/11` | `0` | `3` | `arc 2 / line 14` | `0` | 0/0 → 0/0 | `18.7` | `50.0` | `ring-cycle` |
| random/random-n10-i04 | cp-sat | `uncertified` | `11/12` | `2` | `2` | `arc 2 / line 11 / poly 1 / vg 2` | `0` | 0/0 → 0/0 | `16.8` | `24.0` | `layered` |
| random/random-n10-i05 | cp-sat | `uncertified` | `11/12` | `1` | `1` | `arc 2 / line 12 / vg 2` | `0` | 0/0 → 0/0 | `16.6` | `36.0` | `layered` |
| random/random-n10-i06 | cp-sat | `uncertified` | `10/12` | `1` | `2` | `arc 3 / line 11 / poly 2` | `0` | 0/0 → 0/0 | `18.0` | `20.0` | `layered` |
| random/random-n10-i07 | cp-sat | `uncertified` | `11/12` | `1` | `2` | `arc 6 / line 9 / vg 1` | `0` | 0/0 → 0/0 | `17.9` | `20.0` | `layered` |
| random/random-n10-i08 | ring-construct | `uncertified` | `10/11` | `1` | `2` | `arc 1 / line 14 / vg 1` | `0` | 0/0 → 0/0 | `20.7` | `31.2` | `ring-cycle` |
| random/random-n10-i09 | planarized | `crossed-certified` | `8/8` | `1` | `1` | `polyline 16` | `0` | 0/0 → 0/0 | `40.0` | `98.0` | `layered` |
| random/random-n10-i10 | planarized | `crossed-certified` | `8/8` | `1` | `1` | `polyline 16` | `0` | 0/0 → 0/0 | `46.3` | `94.0` | `layered` |
| random/random-n10-i11 | ring-construct | `uncertified` | `11/11` | `0` | `0` | `arc 3 / line 12 / vg 1` | `0` | 0/0 → 0/0 | `18.5` | `24.0` | `ring-cycle` |
| random/random-n10-i12 | None | `uncertified` | `9/12` | `3` | `6` | `arc 4 / line 10 / poly 1 / vg 1` | `0` | 0/0 → 0/0 | `17.4` | `24.0` | `layered` |
| random/random-n10-i13 | ring-construct | `uncertified` | `9/11` | `1` | `3` | `arc 1 / line 13 / poly 2` | `0` | 0/0 → 0/0 | `18.5` | `54.1` | `ring-cycle` |
| random/random-n10-i14 | cp-sat | `uncertified` | `11/12` | `2` | `2` | `arc 2 / line 12 / vg 2` | `0` | 0/0 → 0/0 | `17.4` | `20.0` | `layered` |
| random/random-n10-i15 | ring-construct | `uncertified` | `9/11` | `0` | `1` | `arc 3 / line 12 / poly 1` | `0` | 0/0 → 0/0 | `17.8` | `34.0` | `ring-cycle` |
| random/random-n10-i16 | planarized | `crossed-certified` | `8/8` | `1` | `1` | `polyline 16` | `0` | 0/0 → 0/0 | `49.1` | `96.0` | `layered` |
| random/random-n10-i17 | ring-construct | `uncertified` | `10/11` | `2` | `2` | `line 14 / vg 2` | `0` | 0/0 → 0/0 | `23.6` | `54.1` | `ring-cycle` |
| random/random-n10-i18 | ring-construct | `uncertified` | `10/11` | `2` | `2` | `arc 1 / line 15` | `0` | 0/0 → 0/0 | `23.4` | `53.0` | `ring-cycle` |
| random/random-n10-i19 | planarized | `crossed-certified` | `8/8` | `1` | `1` | `polyline 16` | `0` | 0/0 → 0/0 | `70.2` | `529.6` | `layered` |
| random/random-n20-i00 | None | `uncertified` → `None` | `7/12` → `n/a` | `30` → `None` | `39` → `None` | `arc 10 / line 16 / poly 3 / vg 3` → `-` | `0` | - → - | `0.0` → `None` | `16.0` → `None` | `layered` → `None` |
| random/random-n20-i01 | None | `uncertified` → `None` | `8/12` → `n/a` | `38` → `None` | `46` → `None` | `arc 9 / line 13 / poly 5 / vg 5` → `-` | `0` | - → - | `15.9` → `None` | `20.0` → `None` | `layered` → `None` |

### 3.5 A1 全语料读数（两腿全部带回路标签的图）

- 带回路标签的图 基线 20 / 新 20，回路标签 基线 57 / 新 57 枚。反向（验收报告口径：成员中心多边形，退化时读交付环）：基线 **23 / 57** → 新 **0 / 57**；两读数（中心多边形 vs 交付环）相反：基线 1 / 新 1 条。
- 逐图反向数（基线 → 新）：arms-race 1→0；brand-flywheel 1→0；bullwhip 2→0；burnout-attrition 1→0；classic-cld-growth-and-burden 3→0；debt-spiral 0→0；eroding-goals 1→0；fishing-collapse 2→0；fixes-that-fail 2→0；induced-demand 1→0；learning-flywheel 1→0；limits-to-growth 2→0；population-logistic 0→0；renewable-resource 1→0；shifting-the-burden 0→0；soil-erosion 2→0；success-to-the-successful 2→0；tragedy-of-the-commons 0→0；urban-migration 1→0；wage-price-spiral 0→0。
- 新腿另有 4 枚两成员标签（classic-cld B3、fishing-collapse B1、shifting-the-burden B1 / B3）的成员路由是直线：改前交付环按「去掉每条路由末点」拼接后只剩两点、读不出，退回种类默认；`484be8d` 起保留直线两端点后读出。其中 fishing-collapse B1 的符号随读数改向（改前与绘制环流相反），另 3 枚读数与默认一致、符号不变。
- **已知边界（留 owner 决策）**：`classic/limits-to-growth` 的 B1 有 1 条成员弧鼓出到第三节点之外——按成员中心多边形读是顺时针、按绘制的环读是逆时针，两种读数相反；符号按卡面规则取中心多边形读数。金标准 8 图 + 靶图 22 枚标签里两种读数全部一致，验收数字不受影响。要不要改成「绘制环优先」，是口径选择，另议。

### 3.6 门变化与质量字段变化（两腿逐图对照）

- 门：无逐图增删。

- 质量字段（placement / crossings / min clear / 回路标签数）：无变化。

### 3.7 rc 差异与未交付图

- random/random-n20-i00: rc base=1 new=None (engine None)
- random/random-n20-i01: rc base=1 new=None (engine None)

### 3.8 冻结基线处置（与流程门分开报）

- `tests/baselines/`（ortho-v1 冻结 layout.json ×2）：ortho 配方未动，逐字节零漂移、无需重祝福。
- `tests/golden/baseline.json`（金标准集 8 图）：按预先批准**重祝福一次**（提交 `0013928`，`python tests/golden_gate.py --update-baseline`）。语义零改动：8 图 `.cld` 与 `loops_audit` 指纹不变、8 图全 `best`、门数与模式不变；变的是 certificate（`loop_labels[].dir`、互指对记账）与 layout（符号方向 / 文字锚点 / 透镜几何）。三阶段 sha（前 8 位）：
- 引擎其后的提交 `484be8d`（直线成员的环读数）不改这 8 图输出：门读回 8/8，与重祝福后的基线逐字节相等。

| 图 | certificate（原 → 现） | layout（原 → 现） | 门 / grade / 模式 |
|---|---|---|---|
| eroding-goals | f2a51ba3 → e79b63b1 | aaee6321 → abf5b3ff | 12/12 best bowtie-vertex |
| escalation | 85bf22ce → dbaef1fc | 6c86a2f1 → 917cb555 | 12/12 best ring-cycle |
| fixes-that-fail | 782b3f02 → 66502b25 | 1636f01c → 77427b67 | 12/12 best ring-cycle |
| growth-and-underinvestment | 3fed3a92 → d9593eb3 | 92e383e3 → eadb2b94 | 13/13 best column-chain |
| limits-to-growth | 40f1a1b1 → c587cdd4 | 791991be → 5ce2285a | 12/12 best ring-cycle |
| shifting-the-burden | 7b965f47 → a27f251e | d556fd37 → 158129ae | 12/12 best ring-cycle |
| success-to-the-successful | 1d456cae → 9424e375 | cf52211a → 90cfa3f1 | 15/15 best lens-chain |
| tragedy-of-the-commons | 0140239e → fd7628b5 | 09f848ef → 75210041 | 12/12 best ring-cycle |

重祝福后门读回 8/8 ALL GREEN；`--update-baseline` 同时刷新计时参考（只作 WARN 参考，不作门）。

### 3.9 byte-pinned 消费方（STDRAW_PIN）

- 消费方现网 pin 仍为 `0.8.1`，未随本登记移动。
- **升级 pin 时的预期变化**：带回路标签的图，回路标签（符号方向 / 文字位置）与证书 `loop_labels[].dir`、`loop_arcs.fallbacks` 记账会变；带互指对且走 lens-chain 的图，透镜宽度与画布高度会变（靶图 424 → 384）；两成员回路按直线交付的图，`loop_labels[].dir_source` 由 `kind:no-ring` 变为 `ring`，个别符号随读数改向。届时须走消费侧复现重验，不静默。

### 3.10 publishing face 同步

- `demos/` 三页同配方重渲，并逐格与新鲜渲染比对：页面、`demos/classic-certificate.json`、`demos/classic-loops-audit.json` 共 5 个文件 sha256 全等；每页唯一 diff = SVG 行（证书面板与页尾逐字节不变）。classic-cld 6 枚药丸里 3 枚符号改向（R1、B2、B4），药丸位置不动；debt-spiral（中 / 英）只有文字居中。
- `docs/gallery/` 三张截图按既有配方重截（1280×860 / 1280×920），重截 sha256 与已提交文件全等；`certificate.png` 的面板未变，未动。引擎其后的提交 `484be8d` 不改演示产物：demos / 证书 freshness 门复跑通过，逐字节不变。
- 逐格验收 14 / 14 通过；publishing face 文本文件 9 个，卡号 / 本机路径 / worktree 路径 / 内部审批用语 0 命中。
- README.md / README_zh-CN.md / skills/stdraw/SKILL.md / CHANGELOG.md 本登记未动（版本收尾另有流程）。`docs/grading-contract.md` 附录 B 与 `docs/layout-modes.md`（中 / 英）已按新口径写明。


## 4. 登记 #4：药丸「图标 + 文字」整块居中（2026-11-26）

### 4.1 批准来源与变更内容

- **来源**：P1 返修视觉终审（2026-11-26）A2 复验——药丸「内容」= 图标 + 文字整块，左留白（药丸左内缘 → 图标最左墨迹）与右留白（文字最右墨迹 → 药丸右内缘）逐枚差 ≤ 2 px（目标 ≤ 1）。登记 #3 的 ② 只把**文字槽**居中（图标 → 文字间隙 = 文字 → 右内缘），整块内容仍偏右。
- **变更内容**：`label_svg` 改三等分构造——左留白 = 图标 → 文字间隙 = 右留白 = (药丸宽 − 图标墨迹宽 − 文字渲染墨迹宽) / 3；图标按箭头尖（墨迹左缘）定位；文字改 `text-anchor: start`，起点 = 图标墨迹右缘 + 留白；奇数宽药丸以 rect 实际左缘（`%.0f` 取整值）为基准（此前取整使内容整体偏 0.5 单位）；坐标精度 0.1 → 0.01。文字渲染墨迹宽由冻结标定表估算（`stdraw/textmetrics.py`：Microsoft YaHei 400 / 700、ASCII 32–126，每字 advance + 单字墨迹右缘 + 左墨迹；非表内 CJK 取 1 em、墨迹中值 ± 0.5），生成时不读字体文件。
- **不动**：`label_size` 药丸宽度解析式、布局、落位、方向符号、透镜、门阈值、grade 语义；金标准 8 图指纹未变，**未重祝福**。
- **不取的两个方案**（预演后否决）：按字面把文字平移「余量的一半」会让文字槽留白差劣化到 2–3.4 px；`textLength` 拉字距约 1.5–2 px / 字距且字体回退不可控。

### 4.2 验收数字（改前主干 vs 改后，同机同浏览器，程序现读）

浏览器真实几何（Edge headless，图标 path 的 bbox、文字 canvas 逐字墨迹），每枚 \|左留白 − 右留白\|（B）与文字槽留白差（S），单位 = SVG 用户单位：

| 组 | 枚数 | B 改前 | B 改后（验收方量具） | B 改后（Range 矩形） | S 改前 | S 改后 |
|---|---|---|---|---|---|---|
| 金标准 8 图 + 四节点靶图 + 延迟变体 | 22 | 4.03–6.76（0 / 22 ≤ 2） | 0.00–0.50（22 / 22 ≤ 1） | 0.00–0.50 | 0.03–0.94 | 0.03–0.52 |
| 语料（classic 20 图） | 57 | 4.03–8.66（0 / 57） | 0.04–1.14（57 / 57 ≤ 2） | 0.49–0.51 | 0.03–1.31 | 0.03–1.16 |
| examples（4 图） | 12 | 4.68–11.80（0 / 12） | 0.01–1.14（12 / 12 ≤ 2） | 0.01–0.51 | 0.19–1.31 | 0.01–1.16 |

- **两套量具的差别只在文字盒**：验收方量具把 canvas 墨迹锚在 tspan **元素矩形**，Chromium 对 SVG tspan 的 `getBoundingClientRect()` 按 CSS 像素外扩取整（91 枚里 25 枚左缘早 0.36–0.67 单位、右缘晚至 0.9）；Range 矩形（卡面口径）91 / 91 与字形前进宽度零偏差。两套读法 91 枚全部 ≤ 2。
- **独立复核**：DSF 4 像素列扫描（无 canvas、无 DOM 墨迹模型，按亮度找墨迹）B 改前 5.05–12.26 CSS px（0 / 91 ≤ 2）→ 改后 0.36–1.14 CSS px（91 / 91 ≤ 2，折合 ≤ 0.73 单位）。
- 残差来源：非表内 CJK 的墨迹中值假设（真值 10 / 11 / 12 取中值 11.5）→ 末字为 CJK 的药丸 B = 0.50；ASCII 文字 B ≤ 0.17。

### 4.3 指纹与产物

- 两腿（基线 = 主干 `49cf73e`）各渲 34 图（金标准 8 + 靶图 2 + 语料 20 + examples 4）：`graph.json` / `graph.cld` / `layout.json` / `geometry_report.json` / `certificate.json` / `loops_audit.json` 逐字节全等；`demo-2d.html` 33 图只变药丸行（图标 translate、文字 x 与锚点），无回路标签的 1 图不变。
- `python tests/golden_gate.py`：8 / 8 ALL GREEN，8 图 baseline identical，未重祝福。
- `tests/baselines/`（ortho-v1 冻结）：未动。

### 4.4 byte-pinned 消费方（STDRAW_PIN）

- 消费方现网 pin 仍为 `0.8.1`，未随本登记移动。
- **升级 pin 时的预期变化**：带回路标签的图，`demo-2d.html` 药丸内图标与文字位置变（rect、药丸宽、落位不变）；其余 6 个产物逐字节不变。届时须走消费侧复现重验，不静默。

### 4.5 publishing face 同步

- `demos/` 三页同配方重渲：`demos/classic-certificate.json`、`demos/classic-loops-audit.json` 逐字节不变（未动）；三页 HTML 唯一 diff = 药丸行。
- `docs/gallery/` 三张截图重截。配方：Playwright 自带 Chromium 153、保留滚动条、视口 = PNG 尺寸、缩放 1；该配方在主干上对已提交三张 PNG 100% 复现。重截图与已提交图的差异像素 100% 落在药丸框内（classic 7640 / debt-spiral 6190 / debt-spiral-en 4388 px，框外 0）。`certificate.png` 为证书面板裁剪、不含药丸，未动。
- README.md / README_zh-CN.md / skills/stdraw/SKILL.md / CHANGELOG.md 本登记未动（版本收尾另有流程）。
## 5. 登记 #5：互指对闭环透镜（非 lens 引擎）+ 圆角箭尖贴边 + column-chain 成员序（2026-11-26）

### 5.1 批准来源与变更内容

- **批准**：owner 的既有缺陷批卡（P1 验收报告 §7 既有问题段 B1–B4）；重祝福**未预授权**——金标准 8 图指纹变化在收口前单独回报 owner 批（本登记写明变化面，批后才 `--update-baseline`）。A 档漂移按登记放行的既有批准同 #1。
- **变更内容**：① `Router.mutual_lens_construct`（交付层最后一道修复，非 lens 引擎全跑）：互指对按 lens-chain 同一配方重建成双弧透镜，锚变体按序试、逐边过 `LENS_CONSTRUCT` + 相距 ≥12，被门拒掉的对原样保留并逐变体记原因；② 新硬门 `mutual_pairs_closed`（非 lens 门表只加不减，lens-chain 排除）：证书从交付几何重读闭环 / 细透镜 / 可复现的豁免，修复道跑过被拒的对如实记入 `mutual_pairs_exempt`；③ 角锚上的箭尖沿末段方向投影到 r=14 圆角轮廓（只改 `arrow` 字段 + JS 镜像 + payload `cardRadius`）；④ column-chain 残余组成员序：有 spine 邻的成员优先占锚点行。
- **grade 语义与既有门阈值零改动**；`mutual_pairs_separated`（≥4）保留不动，新门是加严方向。

### 5.2 验收数字（改前主干 `49cf73e` vs 改后 `a9f71fc`，同机同解释器，程序现读）
- 勘误补注（2026-11-26）：本节「改后 `a9f71fc`」经 rebase 实际落地 = main `3b8e21d..55d0344`；表中数字经终审复量卡在 main `6485774` 复量逐数相同。

| 项 | 改前 | 改后 | 判 |
|---|---|---|---|
| B1 growth-and-underinvestment performance→limit 绕行（弧长 / 端点弦） | 1.681 | 1.065 | ≤1.2 达标 |
| B1 同线箭尖 vs capacity→limit 箭尖距 | 4.5 px | 90.4 px | ≥8 达标 |
| B2 fixes-that-fail problem↔fix 两线相隔 / 宽÷弦 | 4.5 px / 0.046 | 38.0 px / 0.544 | 宽/弦 ≥0.2 达标 |
| B4 limits-to-growth action↔state 两线相隔 / 宽÷弦 | 17.8 px / 0.107 | 21.2 px / 0.394 | 宽/弦 ≥0.2 达标 |
| B3 箭尖落在 r=14 圆角轮廓外（有符号距离 >0.05）金标准 8 图 | 14 枚（1.56 px） | 0 枚 | 悬空 0 达标 |
| B3 同口径全语料 52 图 | 94 | 0 | — |
| 金标准 8 图 grade / crossings | 8 best / 0 | 8 best / 0 | 全绿 |

- B4 的 GaU R1（efforts↔performance）：改前已是 21px 相距的金锚透镜（本册量法宽/弦 0.529；验收报告的 0.10 口径未复现——0.10 是 **LtG R1（action↔state）的改前值，不是 GaU R1**，对账见目检报告 §2.5），本轮未动（performance 的上角锚被 B2 透镜占用，角锚变体不可用；弦 42px 由 80px 行距决定）——如实记录，不宣称改善。
- A4（GaU 三枚标签归属）：改后三枚仍不在各自环内（R1/B2 偏心距 80 / 95.9，B3 64）；药丸 18px 高 + 两侧 4px 门隙需要透镜宽 ≥88 → 弦 ≥209，现节距 80 下不可达，B1 布点修复不改变该结论——按卡面「随 B1 复核」如实记录。
- B3 实现口径与卡面措辞不同：箭尖沿**末段方向**投影到圆角轮廓（无交点时径向），不是沿框边法线；位移 ≤2.34px。

### 5.3 A 档两腿口径

- 基线腿 = 主干 `49cf73e`（改前，52 图：classic 20 + longtail 12 + random-n10 20）；改后腿 = 分支 `a9f71fc`（同机，4 并行子进程，`python -m stdraw layout` 子进程）。比对面同 #1（layout.json / certificate.json / geometry_report.json / demo-2d.html 的 sha256）。
- 无字体渲染字节一致快门：8 金标准图 `textmetrics._load_font=None` 子进程与正常渲染 5 产物逐个 sha256 相同（0 差异）。

### 5.4 汇总

| 项 | 数 |
|---|---|
| 两腿 rc=0（进入逐字节比对） | 52 图 |
| rc 差异 | 无 |
| 逐字节相同 | 0 图 |
| 漂移（预期：B3 改 `arrow` 字段 → certificate / demo 全量漂移） | 52 图（certificate 52 / demo 52 / layout 41 / geometry_report 3） |
| grade best 两腿 | 29 → 29 |
| 丢失的 best | [] |
| 丢失的门 | 无 |
| crossings 变差 | 无 |
| 视觉指标变差 | 无 |
| 布点变化 | 无 |
| 引擎变化 | 无 |
| 箭尖悬空 两腿 | 94 → 0 |
| 互指对：改后闭环 / 如实豁免 / 未闭环 | 5 / 10 / 0 |

### 5.5 逐图表（rc 两腿一致的已交付图）

| 图 | 引擎 | grade 前→后 | 门 前→后 | 交叉 | 线型 | 互指对（线型，顶点最小距） | 轮廓外箭尖 前→后 | 相同文件/总文件 | 改后 mutual_lens |
|---|---|---|---|---|---|---|---|---|---|
| classic__arms-race | ring-construct | best -> best | 12 -> 13  | 0 -> 0 | {"arc": 4} -> {"arc": 4} |  | 2 -> 0 | 4/7 |  |
| classic__brand-flywheel | ring-construct | best -> best | 12 -> 13  | 0 -> 0 | {"arc": 8} -> {"arc": 8} | ad_effect<->awareness arc/arc 20.9 | 1 -> 0 | 4/7 | ad_effect<->awareness tilt closed=None sep=None w/c=None |
| classic__bullwhip | column-construct | best -> best | 13 -> 14  | 0 -> 0 | {"arc": 5, "line": 1} -> {"arc": 5, "line": 1} |  | 0 -> 0 | 5/7 |  |
| classic__burnout-attrition | column-construct | best -> best | 13 -> 14  | 0 -> 0 | {"arc": 6} -> {"arc": 6} |  | 1 -> 0 | 4/7 |  |
| classic__classic-cld-growth-and-burden | spine-construct | best -> best | 14 -> 15  | 0 -> 0 | {"arc": 8, "line": 5} -> {"arc": 8, "line": 5} | crowding<->quickfix line/line 19.0; crowding<->fundamental arc/arc 16.5 | 4 -> 0 | 4/7 | crowding<->fundamental slim closed=True sep=16.5 w/c=None; crowding<->quickfix tilt closed=None sep=None w/c=None |
| classic__debt-spiral | ring-construct | best -> best | 12 -> 13  | 0 -> 0 | {"arc": 6} -> {"arc": 6} |  | 2 -> 0 | 4/7 |  |
| classic__eroding-goals | bowtie-construct | best -> best | 12 -> 13  | 0 -> 0 | {"line": 6} -> {"line": 6} |  | 2 -> 0 | 4/7 |  |
| classic__fishing-collapse | ring-construct | best -> best | 12 -> 13  | 0 -> 0 | {"arc": 7, "line": 2} -> {"arc": 7, "line": 2} | catch_amount<->fish_stock arc/arc 23.5; catch_amount<->quota line/line 9.0 | 2 -> 0 | 4/7 | catch_amount<->fish_stock tilt closed=None sep=None w/c=None; catch_amount<->quota blocked closed=None sep=None w/c=None |
| classic__fixes-that-fail | sym-construct | best -> best | 12 -> 13  | 0 -> 0 | {"arc": 4, "line": 1} -> {"arc": 4, "line": 1} |  | 0 -> 0 | 5/7 |  |
| classic__induced-demand | ring-construct | best -> best | 12 -> 13  | 0 -> 0 | {"arc": 7} -> {"arc": 7} | car_trips<->congestion arc/arc 10.6 | 2 -> 0 | 4/7 | car_trips<->congestion claimed closed=None sep=None w/c=None |
| classic__learning-flywheel | sym-construct | best -> best | 12 -> 13  | 0 -> 0 | {"arc": 4, "line": 1} -> {"arc": 4, "line": 1} |  | 0 -> 0 | 5/7 |  |
| classic__limits-to-growth | column-construct | best -> best | 13 -> 14  | 0 -> 0 | {"arc": 6, "vg": 1} -> {"arc": 6, "vg": 1} |  | 0 -> 0 | 5/7 |  |
| classic__population-logistic | column-construct | best -> best | 13 -> 14  | 0 -> 0 | {"arc": 5, "poly": 1} -> {"arc": 5, "poly": 1} | births<->population poly/arc 58.8; deaths<->population arc/arc 38.0 | 0 -> 0 | 3/7 | births<->population frozen closed=None sep=None w/c=None; deaths<->population built closed=True sep=38.0 w/c=1.225 |
| classic__renewable-resource | column-construct | best -> best | 13 -> 14  | 0 -> 0 | {"arc": 5, "line": 1, "poly": 1} -> {"arc": 7} | harvest<->stock arc/arc 38.0; regeneration<->stock arc/arc 21.2 | 1 -> 0 | 3/7 | harvest<->stock built closed=True sep=38.0 w/c=1.112; regeneration<->stock slim closed=True sep=21.2 w/c=None |
| classic__shifting-the-burden | bowtie-construct | best -> best | 12 -> 13  | 0 -> 0 | {"line": 8} -> {"line": 8} | problem<->symptom_fix line/line 10.6; fundamental<->problem line/line 10.6 | 3 -> 0 | 4/7 | fundamental<->problem frozen closed=None sep=None w/c=None; problem<->symptom_fix frozen closed=None sep=None w/c=None |
| classic__soil-erosion | ring-construct | best -> best | 12 -> 13  | 0 -> 0 | {"arc": 8} -> {"arc": 8} | crop_yield<->farming arc/arc 21.2 | 2 -> 0 | 3/7 | crop_yield<->farming built closed=True sep=21.2 w/c=0.434 |
| classic__success-to-the-successful | ring-construct | best -> best | 12 -> 13  | 0 -> 0 | {"arc": 4, "line": 4, "poly": 2} -> {"arc": 4, "line": 4, "poly": 2} | a_alloc<->a_perf arc/poly 19.0; b_alloc<->b_perf arc/arc 13.6 | 1 -> 0 | 4/7 | a_alloc<->a_perf blocked closed=None sep=None w/c=None; b_alloc<->b_perf tilt closed=None sep=None w/c=None |
| classic__tragedy-of-the-commons | column-construct | best -> best | 13 -> 14  | 0 -> 0 | {"arc": 5, "line": 1} -> {"arc": 5, "line": 1} |  | 0 -> 0 | 5/7 |  |
| classic__urban-migration | column-construct | best -> best | 13 -> 14  | 0 -> 0 | {"arc": 8} -> {"arc": 8} |  | 1 -> 0 | 4/7 |  |
| classic__wage-price-spiral | bowtie-construct | best -> best | 12 -> 13  | 0 -> 0 | {"line": 6} -> {"line": 6} |  | 2 -> 0 | 4/7 |  |
| longtail__longtail-chain-03 | cp-sat | best -> best | 12 -> 13  | 0 -> 0 | {"line": 2} -> {"line": 2} |  | 0 -> 0 | 5/7 |  |
| longtail__longtail-chain-06 | cp-sat | best -> best | 12 -> 13  | 0 -> 0 | {"line": 5} -> {"line": 5} |  | 0 -> 0 | 5/7 |  |
| longtail__longtail-chain-09 | cp-sat | best -> best | 12 -> 13  | 0 -> 0 | {"line": 8} -> {"line": 8} |  | 0 -> 0 | 5/7 |  |
| longtail__longtail-mixed-chain-cycle | column-construct | best -> best | 12 -> 13  | 0 -> 0 | {"arc": 1, "line": 5} -> {"arc": 1, "line": 5} |  | 0 -> 0 | 5/7 |  |
| longtail__longtail-mixed-chain-star | cp-sat | best -> best | 12 -> 13  | 0 -> 0 | {"arc": 2, "line": 4} -> {"arc": 2, "line": 4} |  | 1 -> 0 | 4/7 |  |
| longtail__longtail-mixed-star-cycle | cp-sat | best -> best | 12 -> 13  | 0 -> 0 | {"arc": 2, "line": 4} -> {"arc": 2, "line": 4} |  | 1 -> 0 | 4/7 |  |
| longtail__longtail-nonplanar-k33 | planarized | crossed-certified -> crossed-certified | 8 -> 8  | 1 -> 1 | {"polyline": 9} -> {"polyline": 9} |  | 2 -> 0 | 4/7 |  |
| longtail__longtail-nonplanar-k5 | planarized | crossed-certified -> crossed-certified | 8 -> 8  | 1 -> 1 | {"polyline": 10} -> {"polyline": 10} |  | 3 -> 0 | 4/7 |  |
| longtail__longtail-nonplanar-petersen | planarized | crossed-certified -> crossed-certified | 8 -> 8  | 2 -> 2 | {"polyline": 15} -> {"polyline": 15} |  | 2 -> 0 | 4/7 |  |
| longtail__longtail-star-05 | cp-sat | best -> best | 12 -> 13  | 0 -> 0 | {"arc": 2, "line": 2} -> {"arc": 2, "line": 2} |  | 1 -> 0 | 4/7 |  |
| longtail__longtail-star-07 | radial-construct | best -> best | 15 -> 16  | 0 -> 0 | {"line": 6} -> {"line": 6} |  | 4 -> 0 | 4/7 |  |
| longtail__longtail-star-09 | radial-construct | best -> best | 15 -> 16  | 0 -> 0 | {"line": 8} -> {"line": 8} |  | 0 -> 0 | 5/7 |  |
| random__random-n10-i00 | cp-sat | uncertified -> uncertified | 11 -> 12 FAIL topology_form_fallback,visual_crossings_zero | 2 -> 2 | {"arc": 3, "line": 10, "vg": 3} -> {"arc": 3, "line": 10, "vg": 3} |  | 3 -> 0 | 4/7 |  |
| random__random-n10-i01 | cp-sat | uncertified -> uncertified | 10 -> 11 FAIL anchors_standard,topology_form_fallback,visual_crossings_zero | 3 -> 3 | {"arc": 1, "line": 11, "poly": 2, "vg": 2} -> {"arc": 1, "line": 11, "poly": 2, "vg": 2} |  | 1 -> 0 | 4/7 |  |
| random__random-n10-i02 | ring-construct | uncertified -> uncertified | 10 -> 11 FAIL visual_crossings_zero | 2 -> 2 | {"arc": 2, "line": 14} -> {"arc": 2, "line": 14} |  | 1 -> 0 | 4/7 |  |
| random__random-n10-i03 | ring-construct | uncertified -> uncertified | 8 -> 9 FAIL anchors_standard,lines_no_coincidence,topology_form_fallback,visual_crossings_zero | 3 -> 3 | {"arc": 2, "line": 14} -> {"arc": 2, "line": 14} |  | 5 -> 0 | 4/7 |  |
| random__random-n10-i04 | cp-sat | uncertified -> uncertified | 11 -> 12 FAIL topology_form_fallback,visual_crossings_zero | 2 -> 2 | {"arc": 2, "line": 11, "poly": 1, "vg": 2} -> {"arc": 2, "line": 11, "poly": 1, "vg": 2} |  | 1 -> 0 | 4/7 |  |
| random__random-n10-i05 | cp-sat | uncertified -> uncertified | 11 -> 12 FAIL topology_form_fallback,visual_crossings_zero | 1 -> 1 | {"arc": 2, "line": 12, "vg": 2} -> {"arc": 2, "line": 12, "vg": 2} |  | 3 -> 0 | 4/7 |  |
| random__random-n10-i06 | cp-sat | uncertified -> uncertified | 10 -> 11 FAIL anchors_standard,topology_form_fallback,visual_crossings_zero | 2 -> 2 | {"arc": 3, "line": 11, "poly": 2} -> {"arc": 3, "line": 11, "poly": 2} |  | 2 -> 0 | 4/7 |  |
| random__random-n10-i07 | cp-sat | uncertified -> uncertified | 11 -> 12 FAIL topology_form_fallback,visual_crossings_zero | 2 -> 2 | {"arc": 6, "line": 9, "vg": 1} -> {"arc": 6, "line": 9, "vg": 1} |  | 4 -> 0 | 4/7 |  |
| random__random-n10-i08 | ring-construct | uncertified -> uncertified | 10 -> 11 FAIL topology_form_fallback,visual_crossings_zero | 2 -> 2 | {"arc": 1, "line": 14, "vg": 1} -> {"arc": 1, "line": 14, "vg": 1} |  | 3 -> 0 | 4/7 |  |
| random__random-n10-i09 | planarized | crossed-certified -> crossed-certified | 8 -> 8  | 1 -> 1 | {"polyline": 16} -> {"polyline": 16} |  | 4 -> 0 | 4/7 |  |
| random__random-n10-i10 | planarized | crossed-certified -> crossed-certified | 8 -> 8  | 1 -> 1 | {"polyline": 16} -> {"polyline": 16} |  | 3 -> 0 | 4/7 |  |
| random__random-n10-i11 | ring-construct | uncertified -> uncertified | 11 -> 12 FAIL topology_form_fallback | 0 -> 0 | {"arc": 3, "line": 12, "vg": 1} -> {"arc": 3, "line": 12, "vg": 1} |  | 3 -> 0 | 4/7 |  |
| random__random-n10-i12 | cp-sat | uncertified -> uncertified | 9 -> 10 FAIL anchors_standard,lines_no_coincidence,topology_form_fallback,visual_crossings_zero | 6 -> 6 | {"arc": 4, "line": 10, "poly": 1, "vg": 1} -> {"arc": 4, "line": 10, "poly": 1, "vg": 1} |  | 2 -> 0 | 4/7 |  |
| random__random-n10-i13 | ring-construct | uncertified -> uncertified | 9 -> 10 FAIL anchors_standard,visual_crossings_zero | 3 -> 3 | {"arc": 1, "line": 13, "poly": 2} -> {"arc": 1, "line": 13, "poly": 2} |  | 5 -> 0 | 4/7 |  |
| random__random-n10-i14 | cp-sat | uncertified -> uncertified | 11 -> 12 FAIL topology_form_fallback,visual_crossings_zero | 2 -> 2 | {"arc": 2, "line": 12, "vg": 2} -> {"arc": 2, "line": 12, "vg": 2} |  | 2 -> 0 | 4/7 |  |
| random__random-n10-i15 | ring-construct | uncertified -> uncertified | 9 -> 10 FAIL anchors_standard,visual_crossings_zero | 1 -> 1 | {"arc": 3, "line": 12, "poly": 1} -> {"arc": 3, "line": 12, "poly": 1} |  | 4 -> 0 | 4/7 |  |
| random__random-n10-i16 | planarized | crossed-certified -> crossed-certified | 8 -> 8  | 1 -> 1 | {"polyline": 16} -> {"polyline": 16} |  | 4 -> 0 | 4/7 |  |
| random__random-n10-i17 | ring-construct | uncertified -> uncertified | 10 -> 11 FAIL visual_crossings_zero | 2 -> 2 | {"line": 14, "vg": 2} -> {"line": 14, "vg": 2} |  | 1 -> 0 | 4/7 |  |
| random__random-n10-i18 | ring-construct | uncertified -> uncertified | 10 -> 11 FAIL topology_form_fallback,visual_crossings_zero | 2 -> 2 | {"arc": 1, "line": 15} -> {"arc": 1, "line": 15} |  | 0 -> 0 | 5/7 |  |
| random__random-n10-i19 | planarized | crossed-certified -> crossed-certified | 8 -> 8  | 1 -> 1 | {"polyline": 16} -> {"polyline": 16} |  | 3 -> 0 | 4/7 |  |

### 5.6 金标准 8 图如实豁免的互指对（`mutual_pairs_exempt`）

- 金标准 8 图改后的互指对：闭环 4 对（growth-and-underinvestment efforts↔performance 0.529、growth-and-underinvestment limit↔performance 1.193、fixes-that-fail fix↔problem 0.544、limits-to-growth action↔state 0.394；宽÷弦）；success-to-the-successful 走 lens-construct 引擎（既有 `lens_pairs_closed` 门，不在本门）；如实豁免 3 对：
| 图 | 对 | 状态 | 原因 / 倾角 |
|---|---|---|---|
| shifting-the-burden | fundamental<->problem | tilt | 68.2 |
| shifting-the-burden | problem<->symptomatic | tilt | 68.2 |
| tragedy-of-the-commons | gain<->usage | tilt | 68.2 |

### 5.7 全语料 52 图的互指对处置（改后腿 `meta.mutual_lens`；lens-construct 图本语料集没有）

| 图 | 对 | 状态 | 相距 / 宽÷弦 |
|---|---|---|---|
| classic__classic-cld-growth-and-burden | crowding<->fundamental | slim | sep=16.5 w/c=None |
| classic__population-logistic | deaths<->population | built | sep=38.0 w/c=1.225 |
| classic__renewable-resource | harvest<->stock | built | sep=38.0 w/c=1.112 |
| classic__renewable-resource | regeneration<->stock | slim | sep=21.2 w/c=None |
| classic__soil-erosion | crop_yield<->farming | built | sep=21.2 w/c=0.434 |

| 图 | 对 | 状态 | 原因 / 倾角 |
|---|---|---|---|
| classic__brand-flywheel | ad_effect<->awareness | tilt | corner:tilt:62.9,golden:tilt:62.9 |
| classic__classic-cld-growth-and-burden | crowding<->quickfix | tilt | corner:tilt:62.9,golden:tilt:62.9 |
| classic__fishing-collapse | catch_amount<->fish_stock | tilt | corner:tilt:55.7,golden:tilt:55.7 |
| classic__fishing-collapse | catch_amount<->quota | blocked | corner:claimed,golden:sep:9.0 |
| classic__induced-demand | car_trips<->congestion | claimed | golden:claimed,corner:claimed |
| classic__population-logistic | births<->population | frozen |  |
| classic__shifting-the-burden | fundamental<->problem | frozen |  |
| classic__shifting-the-burden | problem<->symptom_fix | frozen |  |
| classic__success-to-the-successful | a_alloc<->a_perf | blocked | corner:angle:2:2.4,angle:3:2.4,golden:ownbox:2,ownbox:3,sep:9.0 |
| classic__success-to-the-successful | b_alloc<->b_perf | tilt | golden:tilt:53.9,corner:tilt:55.5 |


### 5.8 rc 差异与未交付图

- rc 差异：无。未交付图：无。

### 5.9 冻结基线处置（与流程门分开报）

- `tests/baselines/`（ortho-v1）：`--recipe ortho` 冻结路径未改，字节钉不变（`test_delivery_contract` 全量通过）。
- `tests/golden/baseline.json`：8 图 certificate / layout 指纹变化（B3 改 `arrow` 字段与渲染字节；GaU / FtF / LtG 另有布线 / 布点变化；`gates_passed` 12→13 或 13→14 = 新门），`golden_gate.py` 不更新基线时 0/8 通过、23 条 DRIFT 行全为 sha256 / gates_passed，硬门零失败。**重祝福已获 owner 批准**（2026-11-26 10:43 飞书，default 12:23 回填批准出处），rebase 到 `60786c4` 后复跑只读门确认 23 条 DRIFT 与首跑逐条相同（无药丸相互作用），随后 `--update-baseline` 执行、复跑 **8/8 ALL GREEN**。新指纹（rebase 后基线）：

| 图 | certificate | layout | gates |
|---|---|---|---|
| eroding-goals | 3c8d3ab97bfd | 15adef85bde2 | 13/13 |
| escalation | 021476a208f4 | da023f20b7d4 | 13/13 |
| fixes-that-fail | 1d9cafd87483 | 0d4b2223cf4c | 13/13 |
| growth-and-underinvestment | e038bbbca07e | 6454e86611db | 14/14 |
| limits-to-growth | 27312bae0ad0 | bdac4270a51f | 13/13 |
| shifting-the-burden | 6e81c58755bd | f8bbf041b491 | 13/13 |
| success-to-the-successful | e952667bedb7 | d75351bae6fe | 15/15 |
| tragedy-of-the-commons | 5cd1fe86b897 | e87ee61b2dd8 | 13/13 |

### 5.10 byte-pinned 消费方（STDRAW_PIN）

- 8777 STDRAW_PIN 0.8.1 不动；本轮字节漂移登记于此，消费方升级另行裁决。

### 5.11 publishing face 同步

- `README*` / `demos/` / `docs/gallery/` / `skills/stdraw/SKILL.md` 本轮未动；demos 重渲随重祝福一并做（须过 freshness gate + 发布面验收）。

## 6. 登记 #6：GaU 版面档1（行距 96）——金标准渲染调用点带参（2026-11-26）

### 6.1 批准来源与变更内容

- **批准**：owner 2026-11-26 19:35 桌面对话回复「按你推荐做吧」（default 同日 19:30 落卡评论代记、引原话与出处）——批准 ① growth-and-underinvestment（GaU）版面采用方案档1（行距 96）；② 金标准 8 图指纹中该图 1/8 重祝福（re-bless），其余 7 张逐字节不变。
- **变更内容**：`tests/golden_gate.py` 新增 `PER_GRAPH_CLI_ARGS`，GaU 项渲染命令带 `--pitch 96`（渲染调用点带参，方案①，侵入最小）；**引擎 `stdraw/*.py` 零改动**，门表 / 阈值 / grade 语义零改动。金标准基线 `tests/golden/baseline.json` 重祝福 1/8。
- **T14 deprecated 衔接（过渡用法）**：`--pitch` 已标 deprecated（T14 落地后 CLI 对使用处输出 `[deprecated]` warning 至 stderr）。golden_gate 的渲染走 subprocess capture_output，warning 被捕获、仅在渲染出 problems 时随 stderr tail 透出——实测门输出零污染（改后 8/8 输出无 deprecated 行）；warning 同时如实记入 GaU 证书 notes（deprecated pixel parameter(s) used: --pitch），进 certificate 指纹。**过渡依赖 `--pitch`：迁移到配方级参数须另卡，且须早于 P3 减法卡物理删除 `--pitch`。**

### 6.2 验收数字（改前 = main `d9330b4` 默认渲染 vs 改后 = `--pitch 96`，同机同解释器，程序现读）

| 项 | 口径 | 改前 | 改后 |
|---|---|---|---|
| 画布（viewBox） | 宽 × 高 | 416 × 456 | 416 × 520（+64，≤584 一屏档） |
| R1（efforts↔performance）弦 | 两锚点距离 | 42.0 | 58.0 |
| R1 宽 / 弦 | 两弧最大间距（采样）÷ 弦 | 22.2 / 42.0 = 0.529 | 22.2 / 58.0 = 0.383（进入人画跨度 0.36–0.97） |
| R1 药丸距自身环线 | 药丸矩形到两弧最小距 | 50.0 | 16.9 |
| B2 药丸距自身环线 | 同上 | 22.3 | 9.3 |
| B2 药丸偏心 | 药丸中心到透镜中心距离 | 95.9 | 44.0 |
| B3 药丸距自身环线 | 同上 | 14.0 | 15.2（基本持平） |
| B2 本体（弦 / 宽÷弦） | 水平透镜 | 42.0 / 1.176 | 42.0 / 1.176（不变） |
| 门 / grade / placement | certificate | 14/14 best column-chain | 14/14 best column-chain |
| 标签硬口径 | 压框 / 压线 / 重叠 | 0 违例 | 0 违例（gate 14: 3/3 placed, all clear） |

- **明写不解决项**（行距是纵向参数，四项均不触）：R1 鼓量仍 0.5+0.5（近直线读感不变）；B2 眼形比率仍 1.176（弦 42 由列间门隙 36px 决定）；三枚标签入环几何不可达（药丸 104×18 + 两侧 4px 门隙需透镜内宽 ≥88 ⇒ 弦 ≥209，行距档最大 74）；左留白 144px 不变。四项归引擎卡（slim 通道例外化 + 透镜宽度下限 + 列间距档），前置 = owner 对 ruling A 修订的拍板。
- 数字与方案卡两档实测（`6485774` 之上的 throwaway 树）逐数相同；本登记在 `d9330b4` 复量同值。

### 6.3 重祝福与指纹

- 只读门先跑：改后首跑 = 7 张 baseline identical + GaU 两条 DRIFT（`sha256.certificate` / `sha256.layout`），`loops_audit` / `.cld` 指纹不变；随后 `--update-baseline`、复跑 **8/8 ALL GREEN**。
- 指纹（程序取自基线 JSON 新旧对照）：
  - certificate：`e038bbbca07e` → `c7752750ac94`（notes 记 deprecated 用法；`edge_box_min_clear` 记录字段 26.2 → 28.1）
  - layout：`6454e86611db` → `ec810337ce3d`
- `--update-baseline` 连带刷新 `timing_ref` 与逐图 `seconds`（全 8 图，WARN-only 不作门）——授权口径是整图重录制，计时刷新如实披露。
- A 档流程门：本变更不动引擎代码与默认 CLI 行为（非 GaU 图的渲染字节不变——金标准 7/8 baseline identical + demos 新鲜度门 I 腿绿 + debt 中英两页配方对拍逐字节相同为证），无引擎变更可比对面，不跑 A 档两腿。

### 6.4 demos / gallery

- 引擎输出字节不变（见 6.3），demos 三页 + 两 JSON 重渲对拍逐字节相同（classic-cld 三件走 I 腿；debt 中英走配方对拍）；`docs/gallery/` 截图的内容基（页面字节）未变，未重截。GaU 不在 demos / gallery 发布面内。

### 6.5 byte-pinned 消费方（STDRAW_PIN）

- 8777 STDRAW_PIN 不动：引擎默认渲染零变化。**登记提醒**：消费方若渲染 GaU，须同样带 `--pitch 96` 才得到本登记口径的版面；不带参仍输出旧版面（416×456），届时走消费侧复现重验。

### 6.6 验收（另卡）

- 数字验收门（uidesignerbot 真渲染另卡）：golden_gate 8/8 ALL GREEN、GaU 画布高 520、R1 宽/弦 0.383±0.02 / 弦 58、标签硬口径 0 违例、其余 7 图逐字节相同、GaU 四维评分目标 ≥14/20（现 11.00）。

## 7. 登记 #7：T18 代码卫生——个人裁决注释迁 `docs/adr/`（2026-11-27）

### 7.1 批准来源与变更内容

- **批准**：owner 2026-11-27 桌面对话回复「继续跑」＝按 default 推荐执行，**选项 A 获批**——批准金标准 **3/8 重祝福**（仅更新 `tests/golden/baseline.json` 里 eroding-goals / growth-and-underinvestment / tragedy-of-the-commons 三个 `certificate` sha256，变更依据＝ADR-0016 note 去人名）；其余 5 张金标准图指纹须逐字节不变。批准出处＝本卡评论（default 于 2026-11-27 22:20 转录，原话「继续跑」/「按你推荐」）。选项 B（保留人名 + grep 留例外）**不执行**。
- **变更内容**：把 `stdraw/*.py` 里 68 处「owner + 日期」个人裁决注释迁到 `docs/adr/`——每个裁决一个 ADR 文件（编号 + 拍板日期 + 决策内容 + 背景 + **原文逐字保留段**），代码注释只留规则本身（what/why of the rule）加一个 `docs/adr/ADR-XXXX` 指针。共 18 个 ADR + 索引（`docs/adr/README.md`）。另出 `docs/env-vars.md`：`STDRAW_*` 环境变量集中参考（引擎侧 5 个 + 测试/基准侧 6 个，逐个标注源码读点与影响面，全部按源码核实而非凭印象）。
- **门与阈值**：零放宽。硬门阈值、grade 语义、门集合、门注册表（`when` 生效策略槽）全部未动；本卡只改注释文字与三条证书**说明性**输出串。

### 7.2 字节影响面（改前 = main `302ecfd`，改后 = 本卡树，同机同解释器 Python 3.12.10 + ortools 9.15.6755，程序现读）

逐图渲染两树，逐文件 sha256 比对（每图 7 件产物：`layout.json` / `certificate.json` / `geometry_report.json` / `loops_audit.json` / `graph.json` / `graph.cld` / `demo-2d.html`）：

| 图 | rc 改前/改后 | 件数 | 差异产物 |
|---|---|---|---|
| `golden/eroding-goals` | 0 / 0 | 7 / 7 | `certificate.json` |
| `golden/growth-and-underinvestment`（`--pitch 96`） | 0 / 0 | 7 / 7 | `certificate.json` |
| `golden/tragedy-of-the-commons` | 0 / 0 | 7 / 7 | `certificate.json` |
| `golden/escalation` | 0 / 0 | 7 / 7 | 无 |
| `golden/fixes-that-fail` | 0 / 0 | 7 / 7 | 无 |
| `golden/limits-to-growth` | 0 / 0 | 7 / 7 | 无 |
| `golden/shifting-the-burden` | 0 / 0 | 7 / 7 | 无 |
| `golden/success-to-the-successful` | 0 / 0 | 7 / 7 | 无 |
| `examples/classic-cld-growth-and-burden` | 0 / 0 | 7 / 7 | `certificate.json` |
| `corpus/random/random-n20-i00` | 3 / 3 | 0 / 0 | 无（两腿同样 rc=3，本就不出证书，见 §7.5） |
| `corpus/random/random-n10-i03` | 0 / 0 | 7 / 7 | `certificate.json` |
| `corpus/classic/debt-spiral` | 0 / 0 | 7 / 7 | `certificate.json` |

- **布局面零漂移**：`layout.json` / `geometry_report.json` / `loops_audit.json` / `graph.json` / `graph.cld` 在上述 12 图全部逐字节相同——本卡不动任何布点、布线、门判定或渲染字节。`demo-2d.html` 在 n≤10 图上也逐字节相同；**n>10 图的页面会把证书 `notes[]` 渲进 `<p class="note">`，因此该页随之漂那一行**（实测 `examples/longtail-coupled-loops.cld`：`demo-2d.html` 仅 `n>10 caliber: ... per jacky 2026-11-26 ruling` → `per owner ruling 2026-11-26` 一处 HTML 转义文本，样式/几何/脚本零变化）。
- **证书面差异全部是说明性 note 字符串**，逐条归因（程序 diff 取证）：
  1. `ring_candidates.note`（ADR-0016）：`(D3 pending jacky's ruling)` → `(D3 ring-selection ruling pending; docs/adr/ADR-0016)`。出现在**有环候选**的图上（3 张金标准 + classic-cld + debt-spiral + n10-i03）。
  2. `reports.regularity_demoted_note`（ADR-0018）：`(n>10, jacky 2026-11-26 ruling)` → `(n>10, owner ruling 2026-11-26)`。**仅 n>10 图**出现（实测 `examples/longtail-coupled-loops.cld`，14 节点）。
  3. `notes[]` 里的 `n>10 caliber: ...` 条目（ADR-0018）：同上去人名，**仅 n>10 图**出现（并如上所述连带该图的 `demo-2d.html` 一行）。
- n≤10 图不漂降级 note、n>10 图不漂 ring note 以外的东西——两族漂移互斥，与实现口径一致。

### 7.2b A 档扩面双树对拍（43 图，程序现读）

在 §7.2 的 12 图之外，另跑 A 档可交付族全量双树对拍：**classic 19 + examples 2 + random-n10 20 + longtail 1 = 43 图**，两腿同机同解释器（Python 3.12.10 + ortools 9.15.6755 / cp-sat-layered），逐图 7 件产物 sha256 对比：

| 项 | 数 |
|---|---|
| 图数 | 43 |
| 两腿 rc 相同 | 43 / 43（**rc 不一致 0**） |
| 两腿 rc=0 | 42（1 图 `random-n10-i12` 两腿同样 rc=1 硬门 FAIL，产物照常落盘且逐字节可比） |
| 逐字节完全一致 | 2 图（`arms-race`、`random-n10-i00`——无环候选、n≤10，两条 note 都不触发） |
| 仅 `certificate.json` 漂 | 40 图 |
| `certificate.json` + `demo-2d.html` 漂 | 1 图（`longtail-coupled-loops`，n=14，页面内嵌 `notes[]` 一行） |
| 其它产物漂（layout / geometry / loops_audit / graph） | **0** |
| 落盘产物总数逐字节比较 | 43 图 × 7 件 = **301 件**，其中 261 件逐字节相同、40 件证书面 + 1 件页面面 = 41 件差异全部落在 §7.2 的三条 note 上 |

- 逐图差异行全部由脚本分类到三条 note（未归因差异 **0**），没有出现第四条 note 或任何结构字段变化。
- 随机 n20 族**不在本对拍内**：本机该族多数 rc=3（结构化拒绝，两腿一致）且单图上百秒到数分钟；n>10 的两条 note 取证改用 `longtail-coupled-loops`（14 节点，正常出证书），见 §7.5 不解决项第 1、2 条。

### 7.2c 「只改注释」的代码等价证明（AST 去字符串化对拍）

注释不进 AST，因此把两版模块的每个字符串常量都替换成占位符后对拍 `ast.dump`，即可证明**控制流 / 数值 / 名字零变化**：

- 20 个改动模块 **20/20 CODE-EQUIVALENT**（`__main__` / `_interactive_js` / `anchor_prior` / `anchors` / `bowtielayout` / `cert_gates` / `check` / `columnlayout` / `comblayout` / `edgerules` / `gates` / `layout_auto` / `metrics` / `planarized_layout` / `radellayout` / `render` / `routing` / `spinewinglayout` / `symlayout` / `themes`）。
- 变化的字符串常量共 **58 处**，全部为 docstring / CLI help 文本 / 三条证书 note；三者中只有第三条进产物字节——与 §7.2 / §7.2b 的产物对拍结论互相印证。

### 7.3 冻结基线处置（与流程门分开报）

- `tests/baselines/`（ortho-v1）：**已随 2026-11-24 裁决退役**，仓内无此目录，本卡无基线可动。
- `tests/golden/baseline.json`：**重祝福 3/8 已获批**（§7.1）。只读门首跑 = **5/8 pass + 3 DRIFT**（DRIFT 行全部且仅为 `sha256.certificate`：`eroding-goals 077af414e901 → d64342891080`、`growth-and-underinvestment 10d6a97c3d0b → 56b01fb21101`、`tragedy-of-the-commons 545031a2afb1 → 514be7cd4790`；`cld` / `loops_audit` / `layout` 三类指纹**全部不变**，硬门零失败）；随后 `--update-baseline` 执行、复跑 **8/8 ALL GREEN**。
- `--update-baseline` 连带刷新 `recorded`（2026-11-26 → 2026-11-27）、`timing_ref`（avg 1.08 → 1.06 s，max 2.22 → 2.18 s）与逐图 `seconds`（全 8 图）——计时刷新为 WARN-only 非门，此处如实披露。

| 图 | certificate 改前 | certificate 改后 | layout | gates |
|---|---|---|---|---|
| eroding-goals | `077af414e901` | `d64342891080` | 不变 | 13/13 best |
| growth-and-underinvestment | `10d6a97c3d0b` | `56b01fb21101` | 不变 | 14/14 best |
| tragedy-of-the-commons | `545031a2afb1` | `514be7cd4790` | 不变 | 13/13 best |
| 其余 5 图 | 不变 | 不变 | 不变 | 不变 |

- **A 档流程门（双腿 sweep）**：本卡只改注释与三条说明性 note 字符串，不动任何布点/布线/门判定；§7.2b 的 **43 图双树逐字节对拍**（301 件产物）已把影响面界定到「三条 note、布局面零漂移」，逐图差异行经脚本分类后未归因差异 = 0。形式上的 A 档 61 图全量双腿仍未跑，见 §7.5 第 1 条。

### 7.4 demos / gallery / publishing face

- `demos/classic-certificate.json` 同步重渲（改后引擎实渲与仓内文件逐字节相同：环探针 note 一行差异）；`demos/classic-cld-2d.html` **逐字节未变**（HTML 不内嵌证书 note）；`demos/classic-loops-audit.json` 未变。I 相新鲜度门（demo + certificate + loops-audit 三件逐字节对拍）绿。
- `docs/gallery/` 截图的内容基（页面字节）未变，未重截。
- **README / README_zh-CN 本卡未改**：核查确认两文件已是现行口径（3D 层已删、`layout-diff` / `--compare-auto` 已在 `tools/`、交互层 `--interactive` 显式 opt-in、`--from-layout` 与人工校准闭环写为现役资产），无陈旧引用可修——故不触碰 publishing face，避免无谓字节漂移。`AGENTS.md` 按卡面硬限**未碰**。

### 7.5 明写不解决项

1. **A 档 61 图形式门未按 `sweep_tiers.py` 全量双腿跑**：本卡以自建双树对拍覆盖 **43 图**（classic 19 + examples 2 + random-n10 20 + longtail 1，见 §7.2b），逐图 7 件产物逐字节比较、差异全部归因到三条 note；但**随机 n20 族（20 图）未纳入**，因此与「A 档 61 图双腿形式门」不完全等价。若 owner 要求形式齐备，须另跑 `benchmarks/tools/sweep_tiers.py --tier A` 两腿并把结果回填本册（注意该工具的 `--compare` 只记 rc=0 图的哈希，rc=1 图需另行目录树比对）。
2. **随机语料 n20 族在本机多数 rc=3（两腿同样 rc=3，本就不出证书），且单图上百秒到数分钟**：这是既有语料状态，非本卡造成；该族既给不了证书面漂移样本、性价比也极低，故 n>10 的漂移取证改用 `examples/longtail-coupled-loops.cld`（14 节点，正常出证书，且实测页面与证书两面漂移都只落在降级 note）。
3. **`docs/` 之外的散文仍保留「jacky」称谓**：本卡只清 `stdraw/*.py`（卡面验收口径），`docs/*.md`、`tests/*.py`、`benchmarks/**` 中的历史称谓未动——它们是历史记录与测试夹具，卡面明确「ADR/测试 fixtures 里如实保留历史的不算」。ADR 原文段内的人名属**逐字保留的裁决原文**，同样保留。
4. **ADR 原文段的行号指向迁移前的 `main` 树**：`docs/adr/*` 的「Source: `stdraw/xxx.py:N`」标注的是**迁移前**的坐标（原文即出自该处），迁移后行号会漂——这是刻意的（原文可回溯到它被写下时的位置），不是笔误。
5. **本卡不动 `AGENTS.md`**：卡面硬限；其「Version」段与 CLI 表中的历史段落仍可能与现状有出入，属另卡范围。
6. **`--pitch` 仍标 deprecated**：T14 过渡用法未动，迁移到配方级参数须另卡，且须早于 P3 减法卡物理删除 `--pitch`。

### 7.6 byte-pinned 消费方（STDRAW_PIN）

- 8777 STDRAW_PIN 0.8.1 不动。本卡布局面零漂移（`layout.json` 逐字节相同），消费方若只消费坐标则**零影响**；若消费方连证书 note 一起比对，环探针 note 一行会不同（仅说明文字，判定字段不变）。消费方升级另行裁决。

## 8. 登记 #8：0.10.0 版本收尾——金标准证书哈希随引擎版本号重录（2026-11-28）

### 8.1 批准来源与变更内容

- **批准**：owner 2026-11-28 桌面会话对 0.10.0 发版回「B」（= 现在全套发；版本收尾须 owner 在场批，本条即该批准的执行记录）。
- **变更内容**：`tests/golden/baseline.json` 的 **8 条 `sha256.certificate`** 随版本号 0.9.0 → 0.10.0 重录；同批更新 `_meta.engine_version` 与 `_meta.recorded`。**其余字段零改动**（grade / placement / gates_passed / crossings / visual_crossings / nodes / edges / loops_declared / `sha256.cld` / `sha256.layout` / `sha256.loops_audit` 全部逐字段相同）。
- **触发原因（非行为回归）**：`stdraw/metrics.py` 的 `certificate_auto` 头部写死 `"version": _PKG_VERSION`，而 `_PKG_VERSION` 跟随 `stdraw.__version__`。版本收尾 bump 版本号 → 证书字节变 → 金标准门的证书哈希必然漂移。**这是金标准门建立（2026-11-24）以来的第一次版本收尾相撞**（此前 v0.8.2 → v0.9.0 发版时金标准基线尚不存在），因此这条口径此前未被触发过。

### 8.2 字节影响面与「只有版本号变了」的证明

**证明方法（双树渲染 + 逐字段 diff + 按基线自身哈希口径复算）**：在 bump 前的引擎树（`cc0c19a`，version 0.9.0）与 bump 后的引擎树（`218efcd`，version 0.10.0）分别渲染全部 8 张金标准图，然后：

1. **逐字段证书 diff**：8/8 图的 `certificate.json` 差异字段集合 **恰好 = `[".version"]`**（`"0.9.0"` → `"0.10.0"`），其余字段（grade / gates / metrics / loops / geometry）全部逐值相同。
2. **按基线自身口径复算**（`tests/golden_gate.py` 的 `hash_caliber`：`cld` = fixture 字节 CRLF→LF；`certificate` / `loops_audit` = 文件字节 CRLF→LF；`layout` = 规范化 JSON 且**剔除 `engine_version`**）：
   - 证书哈希：变化（8/8），但**去掉 `version` 字段后两侧哈希完全相同** → 版本号是唯一成因；
   - 布局哈希：**8/8 相同**（口径本就剔除 `engine_version`）；
   - `loops_audit` 哈希：**8/8 相同**；
   - `cld` 哈希：未触碰 fixture，**8/8 相同**。
3. **CI 侧独立佐证**：失败 run 的漂移清单只有 `sha256.certificate drift` 一类共 8 条，**没有一条** grade / gate / crossings / geometry 漂移行——语义门全部逐值通过。

**结论**：漂移是版本号进入证书字节所致，**不是行为回归**。正确动作是按门自身的机制显式重录（`--update-baseline`，仅批准卡可做），而非回退版本或放水门。

### 8.3 与 `demos/` 的同步

- `demos/classic-certificate.json` 同批重渲（同样只差 `"version"` 一行：13005 → 13006 字节）；demo 新鲜度门（ci_checks 相位 I）在 bump 后本地复跑 **双绿**（demo HTML 逐字节相同 + 证书逐字节相同）。
- `demos/classic-cld-2d.html` 与 `demos/classic-loops-audit.json`：**逐字节未变**（HTML 不嵌版本号）。

### 8.4 明写不解决项

1. **口径本身未修**：`certificate` 哈希口径仍含 `version` 字段（`layout` 口径已剔除 `engine_version`）。即**下一次版本收尾仍会触发同一条 8/8 漂移**，需再次显式重录。是否把证书口径改为「剔除 `version` 字段」属**口径变更**（放宽漂移检测面），须 owner 单独拍板，本卡不擅自改。
2. **`_meta.python` 未更新**：基线记录的解释器版本仍为 `3.12.10`（本次重录用的是同一解释器 `Python312`，字节口径一致）；平台字串 `Windows-11-10.0.26300-SP0` 同步保持。
3. **计时参考值随之刷新**（`seconds` / `timing_ref`）：本机 8 图 avg 1.06s → 1.30s、max 2.18s → 2.63s。计时**从不参与门判定**（runner 速度不是仓库属性），门只在慢于参考 2 倍时大声告警。
4. **其余 7 张金标准图的语义字段零改动**：`grade` 全为 `best`，门数 13/13 ~ 15/15，交叉 0，loops 问题 0，几何 fail 0。

### 8.5 与历史口径订正的关系

本条同时订正一条**已过时的记载**：AGENTS.md 历史版本段曾声称「版本号永不进入输出字节、`demos/classic-certificate.json` 在 bump 前后逐字节相同」。该说法自 `3b0e55a`（证书版本号改为跟随 `stdraw.__version__`）起已不成立——现由 `stdraw/delivery.py` 的 `engine_version` 与 `stdraw/metrics.py` 的 `version` 字段共同使版本号进入交付字节。本次 0.10.0 收尾的证书重渲与金标准重录都是该事实的直接后果。

## 9. 登记 #9：证书哈希口径改为「剔除 version 值」——版本收尾不再漂基线（2026-11-28，owner 裁定 B）

### 9.1 批准与动机

- **批准**：owner 2026-11-28 桌面会话对「证书哈希口径要不要改」回「**B**」= 改口径，一次到位。
- **动机**：登记 #8 暴露的口径不对称——`layout` 口径早已剔除 `engine_version`（理由：该字段每次版本收尾都会动），而 `certificate` 口径把跟随 `stdraw.__version__` 的 `version` 值算进哈希 → **每次版本收尾都要重录 8 张图**，且重录时用「整体换 8 条哈希」的方式掩盖同批真实回归的风险更高。改成剔除后，版本收尾与基线解耦。

### 9.2 变更内容（实现面）

- `tests/golden_gate.py` 新增 `sha256_file_certificate()`：先按既有规则把 CRLF 折成 LF，再只把**顶层 `version` 字段的值**替换为占位串 `"<version>"`，然后取 sha256。
- **fail-closed 三判**：证书不可解析、`version` 不是非空字符串、或该值在文件里出现次数 ≠ 1，一律 `SystemExit` 拒跑——**绝不静默回落到「哈希原始字节」**，否则口径失效却不报警。
- `_meta.hash_caliber["certificate"]` 与模块 docstring 的口径清单同步改写：证书字节按 LF 归一后，把顶层 `version` 字段的值中和为占位串 `"<version>"`。
- **仍是字节级钉死**：字段名、字段位置、缩进、分隔符、以及其余所有值都在哈希内（比 `layout` 的 canonical-JSON 路线更严——那条会抹掉格式差异）。

### 9.3 证明（三层，全部实测）

1. **重录后 changed 列表恰 8 条**：`sha256.certificate` × 8，**无一条** grade / gate / crossings / geometry / `sha256.layout` / `sha256.loops_audit` / `sha256.cld` 变化。
   ```
   eroding-goals 92a842ec629c -> 45908ca41f82      limits-to-growth 34e458e6acef -> 825a22b272f7
   escalation e87c74148b5f -> 73579831a66e         shifting-the-burden 0862bd68ef2f -> d232d41a6092
   fixes-that-fail 30fcba32facc -> c7d2ceb2cc5b    success-to-the-successful d05100c005dc -> c50599628945
   growth-and-underinvestment 94582644c058 -> 23ab9a10a02c   tragedy-of-the-commons 7d58fa282968 -> 3f3612bfaacb
   ```
2. **真实数据不变量（8/8）**：取 8 张图的真实 0.10.0 渲染证书（GaU 用其 `--pitch 96` 渲染），把 `version` 原文改写成 `0.9.0` 后再算指纹——**8/8 指纹不变，且等于新基线值**。这就是「版本号不再影响基线」的直接证据。
3. **新增 3 条单测**（`tests/test_golden_set.py`，随 pytest 道常跑）：
   - `test_certificate_caliber_ignores_the_version_value`：0.9.0 与 0.10.0 两份证书指纹相同；
   - `test_certificate_caliber_still_pins_everything_else`：`grade` 变值必漂、缩进变必漂（格式仍在钉内）；
   - `test_certificate_caliber_fails_closed`：缺 `version` 拒跑；`{"version":"0.10.0"}` 这种无空格写法（命中 0 次）也拒跑。

### 9.4 明写不解决项

1. **`demos/` 新鲜度门（ci_checks 相位 I）仍逐字节比 `certificate.json`**——版本 bump 后 demo 证书仍必须重渲。这是**交付面事实**（仓库里那份 demo 证书确实写着旧版本号），不是基线口径问题，故**不**豁免。
2. **AGENTS.md L25「golden archetype baselines, byte-pinned」是概括表述**，未改：受保护文件（每次写入需 owner 当场批准），且该句非事实错误（证书除 `version` 值外仍字节级钉死）。口径正文以本登记 + `tests/golden_gate.py` docstring + `tests/golden/baseline.json` 的 `_meta.hash_caliber` 为准。
3. **登记 #8 的处置不是白做**：那次重录是当时的正确动作（口径未改前，基线必须反映当时的字节）；本条是在其证明结论（version-only）基础上做的一次性口径升级。
4. **不追溯历史**：`v0.9.0` 及更早的 tag 内 `baseline.json` 口径保持原样，不改写历史提交。

## 10. 登记 #10：证书 `grade_semantics` 残留 3D 口径 → 历史读回口径（2026-11-28，并入 0.10.1）

### 10.1 批准来源与变更内容

- **批准**：owner 2026-11-28 对 WorkBuddy P4 评审的处置（处置卡由主 session 拆出，卡面明令本条走批准后的 re-bless）。本卡另含两处文档口径（`AGENTS.md` 受保护，另走 owner 当场批准；`CHANGELOG.md` 本卡自改）。
- **变更内容（唯一产物面改动）**：`stdraw/metrics.py` 的证书 `grade_semantics` 逐字替换一句——
  - 旧口径：`3d` 被描述成「文档里那个 3D 交付层级」所在（原文为一句英文，见改动前的 `git show 803a958:stdraw/metrics.py`）。
  - 新口径：`3d` 仅为历史读回令牌——旧（0.10.0 之前）证书仍可据此校验，而它所描述的 3D 交付路径已于 0.10.0 移除。
  - 字符串 511 → 600 字符（+89 B/图）。同串其余字面（grade 定义 / 软目标段 / `second` 段 / single-source 指针）与代码其余部分**零改动**。
- **语义**：`3d` 由「文档里描述的 3D 交付路径」改为「仅旧证书读回令牌」，与 `docs/grading-contract.md` §1 现行口径一致（3D 已于 0.10.0 物理删除）。
- **同批交付面**：`demos/classic-certificate.json` 重渲（唯一 diff 为同一行）。

### 10.2 证明（双树渲染 + 逐叶子 diff，程序现读，2026-11-28）

- **方法**：改前树 = main `803a958`；改后树 = 本卡工作树。两侧各渲染 8 张金标准图 + classic demo（GaU 用 `--pitch 96`，与 `tests/golden_gate.py` 同口径；Python 3.12.10 + ortools 9.15.6755），对 7 类产物做递归叶子 diff（对比脚本与本条原始输出随处置卡留档，不入库）。
- **结果 9/9**：`certificate.json` 差异叶子集合 **恰好 = `["grade_semantics"]`**；其余 6 类产物（`layout.json` / `loops_audit.json` / `geometry_report.json` / `demo-2d.html` / `graph.json` / `graph.cld`）**逐字节相同**。
- **证书字节**：9 份全部 **+89 B**。
- **门侧独立佐证**：re-bless 前 `python tests/golden_gate.py` 报 **8 条、且只有 `sha256.certificate drift`**，无 grade / gate / crossings / geometry / `sha256.layout` / `sha256.loops_audit` / `sha256.cld` 漂移行。
- **解释器无关**：同一改后树用 Python 3.14.7 与 3.12.10 渲染，8/8 证书逐字节相同（重录用 3.12.10，故 `_meta.python` 保持 `3.12.10`）。

| 图 | 证书哈希（前 12 位 → 后 12 位） | 证书字节 |
|---|---|---|
| eroding-goals | 45908ca41f82 → c9f29257a7b5 | 10179 → 10268 |
| escalation | 73579831a66e → 3dd34481d9d4 | 7749 → 7838 |
| fixes-that-fail | c7d2ceb2cc5b → 0875f9f7b42a | 8068 → 8157 |
| growth-and-underinvestment | 23ab9a10a02c → e2edcaf42783 | 9778 → 9867 |
| limits-to-growth | 825a22b272f7 → 189e50d6387c | 8069 → 8158 |
| shifting-the-burden | d232d41a6092 → e4c0f4e46ac6 | 8623 → 8712 |
| success-to-the-successful | c50599628945 → 50881c0ccdcd | 8127 → 8216 |
| tragedy-of-the-commons | 3f3612bfaacb → fef605f9f169 | 10056 → 10145 |
| classic demo（`demos/classic-certificate.json`） | —（交付面重渲） | 13006 → 13095 |

### 10.3 冻结基线处置（与流程门分开报）

- `python tests/golden_gate.py --update-baseline`（批准卡通道；重录前已按 §10.2 证明差异集合恰 `[".grade_semantics"]`）：**changed 列表恰 8 条 `sha256.certificate`**，无其它键。
- 基线文件 diff 另含 `seconds` / `timing_ref`（计时参考值，从不参与判定）；**无** grade / placement / gates_passed / crossings / visual_crossings / nodes / edges / loops_declared / `sha256.cld` / `sha256.layout` / `sha256.loops_audit` 变化；`_meta.python` / `_meta.platform` / `_meta.engine_version` 不变。
- 重录后 `tests/golden_gate.py` **8/8 ALL GREEN**；`tests/ci_checks.py` 相位 I（demo / certificate / loops-audit 新鲜度）、K（语言分区）、M（金标准集）本地复跑全绿。

### 10.4 byte-pinned 消费方（STDRAW_PIN）

- 任何 pin 了 0.10.0 证书字节的消费方需重取一次：**字段语义零变**（grade / 门集 / 度量逐值相同），只有 `grade_semantics` 文本澄清；新 pin 值见 §10.2 表。
- **明写不解决项**：本条不扩大口径——证书哈希仍按登记 #9 剔除 `version` 值、其余字节钉死；`grade_semantics` 属真实内容，故按真实变更重新钉基线，而不是把它加入剔除清单。
