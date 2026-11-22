# 方案稿：「锚点即先验」候选生成（锚点检索 + 边镜像对称化 + M0 门排序）

状态：**方案稿，未实现**。jacky 拍板后由实现卡承接；本文档不修改任何引擎行为。
决策输入：三轮合并最终偏好对照（36 严格决定对）的结论——BT 偏好排序范式负结果
（全臂无信号，n 不足需 150~250 对，放弃堆标注）；数据最强信号 = jacky 的 18 个手拉
锚点 86%（6/7 决定对）胜引擎候选；未训练 M0 在字节保真层 8/11 = 72.7%（方向性，
Wilson CI [43.4%, 90.2%]）。拍板方向：锚点库检索做进候选生成，M0 当质量门，不再
要人工标注。

审美硬约束（operator 2026-11-21 条目，本方案逐条承接）：
1. 对称主形态 = 左右对称（垂直中轴镜像）；
2. **连线跟着节点镜像**（e↔w、n↔n、s↔s、ne↔nw、se↔sw、分组锚 g↔g）——本方案
   将其升格为引擎一等约束（§2）；
3. 1~2 处交叉可接受，不为 0 交叉牺牲形状；
4. 对齐精度实测 ±1px。

---

## 1. 锚点检索机制

### 1.1 锚点库盘点（如实披露覆盖边界）

18 份手拉锚点 = 10 旧 + batch2 8 份，落点（数据文件，非代码）：

- `benchmarks/manual/*.json`（6 份旧：brand-flywheel / classic-cld / fan-d12 /
  fan-d17 / random-n10-i00 / random-n10-i05，含结构规律口径的 README）；
- `benchmarks/manual/user-2026-11-20/`（i05、i11-a、i11-b 共 3 份）；
- `benchmarks/manual/jacky-batch2/exports/`（8 份：nested-capacity /
  nested-learning / retest-classic-cld / coupled-underinvestment /
  comb-supply-demand / bowtie-wage-price / nonplanar-credit /
  nonplanar-inventory）；
- `benchmarks/aesthetic/pref-synthetic/candidates/epidemic-feedback-manual-layout-human.json`（1 份，随池收）。

族分布与**覆盖边界**（不画饼部分）：

| 族 | 锚点数 | 备注 |
|---|---|---|
| hub / classic-cld | 2 | 含重测对（retest-classic-cld） |
| 嵌套环 | 2 | |
| 多环耦合 | 1 | |
| 梳状 | 1 | |
| 领结 | 1 | 全边带自定义锚点设置 |
| 非平面 | 2 | |
| fan / dense（单环密辐） | 2 | d12、d17 |
| 回路类（brand-flywheel、epidemic-feedback） | 2 | |
| random n10 系 | 5 | 含两组同图重测对 |
| **链族（chain）** | **0** | jacky 判定太简单未收；评分器 hub 族权重不覆盖链型特例 |
| 三轮新拓扑（nested-ring-shared-node / chain-ring-hybrid / dual-hub-asymmetric） | **0** | 三轮 14 对全部 both-bad，池质量本身差 |
| random n>10 / n20 | 0 | 仅 n10 系有锚 |

**检索的预期失效模式（先说清楚）**：库外族一律静默降级为普通候选池——这正是三轮
新拓扑 both-bad 的根因区（池质量，非排序问题）。本方案不许这种降级静默发生：候选
provenance 必须显式记录 `anchor_hit=null, reason=family-unmatched`。检索机制救不
了「库里没有的族」，扩库（jacky 继续手拉）是唯一的根治路径，且库 = 数据文件、零
代码改动。

### 1.2 检索特征：族闸 + 族内相似度（特征单源 features.py 键，阈值/权重不写死）

**Layer 1 族闸（拓扑判别，零新特征）**：复用 candidate_sources 各 source 背后既有
的 `detect_*` 结构分析器（symmetric / bowtie-vertex / spine-wing / comb-bilateral
/ column-chain / ring-cycle / radial——与 auto-v2 模式链同一套构造核心）。输入图
先过族检测：命中族 → 进入 Layer 2；检测全 None（含链族、三轮新拓扑）→ 直接回退
（§1.4）。族判定是拓扑事实，不引入任何阈值。

**Layer 2 族内锚选（布局特征相似度）**：

1. 对输入图先跑一次确定性 baseline 布局（现行 auto 配方，行为冻结不变），用
   `stdraw/features.py` 提取特征向量——**特征键单源自 `FEATURE_KEYS`，检索器不
   自建几何口径**（与 aesthetic_score 薄层同一纪律）。
