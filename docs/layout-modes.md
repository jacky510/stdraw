# 布局模式与美学口径（v0.7.1）

> Engineering doc, maintained in Chinese — English edition (self-contained):
> [layout-modes.en.md](layout-modes.en.md)

> jacky 2026-11-05 全图审查定调（最高优先设计原则）：
> 「如果方框排布能有规律，那么就尽量形成规律，比如纵向对齐一列，比如圆形回路。
> 线尽量配合方框的排布来画。规律让图形更好看，也更好理解。」
> 「所有的回路应该尽量把回路上的方框跟环路的开头靠近，形成一种圆环的感觉。」
> 「部分线相交可以接受，因为排布有规律、秩序和优美更加重要。」

## 模式选择（确定性图论度量，优先级从高到低）

| 优先级 | 模式 | 触发判定 | meta.placement |
|---|---|---|---|
| 1 | 领结对对称（共边） | 核心图恰为两个三角形共享一条边（4 节点 5 边，度序列 {3,3,2,2}，度-3 节点相邻） | `symmetric` |
| 1 | 领结共点对称（美学 v3） | 枚举简单环（长度 ≥3，规范形去重）恰 2 个、两环恰共享 1 个节点、两环并集=全部非孤立节点（与共边领结拓扑互斥：5 节点 6 边） | `bowtie-vertex` |
| 2 | 纵柱+翼位（v0.7.1） | 中枢对（公共邻居 3≤W≤4 的有向边，平局：声明环共现多→规范形小）+ rest 次级簇非空可配对 + 主链长度占比 ≤0.5（详见下节） | `spine-wing` |
| 2 | 双侧梳状（v0.7.7，宽卡 v0.7.8） | 恰两个非相邻 hub，邻居集相同且等于公共源集 S（|S|=m≥3）；其余核心节点为挂在源上的森林（每棵恰含一个源）；comb 源列长 > column 最优 spine 长才抢占纵列；ring ratio 分支在 best k≤4 且 detect_comb 命中时拒绝进入（详见下节） | `comb-bilateral` |
| 3 | 纵列（长链/少环） | 3≤n≤12 ∧ 最长简单回路 3≤k≤4 ∧ k<n（主环小 → 主链感强；k=n 的大环归环形；环形 pure-cycle/ratio 触发者不进纵列） | `column-chain` |
| 4 | 环形 | 纯环 / 主环覆盖 ≥n-2 / 环边占比 ≥0.9 ∧ k≥5 或覆盖全图 | `ring-cycle` |
| 5 | 分层（既有路径） | 其余（链/树/大图等） | `layered` |

每个新模式带**试验闸门**：构造排布后跑同一布线器复核硬门代理（交叉≤2、
压线=0、净距≥16、锚点平滑、互环分离、卡距≥16），任一不过**静默回退**
下一优先级——回退路径输出与不触发的图完全一致（负例逐字节不变）。

### 模式决策链留痕（mode_decision_trace，ref-scrubbed）

上面的确定性优先级链可审计：每次自动布局在 `meta`（layout.json）与证书
（certificate.json，同名字段）记录 `mode_decision_trace`：

- `rules`——按求值顺序逐条记录：规则名、优先级、是否命中、**命中/不命中
  的结构性依据（带实测数字）**、试验闸门结果（pass / fail / 不适用）；
  被更高优先级抢占的规则如实记「detected, but not adopted / trial not run」。
- `fallback`——是否走了分层兜底及原因。
- `legacy_band_exemption`——v0.7.2 基线带外遗留的登记豁免：增强式中带
  重锚与互指直线重布线通道仅 spine-wing 启用，其余引擎按 CI
  `BASELINE_BAND` 锁表保留登记基线带内比例；该豁免逐图披露，不再静默。
- 手动布局（--from-layout）不进链：`manual: true`、`rules: []`——布线
  硬门照常复核，如实评分。

评审报告（2026-11-09）第 5 条「触发决策日志」建议的落地：降低触发式模板
黑盒感，证书读者可直接看到「哪条规则命中、为何命中、豁免是否触发」。

### 纵列模式（column-chain）

- **主链（spine）选择**：候选 = 声明环 ∪ 图论枚举回路，按「环长最大 →
  负边数最少（全正增长回路优先当主链）→ WL 结构色签名 → 声明优先 →
  规范形」确定性选优；起点 = 结构最显著节点（WL 色 → 度），方向 = 有向边
  跟随数多者。
- **排布**：主链节点沿中央纵列对齐一列（x=列轴，y=top+i·pitch）；
  支路（残节点）挂主链近邻侧（右列优先，整组放置不拆组）；孤立节点停
  顶部停车带。
- **主链闭合边**（last→first）：构造为**左侧大弧**（二次贝塞尔；控制点按
  「t=0.5 鼓出=|ctrl−弦中点|/2」解算到最左障碍外 clear+4px，逐框验证用
  check3 同口径的 step=4 加密采样——稀疏采样会漏检端部高曲率的弦切效应）。
