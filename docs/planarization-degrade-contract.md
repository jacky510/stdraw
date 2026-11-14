# 非平面图 planarization 降级契约（P3 triage 设计稿）

> **状态：DRAFT — 契约设计，未经 jacky 批准不得实现。** 本文档由 P3 triage
> （2026-11-14）产出；实现另开卡。维护中文，与 `docs/crossing-exact.md`
> （oracle 数学框架）、`docs/grading-contract.md`（等级语义单一来源）、
> `docs/layout-modes.md`（引擎分工）互为指针，不复制其内容。

## 0. 事实核实（卡面前提修正，全部实测于 59881c0 工作树）

卡面背景有三处与仓内实测不符，契约按实测事实设计：

| 卡面前提 | 实测 | 证据（回读命令） |
|---|---|---|
| 「planar.py 遇非平面输入硬失败」 | **仅 ortho recipe**（`--recipe ortho`，CI-only 冻结基线）。CLI 捕获 `NotPlanarError` 后诚实跳过 2D 证书，**exit 0 不是 1** | `python -m stdraw layout benchmarks/corpus/random/random-n10-i09.cld --outdir <d> --recipe ortho --skip-3d` → stdout `[3/6] 2D planar layer inapplicable … honest degradation`，exit=0 |
| 「random n10 非平面样本 exit 1 变 exit 0」 | **部分成立但机制不同**。n10-i09：今日已 exit=0（crossings=1 ≤ 2），auto-v2 无平面性要求（`stdraw/layout_auto.py` 头注 "No planarity requirement"）；n20-i00：**exit=1**，但根因是 crossings=30 > 2 触发几何门，不是 NotPlanarError | n10-i09 / n20-i00 `--recipe auto` 实测（§6 快照） |
| 「从只能画平面图到任何 CLD 都能画」 | auto-v2 早已能画任何 CLD；**非平面图的 grade 永远 uncertified**（`visual_crossings_zero` 硬门 + `best` 要求 0 交叉，`stdraw/metrics.py` v2 评分段） | `grep -n "visual_crossings_zero" stdraw/metrics.py` |

corpus 非平面盘点（networkx `is_planar` 全量扫描，m=1.6n 均匀随机图）：
n10 4/20（i09/i10/i16/i19）、n20 20/20、n30 20/20、n50 20/20 —— **n≥20 全体非平面**。

**价值重述**：planarization 不会把非平面图画成 0 交叉（cr(G)>0 是数学事实）。
它买到的是两件事：

1. **交叉从偶然变成被见证**——今日 auto-v2 的交叉是路由几何的偶然产物，与
   cr(G) 无对照关系；planarized 管线的每个交叉落在 planarization 见证点上，
   交叉数可与 `crossing_exact` 的 UB/LB 对照（复用既有 `--exact` 块）。
2. **非平面图首次可出证书**——三账一致（几何复点 == witness 数 == oracle UB）
   时给 `crossed-certified` 等级（§4），替代今日的永远 uncertified。

## 1. 降级契约：三级阶梯

| 级 | 触发条件 | 行为 | exit | grade |
|---|---|---|---|---|
| **L0** | core（去度 0/1 后）平面 | 今日 auto-v2 引擎链原样，planarization 层**不进入**（零漂移由构造保证） | 0 | 今日语义不变 |
| **L1** | core 非平面 ∧ 启发式 planarization 成功 ∧ 交叉数 c ≤ CAP ∧ 步数 ≤ BUDGET | planarized-RT 管线（§2）→ 交叉 marker 渲染（§3）→ 证书 `crossed-certified`（§4） | 0 | `crossed-certified`（硬门全过时） |
| **L2** | L1 准入失败（超 CAP / 超 BUDGET / oracle 验 H 不平面——理论不应发生，发生即 bug） | **回退今日 auto-v2 通用路径**（不是硬错误），证书新增诚实降级记录 | 0 | `uncertified`（与今日一致） |

- **NotPlanarError 语义保持不动**：它继续只活在 ortho 层内部（`stdraw/planar.py`），
  ortho 冻结基线字节级不碰。auto 链的降级面是 L2 回退，**不引入新的硬错误路径**。
