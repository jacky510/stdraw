# 修补工序合格判断盘点表（T4 纯重构，2026-11-10）

单一真源：`stdraw/gates.py`（`GatePolicy` + `GateBaseline` + `edge_gate_check`）。
本卡为**纯重构**：每道修补工序的现有口径**原样保留**（差异全部用 policy 字段表达），
**不做任何口径统一**。§3 的口径不一致清单只登记，是否统一另行评审拍板。

基线依据：HEAD 0f35a39 前后的逐字节一致 sweep（classic 21 + random n10，
layout.json sha256 全同），复跑命令见 §5。

## §1 route_all 后的修补工序（delivery acceptance gates，`_edge_stats` 记账级）

`_edge_stats(i, routes)` 五元组 = (press, min_clear, ang, cross, msep)。
记 `before` = 改前同口径快照。

| # | 工序 | 调用点 | press | crossing | clearance 阈值 | own-box | msep | 附加判据 | policy 预设 |
|---|---|---|---|---|---|---|---|---|---|
| G-FAN | fan_spread 整组回退检查 | routing.py `fan_spread`（~1322） | ≤before（单调） | ≤before | `cl-1e-6`（None 容忍） | **无检查** | ≥4.0（None 容忍） | — | `FAN_SPREAD` |
| G-PAIR-BAND | 互对带内局部重路由 | `_reroute_pair_band.gates_ok`（~1446） | ≤before | ≤before | `cl-1e-6` | `_own_box_ok`（绝对） | ≥4.0 | — | `PAIR_BAND` |
| G-MIDBAND-T0 | 连接点带内钳制 Tier 0 基线记账验收 | `midband_reanchor`（~1660） | ≤before | ≤before | `cl-1e-6` | **无检查** | ≥4.0 | — | `MIDBAND_TIER0` |
| G-MIDBAND-T1 | 连接点带内钳制 Tier 1 增强阶梯验收 | `midband_reanchor`（~1703） | ≤before | ≤before | `cl-1e-6` | `_own_box_ok`（绝对） | ≥4.0 | — | `MIDBAND_CLAMP` |
| G-MUTUAL-STRAIGHT | 互对直线重指派验收 | `mutual_straight_reroute`（~1560） | **==0（绝对）** | i: ≤`info['cross']`（_evaluate 记账）；j: ≤before（_edge_stats 记账） | `cl-1e-6` | `_own_box_ok`（绝对） | ≥4.0 | — | `MUTUAL_STRAIGHT` |
| G-ARRIVAL(lgcy) | lens 到达翻转（snap 前） | `mutual_arrival_flip` enhanced_gates=False（~1898） | ≤before | ≤before | `cl-1e-6` | `_own_box_ok`（绝对） | ≥`sep_floor`（改前分离度下取-0.05，≥4.0） | — | `ARRIVAL_LEGACY` |
| G-ARRIVAL(enh) | lens 到达翻转（snap 后） | `mutual_arrival_flip` enhanced_gates=True（~1898） | ≤before | ≤before | **`cl-PRESS_MARGIN-1e-6`** | **`_own_press` ≤before（单调）** | ≥12.0（enh 固定窄透镜下限） | — | `ARRIVAL_ENHANCED` |
| G-LENS-JOINT | lens 四锚联合重指派 | `lens_joint_reassign`（~2095） | ≤before | ≤before | `cl-PRESS_MARGIN-1e-6` | `_own_press` 单调 | **不查**（分离度由 sep≥12 的 min_pair_dist 单独把门） | sib 单调 + `_cert_angle_ok` + `_anchors_in_band` | `LENS_JOINT` |
| G-LENS-PAIR | lens 镜像对吸附 | `_lens_pair_joint_snap`（~2474） | ≤before | ≤before | `cl-PRESS_MARGIN-1e-6` | `_own_press` 单调 | 不查（同上 sep 把门） | sib 单调 + `_cert_angle_ok` | `LENS_PAIR` |
| G-SNAP | anchor_snap tier-1 逐锚验收 | `anchor_snap`（~2729） | ≤before | ≤before | `cl-PRESS_MARGIN-1e-6` | `_own_press` 单调 | ≥4.0 | sib 单调 + `_cert_angle_ok` + `_coincide_no_worse` | `SNAP` |
| G-SNAP-DETOUR | anchor_snap tier-2 整段绕行 | `_snap_joint_detour`（~2971） | ≤before | ≤before | `cl-PRESS_MARGIN-1e-6` | `_own_press` 单调 | ≥4.0 | sib 单调 + `_cert_angle_ok` + `_coincide_no_worse` | `SNAP`（同 G-SNAP） |
| G-SNAP-RETRY | give-way 让位双方验收 | `_snap_retry_conflicts` ok_j/ok_i（~3131/~3173） | ≤before | ≤before | `cl-PRESS_MARGIN-1e-6` | `_own_press` 单调 | ≥4.0 | sib 单调 + `_cert_angle_ok`（**无 coincide 检查**） | `SNAP_RETRY` |

