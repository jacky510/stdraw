# M1-B 消融报告：平面化候选源（planarized source）

状态：M1-B 交付物**返修版 v2**（独立复核 MAJOR-1 归因更正 + 删源对照列 +
构造质量修复 + 6 MINOR 处置；见 §8 处置清单）。分支
`p1/m1b-ablation-fix`；基线 = M1-A（main 合并态，5da2257）。方案依据：
优化方案综合稿 v1.3.1 §7 Phase 1 M1-B + §15(3)。
本报告不含内部卡号（仓泄漏门禁口径）；原始输出见 kanban/evidence/ 对应
证据目录（不入库），复跑命令见文末。

> **v2 归因更正（MAJOR-1，必须先读）**：v1 报告 §4.1 曾把 K₅/K₃,₃ 的
> 交付增益记在平面化源名下——**这是错误的**。复核实测：v1 时点交付
> 赢家是 **ring-cycle:000（M1-A 既有模板源）**，平面化候选 3/3 被
> stage-1 硬门结构性淘汰（min_card_gap=12<16），删掉整个平面化源重跑
> 交付逐字节不变（边际贡献实测=0）。v1 时点的真实增益来源 =
> **M1-B 解除 M1-A 的 `planarized-l1-incumbent` L1 短路**，让既有
> ring-cycle 模板在 L1 作用域内可竞争——不是新源本身。v2 修复构造
> 质量后平面化源首次真实交付（Petersen，见 §4.1），两件事在 §4/§8
> 分别记账，不再混写。

## 1. 新增源口径（实现拍板记录）

`stdraw/candidate_planar.py`（构造核）+ `candidate_sources.py`（接入）：
删边集**帽内全枚举**（|D|≤2；帽 `PLANAR_MAX_DELETION_SETS=4`，取确定性
(size, 边序) 序的前 4 个——K₅ 全枚举 55 个解、K₃,₃ 45、Petersen 60，
实测返回前 4 个且与独立全枚举前缀逐项相等；**帽是预注册资源规则，不是
字面全枚举**）→ 嵌入×外面选择（G−D 上复用 `planar.py` 机器：sorted
插入的 check_planarity 旋转系统 + `faces_of` 面枚举 + Even-Tarjan st
编号 + 可视性表示 + 行压缩装箱；外面选择 = 每条真实边的双向 (s,t)
枚举，覆盖嵌入任一镜像的全部面）→ 面约束画法（全整型 2px 网格坐标）
→ 双变体插回（A = 插回交叉数最小 + 交叉对描述字典序；
B = J_cross=Σw(c) 最小，w=2 若交叉涉及主环边否则 1——§15(3) 的
「平面面均匀度仅作平面化候选附加指标」口径同样遵守：面信息只进
metadata，零评分权）。

**构造卡高口径 = 评估口径（v2 修复）**：面约束画法的 LayoutConfig 不再
复用 ortho 面默认值（card_h=42 / pitch=56 / 间隙 8），改按管线评估口径
参数化——`card_h=ctx.card_h`（auto 文本度量）、`pitch=card_h+min_gap`、
行内/列间最小间隙=`cfg.min_gap`（18）。修前构造/评估口径错位导致每张
触发图的全部 emitted 候选被 stage-1 卡 gap 门结构性淘汰（实测
min_card_gap=12<16）；修后全候选 min_card_gap=18≥16。只参数化平面化源
的构造；`planar.py` 默认值（ortho-v1 冻结路径）不动。

**零评分权与发出口径**：每个删除集在**构造层**完成帽内最多 12 个 (s,t)
面构造；按方案 §15(3) 的 A/B 定义**只发出 best A（构造相同的 best B 并
入 A 并打 `variant_b_same_construction` 标注；构造不同的 best B 作为独立
候选发出）**——A/B 选择是方案规定的构造定义，不是下游质量筛选。发出后
进统一管线，编排器每源配额 2（M1-A 既有口径）裁决。静态 import lint
扩展覆盖新模块（tests/test_candidate_planar.py）。

**确定性合同**：sorted 插入 + 全排序迭代；实测 PYTHONHASHSEED
0/1/2/12345 四种子下 K5−e / K3,3−e / Petersen 旋转系统逐字节一致；
双向 (s,t) 枚举对嵌入镜像不变 ⇒ 候选集不依赖探针返回哪个镜像。
同图双跑字节一致（测试 + 消融 runner 双树实测）。

**预算（预注册资源帽，非质量筛选）**：`PLANAR_MAX_DELETE=2`、
`PLANAR_MAX_DELETION_SETS=4`、`PLANAR_MAX_ST_PER_SET=12`；编排器每源
配额 2 不变——v2 实测：k5/k33 emitted 4 / kept 2；petersen emitted 6
/ kept 2（其中 2 个删除集的 B 与 A 构造不同，B 独立发出）。

