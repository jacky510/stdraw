# Agent 接口契约（T13 修复建议 / T14 语义提示 / T15 规模上限 / 错误面契约）

面向 agent 调用方的接口约定。语法细则见 `docs/dsl-spec-v0.1.md` 附录 B（英文正本）与 zh-CN 副本；本文是行为契约与产物 schema。来源：Copilot 评审清单 T13/T14/T15（stdraw-copilot-issues-2026-11-24）。

## T15 规模上限（先说，决定 agent 怎么调）

- 服务上限 **`MAX_LAYOUT_NODES = 15`**（`stdraw/limits.py` 常量）。节点数 > 15 时 CLI **在任何布局尝试之前**返回结构化拒绝：
  - 写 `refusal.json`（schema 见下），stdout 打印同一 JSON，stderr 一行人读摘要，**退出码 3**；不产出 layout / certificate / demo；
  - `advice` 字段建议**按回路拆图**：每个回路（或紧耦合回路束）作为独立 stdraw 图布局，共享变量跨图保持一致；
  - `split_hint.loops` 列出全部已声明回路（id / 标签 / 判定的 R/B / 节点序列），即候选拆分单元。
- `--allow-oversize`：**仅供校验基础设施**（`benchmarks/tools/sweep_tiers.py` 的 tier A 要跑 random-n20 语料）——把上限放宽到引擎能力天花板 `HARD_CEILING_NODES = 20`（n≤20 范围拍板）。**> 20 即使带旗也拒绝**；n30/n50 语料已退役，任何形态都不跑。agent 调用方应保持默认拒绝路径。
- `refusal.json` schema：

```json
{"rejected": true,
 "reason": "node_limit_exceeded",
 "limit": 15, "hard_ceiling": 20,
 "nodes": 16, "edges": 16, "declared_loops": 1,
 "advice": "split the graph by loops: ...",
 "split_hint": {"note": "...", "loops": [{"id": "R1", "label": "...", "kind": "R", "nodes": [...]}]}}
```

## 错误面契约（0.10.1）

CLI 的失败面分两类，产物文件名与退出码都不同——agent 按文件名判断，不必解析 stderr：

| 情形 | 产物 | 退出码 | 发生在 |
|---|---|---|---|
| 节点数超过上限 | 只写 `refusal.json`，不产出 layout/certificate/demo | **3** | 加载+结构校验通过后、任何布局尝试之前 |
| 输入面错误（语法 / 结构校验 / 读不到文件 / JSON 不是图模型） | 只写 `parse_error.json`，不产出 layout/certificate/demo | **2** | `load_graph` 与结构校验阶段 |
| 布局跑完但几何自检不过 | 产物齐全（`geometry_report.json` 里有失败项） | **1** | 布局之后 |
| 成功 | 全套产物 | **0** | — |

- **默认不吐 Python traceback**：面向 agent 的调用面只给结构化 JSON（stdout 打同一份 payload）+ 一行 stderr 摘要。需要栈时加 `STDRAW_DEBUG=1`（退出码不变，仍为 2）。
- `parse_error.json` schema（`line` / `column` 可为 `null`，其余必有）：

```json
{"error": true,
 "kind": "syntax",
 "line": 6, "column": 10,
 "reason": "DSL line 6 cannot be parsed: 'b -> + a @anchors src=n-g8'",
 "snippet": "b -> + a @anchors src=n-g8",
 "detail": "unknown anchor id: 'n-g8' (vocabulary: n/e/s/w, ne/se/sw/nw, <side>-g1..g7)",
 "input": "g.cld", "exit_code": 2}
```

  - `kind`：`syntax`（该行语法不成立：未知锚点 id / 未知 tag / 重复 tag / 认不出任何文档形式）｜`structure`（`Graph.validate()` 报告的声明不一致：未声明端点·回路·分组、自环、重复边、极性非法、`@main`/`@order`/`@pair` 指向不存在的 id）｜`io`（文件不存在或读不出）｜`input`（`.json` 不是 stdraw 图模型）。
  - `reason` 与库异常消息**逐字相同**（多条问题用 `\n  ` 串联）；`detail` 给更具体的第一因（如未知锚点 id 的词表范围）；`problems` 仅在 `kind=structure` 时出现，逐条列 `{line, reason}`（行号可为 `null`）。
  - `line` 是 1 基源行号；`.json` 输入与 `io` 类没有行号 → `null`。`column` 是 1 基列号：语法类错误指向出错 tag 的起始位置，行级语义问题为 `null`。
  - `input` 只记文件名（不落绝对路径）；`exit_code` 与进程退出码一致（恒 2）。
- **库 API 不变**：`stdraw.dsl.parse()` 仍然抛异常——`DSLParseError` 是 `ValueError` 子类且消息逐字保持历史文本，Python 调用方照旧 `try/except ValueError`；结构化字段只服务 CLI 呈现层。
- 两类错误互斥：同一份输入不会同时产出 `refusal.json` 与 `parse_error.json`（结构校验先于规模检查，语法/结构错误时根本走不到规模检查）。

