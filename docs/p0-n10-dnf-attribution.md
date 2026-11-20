# n10 族 5/20 DNF 回归归因（布线尾部 vs 口径变化）

归因报告 · 手写（非生成）· 基线 main@5da2257 · 分支 `p0/n10-dnf-attribution`
证据目录：`benchmarks/raw/v082/`（v082 sweep 原始数据）+ 卡片工作区 `rerun/`（本卡复跑 stderr 捕获，副本落 `kanban/evidence/`）

## 1. 结论（先行）

**口径变化为主、叠加一处新功能的可修成本热点——不是既有链路的复杂度回归。**

- 触发 350s 墙钟预算的 5 张图（i08/i11/i13/i15/i18）在 v0.8.2 现引擎上**全部走了 2026-11-06 历史 sweep 时还不存在的 ring-construct 模式链**（历史引擎无 mode-detection/ring-construct/`_ring_reposition`，全部图走 layered+CP-SAT+polish）。
- 难点图的墙钟几乎全部（97.8–99.3%）落在 **ring 回位邻域扫描**（`_ring_reposition`，6f9d2b6 = 2026-11-13 引入）：每个降级候选 × 11 档旋转各跑一次**完整 delivery 链探针**（route_all + 全修复链 + anchor_snap 回归复核）；失败路径 = 1 初始探针 + 9 候选 × 11 旋转 = **100 次探针**（i08 实测计数：`_delivery_chain_probe` 100 次 / 378.4s，占墙钟 87%；place_ring 本身仅 0.3s）。
- 因此：「历史 0% DNF → 现 5/20 DNF」的主因是**新引擎把同一批图引上了一条新的、带组合爆炸式探针的模式链**（口径变化），探针本身的每次成本没有劣化（route_all 单次 ~1–3s 量级正常）；但这条新链在最坏情况下烧 ~100 次全链探针 ≈ 250–660s，属于**新功能的可修复杂度热点**（修法方案见 §6，不动手）。
- i08 在本卡 quieter 复跑下 291–292s **能完成**（< 350s 预算）——DNF 与 ok 之间是墙钟预算边缘，REPORT §10.3 的 ±2× 方差声明直接适用。

## 2. 问题与口径

- Phase 0-1 v082 sweep（2026-11-20，run_v082_auto.py，350s/graph 外部墙钟预算）：random-n10 族 5/20 DNF（i08/i11/i13/i15/i18，auto.json 记 status=dnf，无 stderr 计时捕获——计时表只在进程正常结束时打印）。
- 历史 WS4/WS5 口径（2026-11-06 01:38，benchmarks/raw/ 顶层，提交 d53e0e5，引擎态 = 其父 63f5962）：n10 族 20/20 ok，0% DNF（REPORT §4）。
- 本卡归因方法：①图同源核对；②历史引擎独立 worktree（63f5962, detached）复跑同 5 图；③现引擎加长预算（1200s）+ STDRAW_TIMING=1 复跑拿阶段表；④进程内计数探针（monkeypatch 计数包装，不改仓内字节）定位函数级热点。

## 3. 图同源核对

v082 与历史 raw 的 random-n10 全部 20 图 **n=10, m=16 完全一致**（corpus 未变；DNF 行 auto.json 的 n/m 为 null 是 DNF 记录格式，非图不同）。⇒ 两轮差异只能来自引擎/口径，不能来自语料。

## 4. 历史侧证据（引擎代际 + 同图复跑）

### 4.1 引擎代际（git 证据）

| 提交 | 时间 | 内容 | 与本题关系 |
|---|---|---|---|
| d53e0e5 | 2026-11-06 01:38:40 | WS5 benchmarks: full rerun（历史 raw 落盘提交） | 历史 raw 的提交 |
| 63f5962 | 2026-11-06 01:19:36 | d53e0e5 的父 = 历史 sweep 实际引擎态 | 该树 `grep STDRAW_TIMING layout_auto.py` = 0 处（无计时层）；`grep "_ring_trial\|ring-construct"` = 0 处（**无模式链引擎**），仅 `_polish` layered 路径 |
| a46687d | 2026-11-11 10:38 | edge placement rules v1（er 锚点预分配 + 多轮 alternate presets + legacy 双路对拍） | layered 路径 route_final 段的新口径（本次 DNF 图不走此段） |
| 6f9d2b6 | 2026-11-13 22:27 | single-node zero-crossing neighborhood reposition (ring-cycle)——引入 `_ring_reposition` + `_delivery_chain_probe` | **本次 DNF 的成本本体；历史 sweep 时不存在** |