- **L2 诚实记录**（仿 `anchors_standard_deferred` 既有模式）：证书
  `gates.planarization_deferred = {reason: [...], measured: c_ub 或 "budget-exceeded"}`；
  gate 值保持实测（不伪造通过），reason 必须可度量。
- **准入判定源**：core 非平面用 `nx.check_planarity`（与 `build_rotation` 同源）；
  L1 的 H 平面性用 `crossing_exact._planarized_graph` 构造后 `nx.check_planarity`
  复验（oracle 语义与 `docs/crossing-exact.md` 定理 C 一致）。

**决策点 D1（数值，jacky 拍板）**：
- `CAP`（L1 准入交叉数上限）：**推荐 min(3n, 80)**。依据：n20 全量 c 预计个位数
  （见 §6 实测），n50 密度 1.6 下 cr 预计数十，CAP 挡住的是回退而不是质量。
- `BUDGET`：**禁止 wall-clock**（破坏字节级回归），用**确定性操作预算**：F 边逐条
  插入步数 ≤ 2000、H 顶点数 ≤ 600（超出即 L2）。数值进实现卡前跑 corpus 校准。

## 2. 管线（Tamassia）与既有复用点

```
core 非平面
  → U 选择        复用 crossing_exact._heuristic_planarization（固定 sorted(min,max,i) 序，贪心保平面）
  → 嵌入 Π        复用 crossing_exact._embed_U
  → F 逐条插入    复用 crossing_exact._greedy_insert_ub（路径内交点按序剖边插虚拟点）
  → H 构造+验平   复用 crossing_exact._planarized_graph + nx.check_planarity（oracle）
  → RT 布局       新模块 stdraw/planarized_layout.py：在 H 上跑可见性表示
                  （数学复用 planar.py 的旋转系/st-编号/可见性构造，但不改 ortho 冻结文件——
                  提取共用内核或新写，实现卡定，取「ortho 字节零漂移」为硬约束）
  → 回映射        虚拟点 → 交叉 marker（语义 §3）；真实边还原为被剖分的折线
  → 既有下游      anchors/硬门/证书/渲染链不变，新增三账核对（§4）
```

- H 口径 = `docs/crossing-exact.md` §0 good drawing：相邻边不交叉、任意两边至多
  交叉一次、无三边共点；平行边不相交（各自独立计入）。
- 虚拟点度恒为 4（两条边一个交点）；一条边被交叉 k 次 → k 个串联虚拟点。
- 布局跑在 **H** 上（H 平面性已由 oracle 保证，`build_rotation` 前置必过）。

## 3. 交叉点视觉标注（语义契约；视觉常量归 UIDesignerBot）

**现状核实**：画布上**不存在**任何路由交叉标记——今日交叉只有 metrics 计数、
certificate `crossing_details` 坐标、交互 JS 实时计数（`stdraw/_interactive_js.py`）。
本契约引入的是**首个画布交叉标记**，因此「与现有路由交叉标记视觉口径统一」的
卡面问法不成立；统一口径的对象是**未来两种来源**：

| 来源 | 语义 | 出现位置 |
|---|---|---|
| planarization witness（本契约新增） | H 的虚拟点回映射，L1 输出 | 交点处 marker |
| 路由偶然交叉（今日已有，无标记） | L0/L2 输出的几何交叉 | 无 marker（维持现状） |

语义契约（本契约钉死，实现卡执行）：

1. **一个几何交点恰一个 marker**；marker 不改变 crossings 计数口径
   （计数仍由几何复点独立算出，marker 仅是见证的视觉呈现）。
   D2 定稿措辞微调（字段不减）：**逐点渲染为默认态；密集簇折叠为
   聚合视觉形态**——簇内（中心距 ≤10px）≤2 个逐点独立渲染（允许
   视觉重叠）、≥3 个折叠为 Ø10px 聚合徽标「×N」；折叠仅发生在呈现
   层，markers[] 数据一条不缺、witness 数与 crossings 计数口径不变。
2. marker 携带数据：`{edges: [A, B], witness_id, planarization: {ub, lb, gap}}`。
3. hover 文本契约：`A × B · witness #k · cr UB=c (LB=l, gap=g)`；具体文案措辞实现卡定。
4. 符号/尺寸/颜色/ hover 样式 = **决策点 D2，UIDesignerBot 拍板**（守项目
   DESIGN.md；本卡不代拍视觉常量）。建议方向：与节点卡视觉权重明显更低的
   小型 × 符号（8–10px 级），不与 16-anchor 锚点系统冲突。

