# M2 优化提案 1/3：`route_final`（最终布线段）

状态：提案（M1-B 前置交付物，未动手改；供 M2 拍板）。
证据基准：`benchmarks/REPORT.md` §10.3（37 图计时口径，±2× 方差声明）与
`benchmarks/raw/v082/timing-summary.md`；代码位 `stdraw/layout_auto.py`
`_timing.mark("route_final")` 一段。

## 现状证据

- 37 图聚合口径：`route_final` 合计 310,737 ms = **全墙钟 41.2%**，单项最大瓶颈（REPORT §10.3 裁定语：「墙钟不在 CP-SAT 证明段」）。
- 典型值：bullwhip 94.2 ms（13.6%）；fishing-collapse 508.5 ms（26.3%）；random n10 图上被 polish 段掩盖（0.5–0.8%）——瓶颈集中在经典语料与 n20。
- 构成：可见性图 Dijkstra（逐边独立跑，恰好最优）+ 切线弧平滑 + 密集探针 gate_eval + joint reroute。

## 改法（两步，独立可验）

1. **共享最短路树**：可见性图对同一起点框的多条出边只建一棵 Dijkstra 树。
   度 ≥2 的框（fan 形态）天然复用，Dijkstra 次数从 O(m) 降到 O(|起点框|)。
2. **EvalCache 延伸**：`stdraw/routing.py` 的 EvalCache（§9.4 已落）目前只覆
   polish 块；把 per-(框集, clearance) 的可见性图构建也纳入内容寻址缓存，
   同图多次 Router 重建（trial gate / 守卫 / 管线 replay）直接命中。

## 预期收益

- 经典语料 + n20：route_final 段 1.5–2×（Dijkstra 复用按 fan 度数收益，
  实测口径先跑 classic 19 图 + n20 采样腿再定）；聚合墙钟估 −10~20%。
- 缓存延伸对 candidate-v1 管线（每候选一次 route_and_evaluate）同样生效。

## 确定性影响评估

- **中风险**：共享最短路树改变 per-edge 松弛顺序，可见性图上的等长路径
  平局必须钉死同一 tie-break 链（前驱字典序 → 边 id），否则字节漂移。
- 缓存延伸零风险（内容键命中即值恒等，§9.4 已证口径）。
- 验证门：ortho 冻结回归（字节铁门）+ 60 图双腿 sweep 零漂移 + 跨机双矩阵。

## 建议拍板级别

P1（先做缓存延伸，零字节风险）；共享最短路树单独立卡，先跑 classic 19 图
字节 sweep 再谈合入。