**触发规则（纯拓扑）**：核心子图非平面才启用（`core_is_planar` 探针）；
平面图 `disabled_by_rule`，n>20 沿用模板统一节点帽。

## 2. 管线作用域变化（M1-B 契约变更）

M1-A 的 L1 短路（`planarized-l1-incumbent`）退役：候选池现进入 L1
平面化作用域运行。**L1 阶梯的交付楼层语义不变**——守卫的 incumbent 侧
就是 L1 见证图，候选仅在交付证书口径不劣于楼层时才替换交付
（fail-closed 一致性断言保留）。非平面图 provenance 增注
`incumbent_planarization_mode`；平面图 provenance 不增键（负例保护）。
对应测试 `test_planarized_l1_scope_pool_runs_with_l1_floor`（替代原
L1 短路用例）。

**§2 契约的两层效果分开记账（v2 归因纪律）**：(a) 短路解除让既有模板
候选在 L1 可竞争——这一层与平面化源无关，k5/k33 的交付变化属于它；
(b) 平面化源自身的交付贡献由 §4.1 删源对照列实测——只有删源会改变
交付的图，才能把增益记在新源名下（v2 实测 petersen 成立）。

## 3. 长尾验收集

`benchmarks/corpus/longtail/`：12 图（链 3 / 星 3 / 非平面 3 / 混合 3，
全部 n≤10，族标签在首行注释；K₅ / K₃,₃ / Petersen 为非平面成员，构造依据
见该目录 README.md）。Phase 0 空族（链/星/非平面 0 覆盖）由此补齐。
v2 修正：`longtail-mixed-chain-cycle` 初版实为纯 C4（无悬挂链，族标签
偏松）——返修正构为 4-环+挂链（n=6, m=6），标签与构造一致（§8
MINOR-5）。

## 4. 消融结果（15 图 = 12 长尾 + 3 既有负例夹具）

方法：双 checkout（m1a=M1-A@5da2257 / m1b=本分支）各跑 candidate-v1 +
auto-v2；runner = `benchmarks/tools/ablate_m1b.py`（v2 增**删源对照**
：触发图上对每个实际 generated 的源逐个运行时摘除重跑，输出每源边际
贡献表），原始输出 `ablation-raw.json`（证据目录）。

### 4.0 归因更正（MAJOR-1 处置，v1→v2 对照）

| 图 | v1 报告的（错误）归因 | 复核实测（v1 时点） | v2 构造修复后 |
|---|---|---|---|
| k5 | 「平面化源增益」 | 交付赢家=ring-cycle:000；平面化候选 3/3 被 stage-1 淘汰（min_card_gap=12<16）；删源重跑交付逐字节不变（新源边际=0） | 交付仍=ring-cycle:000；删源交付不变（边际=0） |
| k33 | 同上 | 同上（同构出局路径） | 交付仍=ring-cycle:000；删源交付不变（边际=0） |
| petersen | 「候选被诚实拒绝（geo fails 1>0）」——该 geo fail 属 layered-v082:003，非平面化源 | 楼层回退；删源交付不变（边际=0） | **交付=planarized:002**（新源首次真实交付）；删源退回 incumbent-fallback（**边际>0**） |

v1 时点的「正增益」真实来源 = §2(a) L1 短路解除 + 既有 ring-cycle
模板；平面化源当时的边际贡献实测 = 0。v2 构造修复（§1）后平面化源在
petersen 上产生了真实交付增益——增益归属以删源对照列为准，不再按
「接入了新源」推断。

### 4.1 触发图（3/3 非平面成员触发，守卫元组=字典序：index4=anchor 违例、
index10=spacing_cv、index11/12=−min_card_gap/−min_clear）

| 图 | M1-A 交付 | M1-B 交付 | 交叉数 M1-A→M1-B | 守卫元组 候选 vs 楼层 | 删源对照（v2 实测） |
|---|---|---|---|---|---|
| k5 | L1 incumbent | 候选交付 **ring-cycle:000** | 1→1（=cr(K₅) 最优） | cv **0.384→0.0**；anchor 违例 20=20；min_card_gap 332.4→75.6、min_clear 78.8→18.5（更差） | −ring-cycle：交付改变（边际**>0**）；−planarized：交付不变（边际=0） |
| k33 | L1 incumbent | 候选交付 **ring-cycle:000** | 1→1（=cr(K₃,₃) 最优） | cv **0.56→0.0**；anchor 违例 18→1；min_card_gap 94.0→52.5、min_clear 48.1→16.0（更差） | −ring-cycle：退回楼层（边际**>0**）；−planarized：交付不变（边际=0） |
| petersen | L1 incumbent | 候选交付 **planarized:002** | 2→2（=cr(Petersen) 最优） | anchor 违例 **30→1**（字典序主导分量）；cv 0.541→0.569（略差）；min_card_gap 106.5→18.0、min_clear 46.7→17.6（更差） | −planarized：退回 incumbent-fallback（边际**>0**）；−ring-cycle：交付不变（边际=0） |