- **主链跨行弦边**（|行差|≥2）：构造为**右侧大弧**（与闭合弧对侧）；
  不可行（多弦互撞等）回退 Router 候选池。
- 证书规律性门：主链列轴偏差 ≤2px + 主链行距恒等（支路半行/整行偏移
  不计入行距门）；行对齐率/列吸附对纵列不适用（如实 null）。

### 纵柱+翼位（spine-wing，v0.7.1）

> jacky 亲手拉了 classic-cld-growth-and-burden（增长极限×转嫁负担）手动布局：
> 中央纵柱 adopters(顶)/rate(底) 严格垂直压画布中心线（x 差 1px）；左翼
> word/potential 与右簇 crowding 压同一水平中线（y 完全相等）；右上
> quickfix / 右下 sideeffect 近镜像（x 差 6px）；fundamental 右下内侧与
> rate 同行。本模式把该「纵柱+中线翼位」审美基准写死为确定性规则
> （正本 `stdraw/spinewinglayout.py`）。

- **触发判定**（确定性拓扑度量，全部满足才触发）：
  1. **中枢对（spine）**：公共邻居数 W 满足 3≤W≤4 的有向边（平局：声明环
     共现数多者 → 规范形 (u,v) 小者）。经典 CLD 的「rate→adopters」型扩散
     中枢对天然胜出（classic-cld W=3，其余语料最高 2）；
  2. **翼位（wings）**=中枢对公共邻居（各与中枢对构成一条 3-环），**rest
     次级簇**（除 spine∪wings 外的核心节点）非空且 ≤6、全部邻接 ⊆
     spine∪wings∪rest（无外挂——双轴可构性；limits-to-growth 同构 spine
     但 rest=0，属纯增长核不触发）；
  3. **主链长度占比** = |spine 节点| / |核心节点| ≤ 0.5（紧凑中枢对；
     长链形态归 column-chain）；
  4. **rest 可配对**（镜像可构性）：优先配「共享声明环」的 rest 对
     （样本 quickfix/sideeffect 同属 R2），其余按限制邻域键配对，落单 ≤1。
  - 优先级链位次：bowtie-vertex → **spine-wing** → column → ring-cycle
    （本节表格）；**纯简单环仍走 ring-cycle 零漂移**（纯环族 W≤1 天然
    不命中）。
  - 19 图语料 sweep 实测（v0.7.1）：仅 classic-cld-growth-and-burden 命中；
    bowtie 三张 W=1、共边领结两张与纵列族 W≤2、纯环族 W≤1 全部不命中；
    其余 18 张 layout.json 相对 base 7378016 逐字节零漂移。
- **排布**（构造约束——对拍样本相对几何，**非全局目标函数项**）：
  - 纵柱：中枢对沿布局轴 x=0 严格垂直，head 上 y=−Hs、tail 下 y=+Hs，
    Hs=2·(card_h+GAP)=160（样本纵柱半距 160）；head/target 在上是
    「原因向上生长」的样本方向；
  - 中线翼位：翼位全压 y=0 水平带。**rest 簇锚翼**（对 rest 邻接最多者，
    样本=crowding）放右侧最近位；其余翼按（回路 kind R<B<其他 → 规范形）
    排序放左侧、由内到外（样本：word 内 / potential 外）；
  - rest 镜像对：共享声明环对同列上下镜像 ±(card_h+GAP)=±80（样本 ±82 的
    理想化，误差 0px）；落单者右下内侧 y=+160（与 tail 同带，样本
    fundamental y=532 vs rate 534）；全部坐标取偶（2px 网格）。
- **布线**：纵柱边构造竖直直线（顶卡底边中点 → 底卡顶边中点，构造式注入
  不走候选池）；其余边走同一 Router 候选池（直线/弧线一等；互环对
  crowding↔quickfix / crowding↔fundamental 走 Router 互环走廊 ≥4px 分离）。
- **试验闸门**：复用 `_constructed_gates`（压线/净距/锚点/卡距/互环分离/
  交叉≤2），不过静默回退，负例逐字节不变。
- **证书规律门（等价门）**：对纵柱+翼位形态，ring 的「CV≤0.05 / 模板拟合
  ≤0.05」等价口径为——**纵柱 x 对齐 ≤2px + 翼位中线贴靠 ≤2px + 镜像对
  误差 ≤2px**（classic-cld 实测三者全 0px；交叉为软目标报告项；确定性由
  CLI 双跑逐字节一致承载）。本步只对 classic-cld 一张切口径，其余 ring 图
  零漂移可回归验证。
- 同构一致性：与 limits-to-growth 共享 {rate, adopters, word, potential,
  crowding} 子骨架但 rest=0 不触发——「增长核 vs 增长+负担全图」由 rest
  判据天然区分。

### 双侧梳状（comb-bilateral，v0.7.7；宽卡两档 fan v0.7.8）

> ground truth = jacky 手拉的 HDD 供应链图（K_{5,2}+pendant）：源点单列
> 严格同轴、双 hub 镜像槽位（列中行）、全部 hub 边直线扇形、列内边垂直。

