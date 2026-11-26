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