### 4.2 历史引擎复跑同 5 图（63f5962 worktree，本卡实测）

同机、同预算口径（350s），全部 ok：

| 图 | 历史 raw runtime_s (2026-11-06) | 本卡复跑 wall_s (63f5962) | 现 v082 |
|---|---|---|---|
| random-n10-i08 | 58.752 | 72.0 | **DNF (>350s)** |
| random-n10-i11 | 46.700 | 66.8 | **DNF (>350s)** |
| random-n10-i13 | 69.698 | 85.7 | **DNF (>350s)** |
| random-n10-i15 | 42.914 | 58.1 | **DNF (>350s)** |
| random-n10-i18 | 47.541 | 48.7 | **DNF (>350s)** |

同一台机器、同一批图：旧引擎 48–86s 全过，新引擎 >350s 全 DNF。差异不在机器负载，在引擎走的模式链。

## 5. 现引擎逐图阶段级归因（本卡复跑，1200s 加长预算，STDRAW_TIMING=1）

全部 5 图复跑完成（rc=0），阶段表如下（`ring_reposition` 标记只在扫描**采纳**候选时打；扫描失败时该段成本不落标记、计入 `route_final` 桶——见 §5.2 计时口径缺口）：

| 图 | 复跑 wall | 主导段 | 占比 | 判定 |
|---|---|---|---|---|
| i08 | 292.5s | route_final（=无标记的 reposition 扫描失败段） | 99.3% (289.4s) | 扫描无合格候选，100 次探针全烧 |
| i11 | 675.1s | **ring_reposition**（有标记） | 97.8% (659.4s) | 扫描到后期才采纳候选；标记打在采纳时 |
| i13 | 234.1s | route_final（同 i08 形态） | 98.6% (230.3s) | 扫描失败 |
| i15 | 298.3s | route_final（同 i08 形态） | 99.1% (295.1s) | 扫描失败 |
| i18 | 204.9s | route_final（同 i08 形态） | 99.1% (202.4s) | 扫描失败 |
| （旁证）i17 | v082 ok 272.9s | route_final | 99.1% (270.3s) | 同一热点上的 ok 边缘图 |

预算边缘注：本轮复跑在中等负载下进行，5 图全部完成（204.9–675.1s）；其中 4 图 <350s（v082 sweep 时它们 >350s DNF）——DNF/ok 分界正是 ±2× 墙钟方差带内的预算边缘现象（REPORT §10.3 方差声明适用）。

stderr 原始捕获：本卡工作区 `rerun/random-n10-i*.stderr.txt`（副本落 evidence 目录）。

### 5.1 函数级热点定位（进程内计数探针，i08）

monkeypatch 计数包装（不改仓内任何字节），进程内跑 auto-v2：

| 包装函数 | 调用次数 | 累计 |
|---|---|---|
| `_delivery_chain_probe` | **100** | **378.4s（87% 墙钟）** |
| `Router.route_all` | 103 | 94.4s |
| `Router.coincide_reroute` | 101 | 34.8s |
| `ringlayout.place_ring` | 100 | 0.3s |

100 = 1 初始探针 + 9 降级候选 × 11 档旋转（REPOSITION_ROT_DEG = ±0/8/16/24/32/40），与代码路径逐项吻合。每次探针 = Router 构造 + route_all + coincide/midband/fan/arrival_flip + anchor_snap + 回归复核 ≈ 2.5–3.8s（密集弦几何）。i11 的 675s = 同机制 + 采纳前的更多候选×旋转组合被实际扫完。

### 5.2 计时口径缺口（v082 timing-summary 误读风险）

`route_final` 桶在 ring-construct 图上**不是布线本身**：ring 路径在 `mode_detection_trials` 标记之后没有任何标记（ring_reposition 标记仅在采纳时打），因此「ring 构造 + 回位扫描 + 最终 route_all」整段无标记成本全部记进 route_final。推论：

- REPORT §10.3 聚合表里 route_final 41.2% 中，ring 图的份额是「回位扫描失败段」，不是 route_all 本身；
- REPORT §10.4 现有归因句「the gated-reorder path's wall on the slowest graphs now exceeds 350s」**与证据不符**——慢图/DMF 图全在 ring-construct 路径（阶段表里根本没有 polish_gated_reorder 段）；layered+polish 图（i00–i07/i12/i14）全部 16–53s 远离预算。已在本分支 REPORT §10.4 补注更正（见 §7）。