- **几何**：源+pendant 单列（x 同轴偏差 0）、hub_y 取列中行、双 hub 关于
  列轴镜像（中心镜像误差 0）；hub_dx 下限 = max(200, (列内最宽卡+hub 卡)/2
  + 16 + 110)。
- **两档 fan 实现（v0.7.8）**：
  - **tier-0（窄卡，v0.7.7 语义不变）**：hub 边走布线器候选池
    border_point 锚点，hub 半跨 24px 步进加宽括号（≤16 步）找可行窗。
  - **tier-1（宽卡，8777 双 ticker 级）**：宽卡（hw≫hh）时中心射线几乎
    总从上/下边出锚，近水平扇线在水平边上的出射角恒 <20°，而加宽只会更
    平——净距要宽与锚角要窄互斥，tier-0 窗恒空。此时 hub 边改为**贴面
    竖边锚点构造直线**：中心连线在两卡贴面竖边的截点（带内钳制
    ±(hh−3)，2px 网格），hub 侧锚点按源行序固定槽序做 1D 展开
    （≥FAN_SEP_MIN=8px，防堆叠且保序=扇线两两不交的充要条件），线整体
    活在列带两侧的空走廊内（净距结构性成立，近水平线⊥竖边≈90° 出射
    角）；走 constructed 注入通道交付（kind=line，冻结于
    coincide/midband/fan_spread），试验闸门对全边集复跑统一硬门；
    meta.comb.fan="facing-border" 标记。两档都耗尽才抛 InfeasibleComb
    静默回退分层。
- **门集（metrics/check/ci_checks 三处同口径）**：column_axis ≤2px +
  column_pitch 恒定 + hub 中心镜像 ≤2px + hub_edges_straight + 通用硬门；
  CV 为结构性报告项不作门。

### 领结共点对称（bowtie-vertex，美学 v3）

> jacky 亲手拉了 wage-price-spiral 手动布局：共享节点居画布正中心、两环其余
> 节点放四对称位，全图上下左右轴对称——v0.6.0 引擎误判成 column-chain，
> 「拓扑该决定布局」。本模式把该审美基准写死为确定性规则。

- **触发判定**：枚举无向简单环（长度 ≥3，规范形去重）——**不用声明
  loops**（声明表混 2 节点伪环、漏派生环：#11 声明 2 实 3、#18 声明 3 实 6）；
  恰 2 个环 ∧ 两环节点集恰共享 1 个节点 ∧ 两环并集 = 全部非孤立节点
  （存在环外悬挂节点时保守不触发）。语料命中：{eroding-goals,
  shifting-the-burden, wage-price-spiral}。**不误伤**：08/10/17 虽也只有
  2 个简单环，但共享 2 个节点（共边型），判据天然排除。
- **排布**：共享节点居画布中心（布局层轴 x=y=0）；两环各占一个半平面
  （第一环上/第二环下，环序按 kind R<B<其他 → canon 序）；环上其余节点
  放同半平面水平行左右镜像位（同 D、同 H → 全图严格镜像，镜像轴误差
  门 ≤2px，实测 0px）。左右指派 = 从共享节点沿「有向边跟随」方向遍历环，
  后继放左、次后放右（对拍样本：wages 左/cost 右、real_income 左/demand 右）。
- **布线**：构造式注入全直线（线型一致性：外边水平直线 + 辐条直连）。
  语料 4 条辐条全为互环对（双向边）——单线构造两方向逐点重合，故互环
  走廊按 ±12px 平行双线（共享侧边中点 ±t 展开、卡端锚沿所属框边切向
  展开，横边按「相交则换位」配对防翻越交叉）；共享节点同侧双辐条在边
  中点两侧对称展开（不堆叠在同一点）。
- **证书规律门**：镜像轴误差 ≤2px（共享节点居轴心 + 镜像对 x 相等 +
  y 对水平轴对称）。
- 同构一致性：{eroding-goals, shifting-the-burden, wage-price-spiral}
  有向同构 → 同一布局模板。

### 领结对对称（symmetric）

- 共享边端点 A（上行）/B（下行）居纵轴；两顶点左（−D）/右（+D）中行
  镜像——显式几何对称（#11 learning-flywheel「可对称却偏左」的修复）。
- **线型一致性硬规则**：轴边直线 + 4 条侧边全部构造为镜像弧（同一对称
  结构内不直/弧/折混杂）；试验闸门额外拒绝任何 vg/poly 折线。
- 证书规律性门：镜像轴误差 ≤2px（顶点 x 对轴等距 + y 同行）。
- 同构一致性：{learning-flywheel, fixes-that-fail} 有向同构 → 同一模板。

### 同构骨架 → 同布局模板

结构相同的图应产出结构相同的布局（读者把同构教科书模型认成「同一张图」）。
机制：主链选择与槽位指派用 **WL 结构色签名**（2 轮 refine，不依赖声明环
id 顺序）驱动；同构图的对应节点同色 → 对应槽位。已验证语料同构组：
- {eroding-goals, shifting-the-burden, wage-price-spiral}（有向同构，全进
  领结共点 bowtie-vertex，自美学 v3 起）；
