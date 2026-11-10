# 修补工序合格判断盘点表（T4 纯重构，2026-11-10）

单一真源：`stdraw/gates.py`（`GatePolicy` + `GateBaseline` + `edge_gate_check`）。
本卡为**纯重构**：每道修补工序的现有口径**原样保留**（差异全部用 policy 字段表达），
**不做任何口径统一**。§3 的口径不一致清单只登记，是否统一另行评审拍板。

基线依据：HEAD 40dc106 前后的逐字节一致 sweep（classic 21 + random n10，
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

以上差异均有其历史成因注释（ref-scrubbed 各轮），**任何统一都会改变输出字节**，
本卡不改；是否统一、对哪些图有字节影响，等口径表评审另行开卡。

## §5 复跑命令（逐字节一致门）

```bash
# 逐图 layout.json sha256 清单（classic 21 + random n10），重构前后各跑一次比对
python t4_sweep.py <leg> <abs_out_dir>     # 脚本随卡归档；core 循环 = python -m stdraw layout <file.cld> --outdir <dir> --skip-3d
# 确定性二跑：同输入同命令两次 sha256 全同（AGENTS.md 既有口径）
```

## §6 本卡改动范围

- 新增 `stdraw/gates.py`（GatePolicy/GateBaseline/edge_gate_check + 11 个 policy 预设）；
- `stdraw/routing.py`：12 处 `_edge_stats` 级验收表达式改为调用 `edge_gate_check`（见 §1 表）；
  `_evaluate` 级候选过滤与 STDRAW_SNAP_DEBUG 调试打印**原样不动**；
- 行为零变化证明：重构前后双跑 sha256 全同 + 全量 pytest 绿。