2. 候选锚点侧：每份锚点的已存 layout JSON 用同一提取器算同一向量（一次性预计算，
   随库存 `anchor-features.json`，库文件只增不改）。
3. 距离 = 选中特征键子集上的归一化距离：每键用锚点库自体的稳健尺度（IQR/中位最
   近邻距口径，与 edge-mirror 特征的自适应容差同一思路）做 z 化，**初始等权**。
   任何非等权方案必须先过 18 锚点 leave-one-out 校准并如实报告命中率，否则保持
   等权——不写死权重。
4. 命中阈值同样不写死：以「同族其余锚点 = 应命中分布」vs「negatives-library 40
   份 = 不应命中分布」的分位分隔点自动导出（类似 ε 的 P75 校准口径），随库扩充
   重算；导出值落锚点库附带文件，不进代码常量。

### 1.3 命中后：锚点几何当布局种子

命中分两种情形，种子语义不同（不混用）：

**情形 A：同图重测（拓扑同构，如 retest-classic-cld）**——锚点坐标直接可用。
落地走既有通道：`--from-layout MANUAL_JSON` 手动回放面与
`candidate_pipeline.layout(manual=...)` 已支持 manual 布局透传；锚点布局作为一个
候选进入池（新 candidate source「anchor-replay」，与 layered 兜底同地位，**携带
零评分权**——source 不 import metrics/gate 的既有静态 lint 约束不变）。

**情形 B：同族不同图（拓扑相似但节点集不同）**——锚点只能给「形状先验」，不能
给坐标。转移规则：把命中锚点预计算出的**结构规律参数**（role grouping：端点列/
中排带/翼列的相对几何；fan：单环 + 半径带 + 方位角 CV 目标；comb：列结构等——
这些规律口径在 `benchmarks/manual/README.md` 已有实测定义）作为 placement 约束
注入既有 `place_*` 构造核心，产出「anchor-seeded」候选。新 source 与模板 sources
同一接口：发射一切能完成的构造，无内部 top-k，进 orchestrator 池接受现行三 tier
selection 与 not-worse-than-auto guard——锚点候选不带特权。

**边锚点镜像传播**：命中锚点的边锚点表（golden / slot 双口径）经 §2 的 sigma
镜像映射传播到新布局的镜像边对上（e↔w、n↔n、s↔s、ne↔nw、se↔sw、g↔g）。全套
machinery（对合自同构搜索、锚点镜像表、方向对齐比较）已在边镜像研究分支实现并
经 58 图测量验证，直接复用，不重写。

### 1.4 未命中族的回退路径

- 现行 recipe × pitch ladder 候选池照旧（auto / ortho / candidate-v1 × pitch
  56/68/72/80 + arc 变体，硬 viability 门 + 去重，行为冻结）；排序走 §3 的
  M0 门（未命中候选没有锚点相似度项，不罚分）。
- provenance 显式记录未命中（见 §1.1 失效模式段），巡检/复盘可按 reason 分桶。
- 扩库是后续卡：jacky 手拉补链族/新拓扑锚点 → 库文件与预计算特征追加，检索层
  零代码改动。

---

## 2. 边镜像对称化落地（审美约束 2 升格为一等约束）

### 2.1 选路：8 候选合并清单的裁决

`docs/edge-feature-candidates.md`（边镜像研究分支）合并清单的裁决，本方案维持
并落实：

- **#1 Mirror Consistency 不进评分键**：已测，独立区分度弱（条件一致度 AUC
  0.431；presence 2x）；人工信号在 presence（有没有把主形态摆成对称），不在
  pair 一致度（引擎网格布局在结构镜像对上免费拿 1.0）。评分键维持「logged as
  data」。
- **走引擎侧**：`docs/proposals/edge-mirror-symmetry-routing.md` **Option A**——
  确定性布线对称化后处理，挂在 stage-2 末尾，M2 体量。Option B（stage-2 搜索
  内嵌对称项）提案已否（耦合独立边优化、非确定性 tie spiral 风险、买不到区分
  度），本方案维持否决。
- 清单里 #2 anchor consistency / #4 direction harmony / #8 style consistency
  进评分键的测序是另一条后续线的卡，本卡不扩键、不动评分权重。

### 2.2 镜像映射规则

沿 `docs/edge-mirror-feature.md` 的已验证定义：

- sigma = 无向图**对合自同构** + y 保持 + **拟合轴**（轴从候选拟合，不强制画布
  中轴——nonplanar-inventory 实测构图轴 686 vs 画布 1184 的教训）；主镜像 = 拟
  合轴最靠近画布中轴者（tie-break：轴散差更紧 → 镜像对更多 → 枚举序）；