- {fixes-that-fail, learning-flywheel}（有向同构，全进领结对对称）；
- {bullwhip, tragedy-of-the-commons}（无向同构，全进纵列同构模板）。
自反对称位（automorphic 节点）的平局按 id 序打破——几何上等价（镜像）。

## 边极性双色着色规则（jacky 2026-11-09 定调，替代回路着色方案）

- **数据**：`layout.json` 每条边仍带 `loop_kinds`（所属声明回路的 kind 列表）
  与 `loop_color`（引擎数据层不变，渲染层不再消费 `loop_color`）；
  `certificate.json` / `loops_audit.json` 的极性数据不变。
- **着色（确定性规则）**：线只按**边自身极性**两色——**+ 边=朱红 `#c2410c`、
  − 边=制图蓝 `#1e6fae`**（UI-A 浅色档；深色档 `#ffb454`/`#6ec6ff`；唯一出处
  `stdraw/themes.py`），**全部实线**；
  - 共享边（同属 R/B 两环）按该边自身 +/- 极性着色——**环归属不再用颜色
    表达**；
  - 灰色 shared-edge 专色、虚线=负号、loop-id 药丸等一切超出两色的视觉编码
    均已取消（极简优先，jacky 2026-11-09 拍板「信息过载」）。
- **图例压到最小**：两色块 +「+」/「−」即可（2D 在证书面板下方一行；
  3D 右下角固定小图例；是否完全去图例由 jacky 过目两版小样后拍板）。
- 交互层（拖拽）同口径：着色为静态 stroke 属性，拖拽重布线时保留。

## 线型层级：弧线 > 直线 > 折线

- 候选评估加固定类型代价：`vg`（绕障折角）+120、`poly`（车道折线）+40、
  `wrap`（外围绕行）+200——直线/弧线可行时折线不再抢分，**折线=最后手段**。
- 对称结构内线型一致（对称模式构造式保证：轴边直线 + 侧边全弧）。
- 纵列主链闭合边/跨行弦边构造为大弧（不进折线候选池）。

## 线-框连接点口径（2026-11-06 收紧）

> 「整体要看起来协调，线连在方框上的点也优先选每条边的中点，
> 尽量不要选转角的地方。」

- **锚点口径（`routing.border_point`，Python/JS 双侧同源）**：射线定边
  （与旧口径同边）→ 锚点沿该边切向**钳制到边中点 ±1/4 边长带内**——
  正交方向出边即边中点，斜线出口拉回带内；**转角整体排除**（不作候选、
  不作兜底，命中数恒 0）。交互层（拖拽实时跟随）同口径。
- **构造弧映射**：对称弧先按自然锚点定型，ctrl 经弦坐标变换（α 弦比例
  + β 垂偏）映射到钳制后锚点——弧相对形状/出发切向保持。
- **不堆叠硬规则**：同节点同侧 ≥2 个锚点时，Router.fan_spread 按入射角
  排序、沿框边切向在中点两侧对称展开（步距 18px，钳制在边内）；展开后
  逐边复核硬门（压线/净距/锚角/交叉数不增/互环分离），违例整节点回退。
  互环走廊（bowtie 辐条）锚点 ±12px 平行双线，同侧双辐条 ±7px 收窄。
- **验收口径**：corpus 全语料锚点带内比例（±1/4 边长）、转角命中数（=0）、
  精确中点比例，改前改后统计入证书报告。
- **CI 锚点硬门（v0.7.3 二验返修）**：转角命中数 = 0（全引擎）；
  带内比例逐图 ≥ v0.7.2 基线（tests/ci_checks.py `BASELINE_BAND` 锁表），
  其中 spine-wing（本口径域）须 **100% 带内**。基线带外遗留：ring-cycle
  互环对（brand-flywheel 87.5% / fishing-collapse 83.3%）、bowtie-vertex
  ±12px 辐条走廊（62.5%–66.7%）——修复牵动交付 dx 平移与 18 图零漂移
  硬门，归后续卡。
- **交付层三段式钳制（`Router.midband_reanchor(enhanced=)`）**：
  档 0 基线口径（v0.7.2 原语义：端点钳制、ctrl 不动，成功即交付——其余
  18 图逐字节一致的保证）→ 档 1 增强阶梯（仅 spine-wing 启用）：① 弧线
  ctrl 随动平移 + 贝塞尔重散（弧线出发切向保持）；② 沿框边向边中点阶梯
  步进（4px/档，≤半带封顶）；③ 门集加**自家框内部检查**（`_edge_stats`
  只计他框 press，ctrl 随动后切向可下扎自家框，classic-cld 实测坑）→
  兜底「互环对带内局部重定线」（`_reroute_pair_band`）：带内锚候选
  （`_band_candidates`：变体钳带后按新弦重算 line/arc + 双侧别嵌套弧逃生
  门 + 天然带内走廊族）贪心两遍选优，硬门与交付同口径。
  **构造弧映射勘误**：v0.7.2 的「ctrl 经弦坐标变换映射」只覆盖构造弧；
  路由弧的出发点未经钳制（jacky 二验打回根因：classic-cld 症状解虚线
  出发点距角 3px，带内区间 [635.5,708.5] 实测带外）——本版起交付层三段
  式钳制覆盖一切路由弧。