**守卫元组的诚实读法（MINOR-1 处置）**：守卫元组是字典序——k5/k33 行
spacing_cv 0.384/0.56→0.0 在元组序里先于 min_card_gap/min_clear 分量，
候选凭 spacing_cv 严格占优而通过守卫；k33 另有 anchor 违例 18→1 先行
占优。**「其余分量不劣」不成立**：k5 实测 min_card_gap 332.4→75.6、
min_clear 78.8→18.5（更差），k33 同类（94.0→52.5、48.1→16.0），
petersen 的 cv/min_card_gap/min_clear 三项也更差、由 anchor 违例 30→1
先行占优通过。这是字典序守卫的设计语义（先保排序靠前的正字分量），
逐分量如实列出，不粉饰为全面不劣。

**交付赢家归属（对账 §4.0）**：k5/k33 的交付候选是 **ring-cycle:000**
（M1-A 既有模板源）——v1 报告把这两行增益记在平面化源名下属归因错误；
删源对照实测：k5/k33 摘除 planarized 交付逐坐标不变（新源边际=0）、
摘除 ring-cycle 交付才改变。petersen 的交付候选是 **planarized:002**
（v2 构造修复后平面化源首次真实交付；交叉数保持 cr(Petersen)=2），
摘除 planarized 后退回 incumbent-fallback——只有这一行的交付增益可以
记在平面化源名下。每源边际贡献汇总：ring-cycle >0（k5/k33）、
planarized >0（petersen）、layered-v082 =0（3/3 触发图控制）。

### 4.2 非触发图（12 = 9 平面长尾 + 3 负例夹具）

| 保护口径 | 结果（v2 实测） |
|---|---|
| auto-v2 配方 layout 逐字节（15/15 全图） | **15/15 IDENTICAL** |
| candidate-v1 交付坐标逐字节（12 非触发图） | **12/12 IDENTICAL** |
| candidate-v1 全 layout 字节 | 非触发图按设计不同：provenance 诚实记录新源的 `disabled_by_rule` 行（与 M1-A 验收口径同类） |

## 5. 复跑命令

```bash
# 双树消融 + 删源对照（原始输出落 --outdir）
python benchmarks/tools/ablate_m1b.py \
  --m1a-root <M1-A checkout> --m1b-root <本分支 checkout> \
  --outdir <evidence dir> --python <interpreter>
# 删源对照默认只跑触发图（--drop-scope all 覆盖全部图）

# 定向测试（含构造口径防回归 + 语料内 A/B 分化钉）
python -m pytest tests/test_candidate_planar.py tests/test_candidate_pool.py -q

# 全量铁门
python -m pytest tests/ -q && python tests/ci_checks.py
```

删源对照实现：runner 子进程以环境变量 `STDRAW_DROP_SOURCE=<源名>`
运行时摘除该源（同时改 `candidate_sources.SOURCE_ORDER` 与 orchestrator
绑定后重跑 candidate-v1），对比交付模式与交付坐标 sha256——**增益只有
在「删源会改变交付」时才能记在该源名下**；输出 `drop_rows`（逐图逐源）
与汇总表（每源：控制图数 / 交付改变图数 / 边际贡献 >0 或 =0）。

## 6. 已知边界（诚实声明）

- 每源配额 2 使 emitted 候选只保留前 2 个（结构配额、确定序，非质量
  筛选）——petersen 的 B 变体（删除集 2/3）因配额未进 kept；配额放宽
  留给 M2 拍板。
- 删除集帽 4 / 每集构造帽 12：n≤20 大图上可能截断枚举（帽是预注册资源
  规则，metadata 记录 `deletion_sets_capped` / `st_per_set_capped`）。
- 旋转系统跨进程稳定性实测覆盖 K5−e / K3,3−e / Petersen 族（3 连通平面
  子图嵌入唯一镜像定理族）；含 2-分离嵌入自由度的图未逐一实测——同进程
  双跑一致性由测试保证，跨进程字节一致性在这类图上列为待实测边界。
- variant B 判别力已入语料：petersen 删除集 2/3 的 B 与 A 构造不同
  （坐标指纹不同），并有测试钉住（§8 MINOR-4）。
- k33 交付的 `edge_box_min_clear=16.0` 恰好压硬门下限（≥16，复核
  INFO-1）：后续任何阈值上调都会翻红——阈值不动是现状前提，上调须先
  改构造，先记在此。
- 新源插入使同源候选编号位移（layered-v082:001→:003，复核 INFO-2）：
  仅 provenance churn，无交付影响。