## 4. 证书措辞与 check 门

1. **crossings 指标口径不变**：仍是交付坐标上的几何复点计数。
2. **三账核对**（证书签发前提，仿既有 dual-accounting 拒发模式）：
   `几何复点数 == planarization witness 数 == oracle UB`，三方一致才可签
   `crossed-certified`；不一致 → `uncertified` 并记录 mismatch。
   oracle UB 复用 `--exact` 的 `crossing_exact()` 块（`certificate_auto(exactness=…)`
   通道已存在）；L1 路径要求 exactness 必带（**决策点 D4**：是否顺带把 L1 的
   `--exact` 变为默认，成本 = CP-SAT 求解时间，corpus 实测后定）。
3. **「crossings ≤ 2」门在 L1 下替换**（实测依据见 §6：n20-i00 今日 crossings=30
   → exit 1）。L1 输出的硬门不再是绝对数值 ≤2，而是 `crossings_witnessed`
   （数目 == UB 且逐点有 witness）。理由：certified 交叉数由 cr(G) 决定，是
   图的数学属性不是布局缺陷；门的对象从「交叉少」改为「每个交叉都被证明
   必要且被标记」。L0/L2 下 ≤2 口径不变。`ci_checks` B2 的
   `m["crossings"] > 2 → fail` 断言按模式分支（实现卡列改动点）。
4. **grade token**（决策点 D3）：`best` 语义不动（0 交叉专属，避免既有 CI 断言
   `crossings==0 ∧ grade==best` 语义漂移）；新增 token **`crossed-certified`**：
   v2 硬门全过 + 三账一致。`second` 不得复用（v1-legacy only，
   `docs/grading-contract.md` 已钉死）。落地时 `grading-contract.md` 同步 +
   `scripts/check_docs_consistency.py` 用户面同步，列入实现卡交付清单。
5. **HTML 措辞**：L1 输出的 demo-2d.html 标题/注脚不再出现
   "0 crossings guaranteed by theorem"（该句是 RT 平面定理表述，对 L1 为假），
   分支改写为 "crossings = cr UB, witness-marked (planarized)"；L0 输出措辞逐字节不变。
6. **check 门适配**：
   - `visual_crossings_zero` 硬门在 L1 模式下由 **`crossings_witnessed`** 替位
     （每个几何交叉都能映射到 witness 且数目一致）；L0/L2 下语义与今日完全一致。
   - gate 集继续自描述（先读 `caliber` 再解释 `grade`/gate，grading-contract 既有纪律）。
   - `geometry_report` / `ci_checks` 中对 `crossings_zero` 的断言按模式分支
     （实现卡列明改动点清单）。

## 5. 确定性契约（字节级回归硬门）

| 环节 | 确定性来源 | 现状 |
|---|---|---|
| U 选择 | `_heuristic_planarization` 固定 `sorted(min,max,i)` 边序贪心 | 已有 ✓ |
| F 插入序 | 同一 canonical 序；路径内交点按路径序剖边 | 已有 ✓ |
| H 上 (s,t) 枚举 | 现有边序双循环 + `seen_st` 去重 | 已有 ✓ |
| 候选平局 | `(score, discovery index)` 稳定序 | 已有 ✓ |
| ILP（如 D4 默认开） | `num_workers=1, random_seed=42` | 已有 ✓ |
| 预算 | **操作计数，禁 wall-clock / 随机 / 线程**（§1 D1） | 本契约新增 |

回归形态：新增 L1 golden 图（至少 n10-i09 一张 + 一张 n20），双跑 `layout.json` /
`demo-2d.html` / `certificate.json` 逐字节一致断言进 `ci_checks`（沿用既有
ref-scrubbed 字节清单模式）。

## 6. 验收门（按实测改写）

卡面「exit 1 → exit 0」不成立（§0：今日已 exit 0），验收增量改写为
**grade 与证书**维度：