## 弧线弧度参数化（美学 v3）

- **自适应弯曲系数 `routing.adaptive_arc_k(弦长)`**：鼓出
  = min(6 + 0.06·弦长, 40) px，k = 2·鼓出/弦长 ∈ [0.12, 0.50]——短边小弯、
  长边大弯封顶（典型弦 130px → k≈0.21，衔接 v0.6.0 观感）。
- **候选弧首档**即自适应档（ARC_KS 梯保留作可行性兜底，dedupe 保序）。
- **同环弧度一致**：对称结构构造弧（symmetric 侧弧）统一取 4 条侧弦长
  median 档——同一结构内弧度一致、视觉均匀；纵列闭合弧/弦弧仍按净距
  目标解算（几何必要性优先）。
- JS 拖拽弧线平移跟随交付 ctrl（arcFollow），与 Python 同口径。

## 交叉口径：软目标 + 如实报告（v0.6.0 起）

- `crossings_zero` 从**硬门降为报告项**（`certificate.reports.crossings_zero`）：
  排布规律达标时允许 ≤2 交叉（秩序与优美优先）。
- `row_align_ge_060` 同降报告项（14 张手动样本 row_align delta≈0，用户
  不在乎；排布规律由「行距恒等 + 列吸附 / 模式口径」承载）。
- **分级语义不变**：最优 = 硬门全过 + 0 交叉；其次 = 硬门全过 + ≤2 交叉
  （明细入证书供复核）；未获证书 = 其余。排布规律类（压线/净距/锚点/
  模式规律门）仍为硬门。

## 呼吸感（间距目标）

- 14 张手动样本实测：min_card_gap 平均 +35.8px（最大 +73）→ **卡间净距
  目标 36px**（`layout_auto.GAP_TARGET`）：纵列/对称排布按 36px 放置
  （SIDE_GAP/SYM_GAP）；分层路径 polish 目标函数加 `8×max(0, 36−最小卡距)`
  软惩罚（不设硬门，挤了由既有 ≥16 门兜底）。
- 证书新增报告指标：`loop_cohesion_spread`（每声明回路的节点跨度/全图
  对角线，越小越聚拢）、`center_offset_x`（居中偏移）、`line_kind_counts`
  （线型分布）。

## 证书模式口径（metrics/check 三处同口径）

| 模式 | 规律性门 |
|---|---|
| ring-cycle | 环上等间距 CV ≤0.05 + 正多边形模板拟合 ≤0.05 |
| spine-wing | 纵柱 x 对齐 ≤2px + 翼位中线贴靠 ≤2px + 镜像对误差 ≤2px |
| column-chain | 主链列轴偏差 ≤2px + 主链行距恒等 |
| symmetric | 镜像轴误差 ≤2px |
| bowtie-vertex | 镜像轴误差 ≤2px（共享节点居轴心 + 上下环镜像） |
| layered | 行距恒等 + 24px 列吸附 ≥60%（简单图） |

## 方框标准锚点集（16 点，ref-scrubbed；ref-scrubbed 起为**缺省吸附口径**）

- **口径**：每框 16 个离散标准连接点 = 4 边中点 + 4 角点 + 每边 2 个黄金
  分割点（0.382/0.618）= 16 点对称口径（jacky 2026-11-08 口述「边中点 4 +
  角 4 + 黄金分割点」的对称化落卡；单边 1 个黄金点破坏对称，不采用）。
- **内缩**：全部 16 点落在边框**内缩 3px** 的矩形上（复用 fan 槽位的
  `half − 3` 内缩口径，`stdraw/anchors.py:ANCHOR_INSET`）；角点永远不在
  几何角尖上（渲染圆角 rx=7 之外），黄金点方向按顺时针固定
  （g1 = 0.382，g2 = 0.618；顶边左→右、右边上→下、底边右→左、左边下→上）。
- **正本**：`stdraw/anchors.py`（纯函数库）；交互层
  `_interactive_js.stdAnchors` 镜像同一公式（live 卡片几何），probe 逐点
  对拍 JS vs Python（≤0.02px）。ref-scrubbed 当时只落交互层（「静态管线
  不 import → sweep byte-identical」约束）；**ref-scrubbed（jacky 2026-11-09
  「连接点还不是我定过的 16 个标准连接点」）起该口径升级为缺省吸附口径**，
  交付层新增 `Router.anchor_snap`（见下节），静态管线自此 import 本库。
- **视觉去噪（ref-scrubbed）**：缺省渲染（2D 静态 PNG / demo HTML 初始态 /
  3D）**不显示锚点圆点与端点把手圆圈**；交互层锚点圆点 hover 才显示且
  **缺省关闭**（工具栏开关保留，probe hook `__stdrawSetAnchorToggle`）；
  端点把手圆圈缺省隐藏，边 hover 或端点拖拽中才淡入（`.stdraw-ep.vis`）。