## 7. 验证状态（实测，v2）

- 全量 pytest（本分支，含构造口径修复与 2 个新增防回归测试）：
  **343 passed, 1 skipped**（2447.5 s；skip 为既有跳过项；与 ci_checks
  并行跑、隔离 TMPDIR，无固定名互踩）。
- ci_checks 全量（1900.5 s）：除语言政策门外**全绿**（ortho 冻结字节
  回归 / auto 硬门 / 随机密集 / 崩溃回归 / 平面化 L1 goldens / exact /
  manual loop / ring / H2 19 图 / 新鲜度 / D0 / 内漏门全部 OK）。
- 语言政策门：命中集与 main **逐文件一致**（36 处 benchmarks/REPORT.md
  + 1 处 benchmarks/tools/gen_v082_report_section.py，全部为已提交
  main 的既有违例，双树违例集 diff 为空集新增）——**本分支零新增**；
  上游修复另立卡处理（REPORT.md 为已发布数字面，本卡不代改）。
- 内漏门禁：`scripts/check_internal_leaks.py` clean（1165 tracked files
  扫描）。
- 确定性（交付已变化的 petersen）：CLI candidate-v1 双跑 layout /
  certificate / geometry_report / loops_audit **逐字节一致**（证据
  `det/`）。
- 消融双树负例保护：auto-v2 字节 15/15、candidate-v1 交付坐标非触发图
  12/12 逐字节不变（`ablation-raw.json` 汇总）。
- 分支名说明：卡面字面分支名含内部卡号，仓 AGENTS.md 泄漏门禁禁止
  卡号进分支名（pre-push 钩子物理拦截），按其冲突规则（安全口径以仓
  文件为准）改用 `p1/m1b-ablation-fix`——同一返修线、不合并 main。

## 8. 缺陷处置清单（MAJOR-1 + 6 MINOR，逐条）

| # | 缺陷 | 处置 | 落点 |
|---|---|---|---|
| MAJOR-1 | 消融报告把 K5/K33 增益记在平面化源名下；实测交付赢家=ring-cycle:000、平面化候选 3/3 硬门淘汰、删源交付逐字节不变、真实增益=L1 短路解除 | §4.0 归因更正表按实测改写（不粉饰）；ablate_m1b.py 增删源对照列（逐源摘除重跑，边际贡献表）；构造质量修复（§1）后平面化源在 petersen 真实过门交付，重跑删源对照确认边际>0 | 本报告 §4.0/§4.1；ablate_m1b.py；candidate_planar.py；测试 `TestConstructionCaliber` |
| MINOR-1 | §4.1「其余分量不劣」不实（守卫元组字典序，spacing_cv 先胜，min_card_gap/min_clear 实测更差） | §4.1 改为诚实读法：逐分量列实测值，明写字典序语义与更差分量 | 本报告 §4.1 |
| MINOR-2 | 「删边集全枚举」实为帽内全枚举（4/55、4/45、4/60） | §1 改口径「帽内全枚举（帽 4，确定性序）」，附全枚举解总数实测 | 本报告 §1 |
| MINOR-3 | §1「全部变体构造进管线」与实测（每集 12 面构造只发 A、必要时 +B）不符 | §1 与 candidate_planar.py docstring 改为「构造层帽内 12 面构造；按 §15(3) A/B 定义只发 best A（+构造不同的 best B）；配额 2 裁决」 | 本报告 §1；candidate_planar.py |
| MINOR-4 | 12 图语料不覆盖 A/B 分化（3/3 触发图 B≡A，只在语料外成立） | 构造修复后 petersen 语料内即出现 A/B 分化（删除集 2/3 的 B 构造不同、坐标指纹不同）；新增测试 `test_dual_variant_split_covered_in_corpus` 钉住 | tests/test_candidate_planar.py；本报告 §6 |
| MINOR-5 | `mixed-chain-cycle` 实为纯 C4，族标签偏松 | 返修正构：4-环+挂链（n=6, m=6），README 表与首行注释同步 | benchmarks/corpus/longtail/longtail-mixed-chain-cycle.cld + README.md；本报告 §3 |
| MINOR-6 | 提案 3「可容忍方向」与「代理≥当前⇒跳过」剪枝矛盾（弦代理是过计数器，配该跳过条件不安全） | 提案 3 第 1 步改写：明确剪枝只在代理为下界（代理≤真值）时安全；现状代理为过计数器 → 剪枝步在下界代理+单测落地前不得实现，或改预算裁剪 | docs/proposals/m2-hotspot-3-ring-reposition.md |

复核 INFO-1/2/3（压线 clearance / 编号位移 / 语言门零新增）见 §6 与
v1 状态注记；无新增违例（本分支双树违例集 diff 为空集新增，v1 实测
结论继续成立）。