## §2 candidate-pool 过滤（`_evaluate` 记账级，**不在本模块收拢范围**，保持内联）

这些检查打在候选 info（`_evaluate` 输出）上，记账口径与 `_edge_stats` 不同
（press 绝对 0、min_clear 候选级），改它们属行为面而非收拢：

- `route_all` 主选路（`_evaluate` 的内部硬门与打分）；
- `coincide_reroute`：候选 press==0、`min_clear ≥ cl-1e-6`、角度 ≥ANCHOR_MIN_DEG、
  交叉数不增、重合跨度严格下降；
- `mutual_straight_reroute` 候选过滤段（与验收段同函数内的两套记账，见 §3-5）。

## §3 口径不一致清单（**只登记，不统一；等拍板**）

1. **clearance 阈值两套**：`cl-1e-6`（G-FAN/G-PAIR-BAND/G-MIDBAND/G-MUTUAL-STRAIGHT/G-ARRIVAL lgcy）
   vs `cl-PRESS_MARGIN-1e-6`（G-ARRIVAL enh/G-LENS-*/G-SNAP-*）。
   背景：`_edge_stats` 量到 1px 外扩矩形，`-PRESS_MARGIN` 档折算回原始边界矩形 ≈ CI/certificate 的
   raw ≥ CLEARANCE 口径（见 anchor_snap 内注释，population-logistic n-g2 实测 15.79 膨胀 = 16.79 raw）。
   即：**前五处比证书口径严 1px，后六处与证书口径对齐**。
2. **own-box 三种口径**：`_own_box_ok` 绝对（G-PAIR-BAND/G-MIDBAND/G-MUTUAL-STRAIGHT/G-ARRIVAL lgcy）、
   `_own_press` 单调不恶化（G-ARRIVAL enh/G-LENS-*/G-SNAP-*）、**完全不查**（G-FAN）。
3. **press 两套**：绝对 ==0（G-MUTUAL-STRAIGHT）vs 单调 ≤before（其余全部）。
4. **crossing 记账两套并存于同一函数**：G-MUTUAL-STRAIGHT 对 i 用候选 info['cross']（_evaluate）、
   对 j 用 `_edge_stats`；其余工序统一用 `_edge_stats`。
5. **附加判据覆盖不一**：`_cert_angle_ok` 只有 snap 系（G-LENS-*/G-SNAP-*）查；
   `_coincide_no_worse` 只有 G-SNAP/G-SNAP-DETOUR 查（G-SNAP-RETRY 让位后反而不查）；
   `_anchors_in_band` 只有 G-LENS-JOINT 查。
6. **msep 三种**：4.0 固定（多数）、`sep_floor` 改前导出变量（G-ARRIVAL lgcy）、12.0 窄透镜固定
   （G-ARRIVAL enh）、不查改由 sep≥12 独立把门（G-LENS-*）。
7. **vg 路由端点两套——已统一（方案 b，2026-11-24）**：`route.points`（证书 metrics / `edges[].anchors` /
   check 13 的校验折线用）vs `route.vg_corners[0]/[-1]`（`path_d` 渲染用）。行内端点改位工序（midband / fan）
   原地改 `points[0]` 不回写 `vg_corners`/`vg_fillets`；anchor_snap 正常跑时从 corners 重导 `points` 把两者对齐，
   但 E/N≥1.6 延迟（DEFERRED）或回退（REVERTED）时保留改位前的 pre-snap 路由 → 两套端点不一致原样出货，
   check 13 `path_d` 偏差（tier-A 13 图，2.4–32px；随机 n20 最大 32px）。
   **修法**：`layout_auto.py` 新增 `_resync_vg_points(routes)`，DEFERRED / REVERTED 两个分支（含 ring 改位探针
   `_delivery_chain_probe` 的同一回退路径）在 `routes = _pre_routes` 之后对 vg 路由用
   `dense_geometry(vg_corners, vg_fillets)` 重导 `points`——度量对齐实际渲染（「画在哪就量在哪」），该路由的
   midband 端点位移随之放弃；两套几何本已一致的路由数值相同、零字节影响。重导条数 >0 时 deferred 记录多带
   `vg_resynced` 键。未选 (a)（改位处同步平移 corner）：会改变所有含 vg 且被 midband 改位的图的 snap 起点，
   影响面超出缺陷图集合。tier-A 双腿 sweep（同机同解释器、cp-sat-layered）：13 图 check 13 清零，
   其余 44/44 rc=0 图逐字节零漂移，rc=1 图 16 张里仅这 13 张变字节（见 `docs/validation-tiers.md` §0.1）。
   **残余**：行内改位工序本身仍未回写 corner——非延迟图靠 snap 重导兜底；若日后出现「snap 保留但该 vg 端点未被
   snap 移动」的不一致（check 13 会抓住），再评估 (a)。