- **交互语义**：hover 方框显示 16 锚点（工具栏可关）；边端点（起点+箭头
  端）可单独拖动，松手吸附到**端点所属框**的最近标准锚点（并列取
  ANCHOR_IDS 序靠前者）；点击可见锚点 = 显式指派（最近落点端点胜出）。
- **user-anchored 重投影**：显式指派（拖拽吸附/点击/`__stdrawApplyLayout`
  `edge_anchors`）后，节点拖动只把端点**重投影到同一锚位**（按 live 几何
  重算坐标），不漂移；导出 layout 的 `edges[].anchors {src,dst}` 随
  Export layout 语义走（viewer 回放恢复；T1 起 CLI `--from-layout` 亦消费
  该键，见下条）。
- **CLI 读回（T1，2026-11-11）**：`--from-layout` 读回 `edges[].anchors`：指定端
  直接落到对应标准锚点坐标（±0.1px 交付），该边加入冻结集合
  （与手动 waypoints 的 G4 冻结同族；`anchor_snap` tier-1/tier-2、lens
  joint 系列按端豁免，路由 dict 带 `ua_ends` 标记）；直线/弧线/折点三种
  route kind 都遵守指定，弧 ctrl 按端点位移均值平移（viewer `arcEpPts`
  口径）；校验与 `_manual_waypoints` 镜像（边必须在图中、锚点 id ∈
  `ANCHOR_IDS`，否则 exit 2）；证书 `from_layout.user_anchors` 如实记录
  锚点来源（auto vs user）。auto 路径字节不变。回归：
  `tests/test_manual_anchors.py`。
- **手动布局硬门回退（T2，2026-11-12）**：用户样式/锚定的边（waypoint 自由
  拖拽边除外）在注入完成后按交付几何**逐边复核硬门**——自盒/他盒压线
  （1px 膨胀口径，端点 6px 附着区豁免，与几何检查 2 同账）、边-框净距
  （<16px）、mutual 对双向均被用户锚定时的双线分离（<4px，与检查 12 同
  账）。违例边**整条回退到引擎自有路由**（注入前快照），由路由器的
  mutual-pair lens 弧偏移 / 压线回避 / 净距候选机制交付过门几何；mutual
  对原子回退（任一方向违例即整对回退，避免半对共点）。过门的用户样式
  一字不动——良性手动布局字节零漂移；回退在 `from_layout.manual_fallback`
  逐边如实记录（边 + 违例原因），CLI 同步打印回退清单。auto 路径字节
  不变。回归：`tests/test_manual_fallback_gates.py`（经典「富者愈富」
  fixture：手拖位置 + 3 条用户边，2 条违例回退、1 条过门保留，
  fail=0 / crossings 0 / 双跑逐字节一致）。

## 交付层默认吸附 16 标准锚点集（ref-scrubbed，`Router.anchor_snap`）

jacky 2026-11-09：「连接点还不是我之前定过的 16 个标准连接点」——16 锚点集
从交互层口径升级为**缺省吸附口径**：auto 配方每一引擎（含构造/waypoint 冻结
边）交付前，所有边端点（起点+箭头端）必须落在端点所属方框的 16 标准锚点
之一；证书新增 `anchors_standard` 硬门（成员判定 tol 0.75px，进 grade 合取）。

- **算法路径（门径最近锚分配，非布线后硬吸附）**：① 占用登记——已在锚上的
  端点按 (框, 锚) 占用（同锚不共点，杜绝 V 形共点）；② 逐边（确定性序）
  每端点按**距离最近优先**（并列取 ANCHOR_IDS 序）枚举 16 锚候选，候选仅当
  全套交付硬门成立才落锚：press 不增 / 对任何他边**零新增交叉** / 净距
  （CI raw 口径 ≥16，即 router 膨胀口径 ≥15）/ 出发角 ≥20°（router 与
  **证书双侧分类口径都**须过——角锚点两侧分类可不一致，population-logistic
  nw 实测 router 50.2° vs 证书 0.0°）/ 互环分离 ≥4px / 自家框弧身侵入不增
  （贴附区 6px 内采样豁免，与 metrics/check 同源同口径）。③ 扫描循环至
  不动点（≤4 轮）：先落锚的边更新共享几何，后处理的边对着**已吸附状态**
  复核——顺序联合求解，移动方自己的门已计入其移动造成的交叉。
- **路由器形状联动**：直线端点直移；弧线端点落锚 + ctrl 随端点位移平移后
  按 `ARC_CTRL_SCALE_LADDER`（1.0→0.45/1.6）绕新弦中点缩放重定形（保绕行
  侧，门径复检）——长切向大弧（bullwhip 东绕弧）靠此档满足离切角硬门；
  vg 折线端点+相邻折点同向量平移（首段共线、出发方向保持）+ 对应圆角刚移
  + 按 corners+fillets 重稠密化；poly/wrap 同折点平移；waypoints 只移端点
  （不动用户折点）。