| 输入组 | 今日 | 本契约后 | 门 |
|---|---|---|---|
| random-n10 i09/i10/i16/i19（4 图） | exit 0, uncertified, 交叉数无对照 | exit 0, `crossed-certified`, 三账一致 | B2-P 新门组 |
| random-n20-i00（triage 快照，余 19 图实现卡补测） | **exit 1**（crossings=30 > 2 几何门失败）, uncertified | exit 0, `crossed-certified`, crossings==UB（cr 预计 ≪30），`crossings_witnessed` 替位 ≤2 门 | B2-P |
| random-n30 ×20 | triage 快照 n30-i00：**exit 1**（crossings=75 > 2 几何门失败）；余 19 图实现卡补测 | L1（CAP 内）或诚实 L2 | B2-P（实现卡开工前补测定档） |
| random-n50 ×20 | exit 0, uncertified | 大概率 L2（超 CAP），断言诚实降级记录存在 | L2 诚实门 |
| B2 既有 4 张 planar n10 | 过 | **零漂移**（L0 恒不触发，构造保证） | 既有字节基线不动 |
| ortho 冻结基线（含非平面跳过路径） | exit 0 skip | **0 触碰** | 既有 gate A 基线不动 |

B2-P 新门组断言（每图 ×2 跑）：exit 0 + 硬门全过 + 三账一致 + 双跑字节一致 +
`grade ∈ {crossed-certified, uncertified}` 且 uncertified 必带
`planarization_deferred.reason`。

> n20/n30 的 cr UB 与耗时实测：triage 时后台在跑（本节表格数字以实现卡开工前
> 的复测为准；triage 实测快照见本卡交接 metadata）。triage 快照补测：n20-i00
> 的 `_greedy_insert_ub` 纯贪心插入返回 (None, None)（贪心步骤失败，oracle 层需
> 走 oil-insertion/CP-SAT 通道）——这支持 **D4 推荐项**（L1 默认带 `--exact`，
> 否则部分图连诚实 UB 都拿不到）。

## 7. 决策点汇总（jacky 拍板项）

| # | 问题 | 推荐 | 备选 |
|---|---|---|---|
| D1 | CAP / BUDGET 数值 | CAP=min(3n,80)；BUDGET=插入步数 2000 / H 顶点 600 | corpus 校准后调 |
| D2 | 交叉 marker 视觉常量（符号/尺寸/色/hover） | 8–10px × 符号，UIDesignerBot 定稿 | — |
| D3 | grade token 名 | `crossed-certified` | `best-crossed` / 其他 |
| D4 | L1 是否默认带 `--exact`（oracle UB 参与三账） | 默认带（证书完整性优先）；若 n30/n50 求解时间不可接受再改为可关 | 仅显式 `--exact` 时三账，否则只对 witness 双账 |

## 8. 明确不做（本契约边界）

- 不改 `stdraw/planar.py` / ortho 冻结基线 / `crossing_exact.py` 数学（只消费）。
- 不碰 AGENTS.md 等受保护文件。
- RT 内核从 ortho 冻结文件复用的方式（提取 vs 新写）= 实现卡的技术决策，
  唯一硬约束是 ortho 产物字节零漂移。
- 视觉常量不代拍（D2 归 UIDesignerBot）。

## 9. 范围拍板附录（jacky 2026-11-14，planarization 实现卡执行）

1. **能力上限 = n≤20**：stdraw 本体只服务 n≤20 的 CLD（实际消费场景 6–10 节点，
   n20 已留一倍余量）。n30 能力移交 **stdraw20 线**（z.code 承接）；本文 §6 表中
   random-n30/n50 行的验收项**作废**，已跑数据仅作参考。
2. **D4 退路触发**：范围钉死 n20 后，超预算条件实测成立（random-n20-i00 单次
   layout 静机 838.1s vs 改动前 122.5s / 原 300s 预算——L1 准入尝试即 oil nogood
   阶梯的结构性成本）。按已批退路执行：`--exact` 改**可关**（`--no-exact`，默认
   仍开保证书完整性；关闭后 L1 保留 witness 标注图但诚实 `uncertified`）；
   900s/次的诚实降级上限保留（test_scalability 墙钟门据此从 300s 调至 900s）。
3. 验收口径相应收窄：n10 非平面 4 图 crossed-certified + n20 全 20 张（L1 或
   诚实 L2）+ L0 平面 corpus 零漂移为准。