## T13 FAIL 结构化修复建议

- **证书**（`certificate.json`）：每个值为 `False` 的硬门，`repair_hints` 数组给一条 `{"gate", "hint", "retry": true}`（`hint` 指向 `@main` / `@order` / `@pair` 语义提示或拆图杠杆）。仅在存在失败门时输出——全过证书字节级不变（金标准集字节锁定，重祝福须授权）。
  - **`edge` 的口径（必出，仅限两个几何门）**：`visual_crossings_zero` 与 `lines_no_coincidence` 的 hint **必带** `edge`，格式 `u<->v`（节点 id，方向省略），取自本次测量明细的首条（`metrics.visual_crossing_details` / `metrics.line_line_coincident_details`）；这两个门 FAIL 当且仅当明细非空，故无缺失分支。其余门的 hint **不含** `edge`（它们不测线段对，硬编一个 tag 就是编造事实）。完整交叉/重合明细仍在 `metrics` 里，`edge` 只是指针级摘要。取舍见 `docs/adr/ADR-0020-repair-hint-edge-source.md`。
  - **口径**：只有硬门 FAIL 才附建议。报告项（`crossings_zero` / `row_align_ge_060` / `loop_edges_arced`）是软目标不是门，不产生建议块。
  - **文案纪律**（default 备案 2026-11-26，依据 stdraw20 人工校准经验）：`cv_le_035` / `pitch_uniform` / `column_snap24_ge_060` / `anchors_standard` 四门的 hint 不得把 agent 往机械网格 / 16 锚集坐标上推（实测这些门惩罚人类风格排布，anchors_standard 阻塞约 80% 的人工稿）——只指语义提示与拆图。门阈值与 grade 语义不受文案层影响，本卡未放宽。
  - 带交叉下界的 hint（非平面图 `visual_crossings_zero` 不可达 0）留后续卡，不在本卡。
- **回路审计**（`loops_audit.json`）：
  - 未声明回路 → `suggested_declarations`：**可直接粘贴**的 `loop <id> "..." "<R|B>" [nodes]` 声明行，R/B 由极性奇偶独立判定（`xauto1`、`xauto2`…，避开已声明 id）。贴回后还需给该回路的边打 `@loops` 标签（`repair_hints` 里的 fix 带此指引）；
  - 声明环不闭合 → `repair_hints`：若枚举覆盖到同节点集的闭合走线，给可粘贴的更正声明；否则指明补标签方向；
  - R/B 标错 → `repair_hints`：按极性奇偶给可粘贴的更正行；
  - 三个键均只在有问题时输出，干净审计字节不变。CLI 同时把这些 fix 打到 stdout（`hint: ...` 行）。

## T14 语义提示（替代像素参数）

- 语法：`@main R1`（主回路居中）/ `@order R1,B1,R2`（回路阅读顺序）/ `@pair a,b`（两变量相邻）。校验、往返、证书记录见 dsl-spec 附录 B。
- 实际机制（提示存在时才进入任何提示代码路径；无提示图输出字节级不变）：
  - `@order`：流水线入口按声明序列重排 `graph.loops`——回路审计清单、回路弧向作用域、注解层顺序都跟随（幂等）；
  - `@main`：ring 模式强制主环选择（`meta.ring.hint_main` 如实记录；试验门兜底不失效）；layered 模式在放置目标函数加入居中项（cp-sat）/ 整体平移居中（construct）；
  - `@pair`：ring 模式旋转环序列使两变量占相邻环位；layered 模式目标函数加相邻项（cp-sat）/ 相邻打包（construct）。跨行对无法相邻，如实不生效。
- 证书 `hints` 块：声明的 id + 每条提示馈入的机制说明——仅在有提示时输出。
- **弃用（本卡只标记，物理删除留 P3 减法卡）**：`--pitch` / `--hub-side` / `--column-order` 继续工作，但 `--help` 标 DEPRECATED、使用时 stderr 打 `[deprecated]` 警告、certificate `honest_notes` 追加一条弃用记录（条件追加，不用则字节不变）。

## 决策记录

- 上限取 15（n≤20 硬限内留余量），拒绝发生在布局前（不先布局再给 uncertified）。
- 退出码不重排：**0 成功 / 1 布局跑完但几何门不过 / 2 输入面错误（`parse_error.json`）/ 3 规模拒绝（`refusal.json`）**——0.10.0 起 1/2/3 已是这个语义，错误面契约只是把 2 的产物从"仅 stderr"补齐成结构化 JSON。
- tier A 全量字节门（61 图，含 random-n20 x20）经 `sweep_tiers.py --allow-oversize` 保持不变；ci_checks B2-P 的 n20 L2 腿同旗保持其计划化降级覆盖，另加 B2-T15 拒绝腿。
