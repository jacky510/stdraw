# longtail 验收集（M1-B）

按拓扑族审查补族的验收语料：链 / 星 / 非平面在 Phase 0 打标中 0 覆盖
（空族警告），本目录补齐作为 M1-B 消融验收集。全部 n≤10，拓扑族标签在
每个 `.cld` 首行注释（`# ... | topology family: <family> | n=<n>`）。

| 文件 | 族 | n | m | 构造 |
|---|---|---|---|---|
| longtail-chain-03.cld | chain | 3 | 2 | 纯链（无环树） |
| longtail-chain-06.cld | chain | 6 | 5 | 纯链 |
| longtail-chain-09.cld | chain | 9 | 8 | 纯链 |
| longtail-star-05.cld | star | 5 | 4 | 纯星（1 hub + 4 叶） |
| longtail-star-07.cld | star | 7 | 6 | 纯星 |
| longtail-star-09.cld | star | 9 | 8 | 纯星 |
| longtail-nonplanar-k5.cld | nonplanar | 5 | 10 | K₅（cr=1，删 ≤1 边可平面化） |
| longtail-nonplanar-k33.cld | nonplanar | 6 | 9 | K₃,₃（cr=1，删 ≤1 边可平面化） |
| longtail-nonplanar-petersen.cld | nonplanar | 10 | 15 | Petersen 图（cr=2） |
| longtail-mixed-chain-cycle.cld | mixed | 6 | 6 | 4-环 + 挂链（真链+环混合；初版为纯 C4，返修正构） |
| longtail-mixed-star-cycle.cld | mixed | 6 | 6 | 星 + 叶间一弦（星+环） |
| longtail-mixed-chain-star.cld | mixed | 7 | 6 | 星挂链（无环树） |

约定：

- 无 `loop` 声明（loop 审计对独立枚举做闭合校验，无需声明即可审计）；
- 极性全 `+`（拓扑结构验收集，不承载 R/B 语义测试——那由 classic 语料承
  担）；
- 消融口径见 `docs/m1b-planarization-ablation.md`（M1-B 消融报告），
  复跑工具：`benchmarks/tools/ablate_m1b.py`。

本目录是追加语料（AGENTS.md「Allowed: Append samples to benchmarks/corpus/」），
不触碰既有语料与 REPORT.md 已发布数字。