- 容差自适应：`tol = 0.5 × 中位最近邻节点距`（不用画布对角线比例——同侧堆叠误
  配成镜像对的实测坑）；
- 锚点镜像 **golden / slot 双子口径并行** + 逐端点三态（equal/mismatch/unknown，
  缺数据=不可评估、不静默 pass）；镜像边常反向存储 → 先按 sigma 方向对齐再逐端
  点比；分组锚 g↔g 由 golden/slot 表给出；
- 对称化执行：每对取 canonical 较小端点 id 一侧为 master，另一侧重算为 master
  的精确镜像（镜像锚点 id、同 route kind、polyline x 镜像）；
- **有效性门复跑**：镜像路线重过 box-over-line 硬门 + clearance 检查；违门则该
  对保留原路线并记 exception 日志——**绝不把过门布局改成挂门布局**；exception
  进 certificate/routing log，fail-loud。

### 2.3 ±1px 对齐：实现与测量

- 实现：镜像 = 对已算路线的纯几何复制（`x' = 2c − x`），无搜索、无求解器、字节
  确定性；stage-1 placement 不碰，交叉/行质量指标构造性不变（审美约束 3 的
  「1~2 处交叉可接受」由 placement 保持现状天然满足，不为 0 交叉牺牲形状）。
- 测量口径：`edge_mirror` + `symmetry_axis_err_px` + `alignment_coverage_tight`
  （±1px tight 口径）——全部是 `FEATURE_KEYS` 既有键，单源 features.py。验收：
  开旗后 mirror-bearing 布局的主镜像 pair 锚点一致度 = 1.0（可评估子集）、
  ±1px 对齐达标率 = 100%（可评估子集），并给出逐图清单。
- 存量期望基准：18 锚点回归中 mirror-bearing 图（comb / bowtie / fan-d12 /
  fan-d17 / nonplanar-inventory 等，锚点本体实测一致度 0.5~1.0 见测量报告）——
  引擎候选的镜像一致度不得低于锚点本体实测值。

### 2.4 开关与 pin 影响（如实）

- **默认 OFF，`--mirror-symmetry` 显式 opt-in**：现有 byte-pinned 消费方（8777
  STDRAW_PIN、frozen baselines、gate A 字节回归）在旗关闭时构造性零漂移。
- 开旗发版走完整流程：A 档 61 图全量重渲 + 漂移逐字节登记（无镜像对的图位级
  不变；classic 语料网格布局的偶然镜像对会漂移，须列入发版说明）；pin 升级与
  引擎发版对齐。无镜像对图的位级不变性有构造性证明 + 测试钉。

---

## 3. 候选排序主信号：M0 质量门 + 锚点相似度（替换 BT 排序）

### 3.1 排序设计

```
viability 硬门（现行，不动）
  → M0 质量门：committed v2 pointwise 模型（model-v2.json）打分，
    阈值 = 跨会话噪声门 66.7% 对应的 ε 校准（M0 ε P75 = 58.6，18 both-good 对
    P75 口径，已有实测值）；低于门的候选降级/淘汰
  → 锚点相似度排序：仅在锚点命中的检索语境里生效——候选对命中锚点的特征距离
    越小排越前；不可评估（未命中/缺键）= 不参与本层排序，**记为不可评估而非
    0 分**（三态纪律，同 edge-mirror 逐端点口径）
  → 同分 tie-break：M0 分数高者先
```

边界（防走偏）：

- **锚点相似度不进 v3 评分键**——那是 8 候选清单已否决的路（镜像先例：光靠条件
  化救不了 consistency 类特征）。它只在「有命中锚点」的排序语境作信号。
- M0 门阈值沿用**成对/相对口径**（ε 是 v2 分数差，跨图不可比），不新造绝对阈值、
  不动评分与证书 grade 分离。
- BT 训练线退役：不再新增标注轮次，pref-* 实验脚本与其 JSON/MD 产物保留为历史
  证据，不再作为排序依据。

### 3.2 替换前后离线 A/B（现有三轮候选，零新增标注）

数据面：`benchmarks/aesthetic/pref-synthetic/candidates/`（三轮全部候选，含
*-human 锚点候选）+ 三份 selection JSON + 62 对既有标注（仅作评测集，不再训练）。

- **旧序**：BT 臂排序（pref-ranking 数字已在案：M1 6/36、M2 8/36、M2s 11/36，
  全臂无信号）。