- **与既有口径的关系**：±1/4 带内比（ref-scrubbed/ref-scrubbed 的中点偏好
  代理门）被本口径**有据取代**——ci_checks `BASELINE_BAND` 锁表与
  test_layout_modes 带内比例锁改为 16 锚成员硬门，带内比降为报告项
  （吸附后实测：classic-cld 18/26、brand-flywheel 8/16、urban-migration
  8/16、limits-to-growth 9/14 等，classic 语料转角锚命中恒 0）；fan_spread /
  midband_reanchor / mutual 通道照旧（先跑，anchor_snap 收尾兜底）。
- **验证（21 图 sweep，吸附前 vs 后逐图字节对比见卡）**：21/21 crossings 0、
  grade best、visual_crossings_zero True、anchors_standard True、端点成员
  违例 0；确定性两次运行字节一致（ci_checks 层 B）。

### 密度阈值探针模式（ref-scrubbed 收口，jacky 2026-11-09 拍板通过）

random dense 抽样实测：n10-i05（E/N=1.60）吸附后三门连挂——visual_crossings
2→4（2 fan 对+2 普通对）、1 端点无锚可落（N03→N08 poly）、line-line
coincidence。而 classic 正本 classic-cld（E/N=13/8=1.62）吸附 21 图全绿，
失败样例最大度（4）反而低于 classic-cld（7）——**任何静态标量密度阈值都无法
既放行 classic-cld 又拦住 random n10**。故口径落地为：

- **阈值**：`ANCHOR_SNAP_DENSE_E_OVER_N = 1.6`（E/N ≥ 1.6，即平均度 ≥ 3.2）进入
  **探针模式+整体延后记账**（端点无锚也算回归，回退同时证书记录 deferred）；
  低于阈值同样走**退化撤回探针**（ref-scrubbed T5 卡，Copilot 复核发现的静默
  变差漏洞）：吸附后复算交叉对数与 line-line coincidence，任一变差即回退——
  但**端点无锚既不触发回退也不触发 deferred 记账**（低密度图的诚实无锚端点
  仍由 `anchors_standard` 门如实计数，stderr 打印失败清单）。
- **探针**：在工作副本上执行完整吸附，然后复算三硬门（普通交叉对数
  `final_crossing_pairs` / line-line coincidence 对数 / 端点锚成员——任一
  端点无锚即失败）；**零回归才保留吸附结果，任一回归整体回退到吸附前路由**
  （保留不变式：dense 图要么全端点落锚，要么完全回退，不存在半吸附态）。
- **诚实降级**：回退时证书记录 `gates.anchors_standard_deferred =
  {density_en, reason[], moved_before_revert}`，`anchors_standard` 门**保持
  实测值 False**（不放水、不改 grade 语义——dense 降级图 grade 如实变为
  uncertified/second，jacky 拍板的正是这条降级路径）；布局 meta 恒带
  `anchor_snap_deferred`（null=已吸附）。回退路由不再跑吸附后的
  `mutual_arrival_flip(enhanced_gates=True)`（吸附前翻转已跑过，避免扰动
  诚实的吸附前状态）。
- **ci_checks 断言（B2 随机层）**：E/N≥1.6 的图必须「成员门 True（探针保留）
  或带非空 reason 的 deferred 记录」二选一；E/N<1.6 的图不允许出现 deferred
  （低密度图没有降级豁免）；任何 deferred 必须带实测 reason。
- **已知局限（后续卡专项）**：fan 对视觉交叉增量暂未进探针回归判据（实测
  n10-i05 由「端点无锚」触发回退已覆盖；fan-only 回归未观测到）——dense 吸
  附门径专项优化卡（coincidence 门+链式交叉溯源）承接。
### 互环透镜联合重指派（ref-scrubbed，恢复 <=10° 到达角目标）

吸附的镜像 golden 对锚点量化会让部分互环透镜对的弦倾角存在硬下限：
classic-cld crowding<->fundamental 两框中心错位 24px，量化锚偏移
（crowding ±10.6px / fundamental ±16.5px）使镜像对的弦 dx 只能取
24±5.9px，最坏弦倾角 atan(29.9/122) ≈ 13.8°。到达角 <=10°（两端同达）
要求锚点水平错位 |Δx| <= tan(10°)·H（H=弦竖向跨度，本对 ≈122px →
21.4px）——镜像锚弦的 29.9px 超出该锥形约束，ctrl 全域枚举下限
~11.5°、交付 14.4°，目标在该锚指派下数学不可达（ref-scrubbed 如实降级
15° 的依据）。

**解法 = 扩展锚指派空间而非调 ctrl**：允许两弧各自取「非镜像」的
朝向边锚组合（每框有向锚对枚举，他边已占锚排除），逐组合重定形
（lockstep ctrl 平移 + ARC_CTRL_SCALE_LADDER 缩放）并复检全套交付门
（press/交叉/净距/锚角/自家框/共端点兄弟交叉/带内/互环分离 >=12px），
再模拟吸附后 `mutual_arrival_flip(enhanced_gates=True)` 得四端到达角。
`Router.lens_joint_reassign` 只在两处 gate 下触发：pair 由联合吸附
镜像指派过、且模拟 flip 后仍 >`ARRIVAL_TARGET_DEG`；**枚举最优组合
四端全部 <=10° 才应用**（达不到目标的边际改善一律拒绝——soil-erosion
crop_yield<->farming 实测枚举最优 21.69° vs 交付 21.82°，正确保持
原字节）。应用后由调用方的 flip 精确复现模拟终态（本通道只落
flip 前的梯门几何）。