以上差异均有其历史成因注释（ref-scrubbed 各轮），**任何统一都会改变输出字节**，
本卡不改；是否统一、对哪些图有字节影响，等口径表评审另行开卡。

## §5 复跑命令（逐字节一致门）

```bash
# 逐图 layout.json sha256 清单（classic 21 + random n10），重构前后各跑一次比对
python t4_sweep.py <leg> <abs_out_dir>     # 脚本随卡归档；core 循环 = python -m stdraw layout <file.cld> --outdir <dir>
# 确定性二跑：同输入同命令两次 sha256 全同（AGENTS.md 既有口径）
```

## §6 本卡改动范围

- 新增 `stdraw/gates.py`（GatePolicy/GateBaseline/edge_gate_check + 11 个 policy 预设）；
- `stdraw/routing.py`：12 处 `_edge_stats` 级验收表达式改为调用 `edge_gate_check`（见 §1 表）；
  `_evaluate` 级候选过滤与 STDRAW_SNAP_DEBUG 调试打印**原样不动**；
- 行为零变化证明：重构前后双跑 sha256 全同 + 全量 pytest 绿。

## §7 等价加速与透镜合同（2026-11-25）

三处**不改任何输出字节**的等价加速（金标准 8 图 + 4 节点 limits-to-growth 原图的布局输出逐字节不变）：

1. **候选下界剪枝**（`Router._cand_lb`，`_evaluate_cached` 候选循环）：候选分数只含精确已知项
   （线型偏好 `kind_pref`、规则惩罚 `rule_pen`、0.01×线长）的下界 ≥ 现任分数时，跳过几何求值。
   下界只少算不多算，被跳过的候选不可能胜出，选择结果与全量求值一致。
2. **互指对分离度 memo**（`EvalCache.pairsep` / `samples12`，内容键 `sib_key`）：同一对端点采样折线的
   `min_pair_dist(…, 4)` 只算一次。
3. **lens 联合重指派的 bbox 预检**（`lens_joint_reassign`，G-LENS-JOINT）：两条弧采样折线的包围盒间隙
   ≥12px 时直接判 `sep≥12` 通过（包围盒间隙是两条折线真实最小距离的下界：任意点对距离 ≥
   包围盒间隙，下界已 ≥12 则真实值必 ≥12），否则照旧跑 `min_pair_dist`。

**透镜合同**（证书 `lens_pairs_closed` / check 第 9 门，`lens-chain` 模式；口径正本
`docs/layout-modes.md`「透镜链」节）：每个互指对的两条边都是 Q 弧，鼓度 = 二次 Bezier 顶点到弦的
偏移 / 弦长（有控制点时精确 = 0.5×|ctrl − 弦中点|；无控制点按折线顶点取）≥ `gates.LENS_BULGE_MIN`
（0.15），且两弧鼓向弦的异侧。`gates.arc_bulge(pts, ctrl=None, flip=False)` 是鼓度与侧别的单一来源。

## §8 回路方向弧线默认的候选序（2026-11-25）

口径正本 `docs/edge-placement-rules-v1.md` §20，本节只登记路由侧的实现约定：

- 作用域 = `layout()` 级 `routing.loop_arc_context(graph.loops)`：放置试验 / polish / 最终路由 / 修复探针里
  构造的每个 `Router` 读同一份 `loop_arc_sides`（按当前盒中心现算侧别）。**不能只包第一阶段**——
  最终 Router 在第二阶段才构造，拿不到偏好就会交付直线（实测踩坑）。手工路径与无回路图不进上下文。
- 候选序（`_candidates_linearc`，成员线且非互指对）：顺向弧（5 元组，规则罚 0）→ 反向弧（`ARC_NEAR_PENALTY` 25）
  → 直线（`STRAIGHT_FALLBACK_PENALTY` 30，低于折线类型代价 40）。`_candidates` 的 memo 键含 `pref`；
  5 元组 / 6 元组混排对评分与下界剪枝透明（`cand[5]` 缺省 = 0.0）。互指对与非成员线走 legacy 分支，逐字节不变。
- 几何项权重照旧主导（压框 4000 / 交叉 40 / 净距 30）：干净的直线（+30）输给干净的顺向弧（+0）；
  压框或交叉的顺向弧输给干净的反向弧（+25）或干净的直线（+30）。兜底是算出来的，不是阈值放出来的。
- 证书记录在交付层重算（`routing.loop_arc_audit` 对最终坐标重评顺向弧候选 → 实测原因），
  不读路由器内部状态；anchor-snap 联合绕行、构造模板几何各带来源标注。