- **新序**：§3.1 管线离线重放（纯本地计算，零 API 成本）。
- **比较指标（全部机械可算）**：
  1. 锚点识别子集（9 问锚点 vs 引擎，有 jacky 答案）：新序下锚点候选排第一的
     比例 vs 现值 M0 4/9——这是唯一直接连到 jacky 偏好的可验证子集；n=9 只作
     方向性读数（CI 纪律同 72.7% 段）。
  2. 池顶候选（每图 top-1）的锚点相似度分布：新旧序对比（命中族子集）。
  3. 池多样性：去重后池大小与 recipe 覆盖不得塌缩（防止 M0 门把池砍没）。
  4. 门控成本：每图被 M0 门淘汰的候选数、未命中比例（family-unmatched 桶）。
- **判读纪律**：29 对 both-bad 是池质量问题，排序救不了，如实报告；三轮新拓扑
  0 决定对 → 其上任何排序改进都不可测，不许声明。

### 3.3 实施切分（供拍板后拆卡参考）

| 阶段 | 内容 | 体量 | 可独立回滚 |
|---|---|---|---|
| S1 | 锚点检索 + anchor-replay/anchor-seeded 两个 source（§1） | 中（新模块 + 预计算脚本） | 是（source 不注册即回退） |
| S2 | 镜像对称化后处理，`--mirror-symmetry` 默认 OFF（§2） | 小-中（模块 + 旗 + sweep） | 是（旗关闭 = 零影响） |
| S3 | 排序管线替换 + 离线 A/B 报告（§3） | 小（选层逻辑 + 评测脚本） | 是（排序层独立） |

---

## 4. 回归保护

- **负例字节保护**：negatives 语料 .gitattributes 字节钉死 + 聚合 sha 期望测试
  不动；本方案零接触负例语料。
- **18 锚点回归**：`tests/test_manual_anchors.py`、
  `test_layout_modes.py::TestSpineWingManualEquivalence`、
  `test_radial_manual_calibration.py` 等全部从锚点文件自导期望（仓内无坐标副本
  纪律）——锚点候选源不改这些测试的期望推导路径；锚点库文件只增不改（改 = 破
  坏重测对基线）。新增回归：anchor-replay 命中图的回放候选与锚点本体字节关系、
  镜像旗 ON 时的 mirror-bearing 期望清单。
- **ci 门**：pytest 全绿（现基线 377）+ ci_checks 绿 + gate A 61 图逐字节（旗
  OFF 构造性零漂移；旗 ON 发版单走全量重渲 + 登记，§2.4）。
- **快慢门纪律**：实现卡各轮只跑快门（确定性 + 净化 + 受影响单测，≤2min）；
  全量 sweep + 全测只在收口前跑一次。

---

## 5. 风险与不做什么

**不做**：

- 不动评分器权重与证书 grade 分离（aesthetic 分数不进 certificate grade）；
- 不动 auto / ortho / candidate-v1 现行行为与冻结基线（ortho-v1 冻结不动；
  anchor-seeded 是新增 source，不是改 template 行为）；
- 不动 negatives 语料、AGENTS.md、publishing face（README/demos/docs/gallery）；
  镜像旗开启若触发 demos 重渲，属实现卡收口时按 freshness 门单走 publishing-face
  acceptance；
- 不扩 v3 评分键（8 候选清单 #2/#4/#8 的测序是后续独立卡）；
- 不新增任何人工标注；不跑 n30/n50（引擎硬范围 n≤20 不变）；
- 纯本地计算，零 API/外部服务成本。

**风险（如实）**：

| 风险 | 缓解 |
|---|---|
| 库外族静默降级（0 锚点拓扑） | provenance 显式记 `anchor_hit=null` + reason 分桶；报告里单列 |
| 18 份库小、族内常仅 1~2 锚 → 检索过拟合 | 排序信号只在可评估子集生效；LOGO 校准披露命中率；阈值/权重随库重算，不写死 |
| M0 门 ε 是分数差量纲，跨图不可比 | 沿用成对/相对口径，不造绝对阈值 |
| 镜像旗开启后 classic 语料偶然镜像对字节漂移 | 默认 OFF；开旗发版全量重渲 + 漂移登记清单 + 消费方重 pin |
| 锚点种子候选被误当「特权候选」 | source 零评分权纪律不变（静态 import lint 测试继续生效） |

**本方案不承诺的事**：三轮新拓扑（0 锚点）的候选质量提升；链族的任何检索命中；
M0 门把偏好排序问题变没问题（72.7% 只是方向性读数）。