- **classic-cld 实测**：胜出指派 = arc1（crowding→fundamental）取
  (s-g2 +10.6px → n 0px)、arc2（fundamental→crowding）取 (n-g1 −16.5px →
  s-g1 −10.6px)，两弦倾角 6.27°/8.44°，四端到达角 2.8°/6.8°/0.9°/8.9°
  （max 8.93°），互环分离 16.5px，14 checks fail=0、grade best、
  全硬门绿——<=10° 目标恢复（test_mutual_lens_arrow_normal 断言回归
  ARRIVAL_TARGET_DEG，15° 锚点口径上限退役）。
- **字节影响**：21 图 classic sweep 仅 classic-cld 一图漂移
  （layout/certificate/demo-2d，随引擎重渲，demos/ 新鲜度门同步）；
  其余 20 图逐字节零漂移（触发条件构造性排除：flip 已达标的 pair
  在模拟阶段即跳过）。

### dense 吸附门径强化（ref-scrubbed B 项，`Router._snap_joint_detour` + coincidence 门）

探针「任一回归整体回退」的口径下，本卡把 dense 图的吸附**做真**——回归越少，
探针保留吸附的比例越高：

- **coincidence 门**：每个吸附候选 acceptance 新增 `_coincide_no_worse`——候选
  边对他边的最大贴合跨度（`_coincide_max_span`，与证书 line_line_coincident
  同源同口径，bbox 预筛）不得从 <8px（COINCIDE_SPAN）变成 ≥8px（禁止**制造**
  重合对）；已在违例状态的边要求单调不恶化。classic 域零重合基线不受影响
  （候选若会制造重合，21 图 sweep 早已出现违例——字节零漂移实测）。
- **joint-detour tier（tier-2）**：tier-1 全 16 锚被拒的端点，整边按可见图重排
  ——`_vis.plan_route` 从「起点锚×终点锚」标准锚**对**出发（两端各自最近优先
  阶梯 × 两档膨胀 cl+VG_PAD / +PAIR_VG_OFF 车道分离），两端点由构造**保证**
  落在 16 锚集上。互指对与用户 waypoints 边不进 tier-2（镜像对称/用户折点由
  专属通道保持）。验收=与 sweep 同一套全套硬门 + 端点成员 + coincidence 门。
- **端点方向律**：tier-2 输出必须 `points[0]∈a 锚、points[-1]∈b 锚`（边方向序）
  ——check.py 门 4 在 pts[0] 对框 a 量出发角，反向路线会把两端双双判成
  off-border（random-n10-i00 N03→N08 实测教训）。
- **实测效果（B1+B2 后、探针保留吸附路径）**：n10-i05 visual_crossings 4→1、
  astd 1→0、coincidence 1→0；n10-i00 astd 2→0（off-border 双端清零）。classic
  21 图 tier-2 零触发，逐字节零漂移。全量 random 语料探针保留/回退比例见卡
  报告；阈值上限是否上调/取消由 jacky 依数据拍板。

### 互指透镜到达角：放置联合优化探索归档（ref-scrubbed D 项，与 ref-scrubbed 互补）

ref-scrubbed（`Router.lens_joint_reassign`）以**非镜像**锚指派恢复了 ≤10° 目标
（classic-cld 四端 max 8.93°，见上节）。本卡在其落地前完成了放置+路由联合
优化探索（离线工具 `benchmarks/tools/lens_placement_experiment.py`，不复跑），
数据与该解法互补：

- **镜像配对内的不可行性（已证，后被 lens_joint_reassign 精确突破）**：
  镜像 golden 对的弦 dx 只能取 24±5.9px → 最坏倾角 13.8°（= ref-scrubbed 文档
  中的锥形约束推导）；ctrl-only flip 下限 14.4°。
- **放置对齐枚举（±24/±48/±72px × 两框，生产通道链口径）**：12 候选全部被
  硬门拒——对齐位到达角可到 ~2-4° 但透镜分离跌到 4.5px（<12px SEP_FLOOR）；
  +48 位出 2 fan 交叉+1 出发角违例；fundamental -24/-48 卡距跌到 11/0px。
  ⇒「到达角 ≤10° + 分离 ≥12px + 16 锚口径」三角在**镜像配对+既有放置**下
  不可满足——正是 lens_joint_reassign 放弃镜像约束的依据。
- **共享锚受控放宽**：两弧共锚 ⇒ 贴附区分离 0px，撞 mutual_pairs_separated
  （≥4px）与透镜禁并线规则——不可采纳（与 ref-scrubbed 的「带内+分离 ≥12px」
  门共同证实分离约束不可松）。
- 生产管线不引入放置移位通道（枚举从不采纳、纯耗时）；工具与数据留档。