## 6. 回归 vs 口径变化——判定与根因假设

**判定：口径变化（新引擎模式链），叠加新功能的可修成本热点。**

1. 不是旧链路劣化：旧引擎树上根本没有这条链（§4.1）；同图旧引擎 48–86s（§4.2）。
2. 新链的每一步单价正常（route_all 单次 ~1–3s；place_ring 0.3s/百次），爆炸来自**组合**：无合格候选时全候选×全旋转×全链探针，最坏 ~100 次 ≈ 250–660s，恰跨 350s 预算线。
3. 机器负载敏感性：i08 本次 291–292s 完成（v082 sweep 时 >350s）——±2× 方差带内，DNF 判定是预算边缘现象。
4. 质量侧收益真实存在（i11 扫描后采纳了零交叉候选、交付质量提升），所以这不是「纯浪费」，是「深度换时间」的新口径——但最坏情况的代价没有被预算管理。

## 7. 修法方案（方案卡，不动手；等拍板）

| # | 方案 | 改动面 | 预期效果 | 风险 |
|---|---|---|---|---|
| A | **chord 代理预筛**：先以纯几何 `_crossing_count`（已在候选排序里用）预筛，只对 chord_crossings 更小的前 k 个候选跑全链探针（k=3~5），其余跳过 | `_ring_reposition` 局部 | 最坏 100→~46–56 次探针（≈-50%）；失败路径有界 | 采纳率可能下降（跳过的候选可能合格）——需 sweep 验证交付质量零漂移 |
| B | **旋转阶梯早停**：失败路径上同一候选的前 2–3 档旋转探针全失败后跳过剩余旋转（旋转只影响碰撞地形，连续失败是强信号） | `_ring_reposition` 循环控制 | 失败路径 100→~28 次探针（≈-72%） | 可能漏掉深旋转档的合格候选；同样需字节级 sweep 验证 |
| C | **探针预算上限**：`_ring_reposition` 带确定性探针计数上限（如 40 次），超限放弃扫描（维持现有「不采纳则字节不动」语义） | `_ring_reposition` 签名+循环 | 失败路径上界固定 ≈ 40×~3s ≈ 120s，n10 全族回到预算内 | 上限内没扫到的合格候选丢失；确定性保持（计数是确定性口径） |
| D | **计时标记补齐**（正交、低风险，建议与 A/B/C 任一并行）：扫描开始/结束打 `ring_reposition_scan` 标记，失败路径不再污染 route_final 桶 | `_timing.mark` 两处 | timing 聚合恢复诚实；不改变任何交付字节 | 无（纯计时层，REPORT §9 已证计时层零漂移） |

推荐组合：**D 先行（零风险）+ C（上界治理）**；A/B 需要全量字节零漂移 sweep 佐证后再议。落地时遵守：i11 这类「扫描后采纳」图的交付字节必须零漂移或如实登记（byte-pinned 消费方纪律）。

## 8. 证据清单与复跑命令

- v082 sweep 原始数据：`benchmarks/raw/v082/`（timing-summary.json / timing/*.txt / DNF auto.json）
- 本卡复跑捕获（现引擎 5 图 + 计数探针 JSON + 老引擎 5 图）：卡片工作区 `rerun/`、`old-rerun/`；副本见 `kanban/evidence/`（未跟踪目录，不进 git）
- 复跑命令（任一图）：
  - 现引擎：`STDRAW_TIMING=1 python benchmarks/tools/run_stdraw.py benchmarks/corpus/random/random-n10-i08.cld <outdir> auto`（预算由外层 timeout 控制）
  - 老引擎：`git worktree add --detach <dir> 63f5962 && cd <dir> && python benchmarks/tools/run_stdraw.py benchmarks/corpus/random/random-n10-i08.cld <outdir> auto`
- 引擎代际核对：`git log --format="%h %ci %s" -S "_ring_reposition" -- stdraw/layout_auto.py`；`git grep -c "STDRAW_TIMING" 63f5962 -- stdraw/layout_auto.py`（0）

## 9. 验收对照

- [x] 5 张 DNF 图逐张有阶段级归因（§5 表 + evidence stderr 逐图捕获）
- [x] 「回归 vs 口径变化」有数据支撑结论（§3 图同源 + §4.1 引擎代际 + §4.2 同图双引擎对照 + §5.1 函数级计数）
- [x] 可修热点给出修法方案（§7，不动手）
- [x] REPORT §10.4 补注（本分支，见 §7/§5.2）
