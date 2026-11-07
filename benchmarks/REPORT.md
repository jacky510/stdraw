# stdraw 基准对比报告（WS4 建立 · WS5 性能修复后重测；真实数字，赢了写赢，输了写输）

生成：benchmarks/tools/collect.py ← benchmarks/raw/（全部原始评测 JSON 留证）。

## §1 结论先行（机械生成，无人工修饰；数字出自 §3/§4/§7）

- **交叉数（classic 均值）**：stdraw-auto=0.16；stdraw-ortho=0.00；graphviz-neato=0.05；elk-layered=0.05；stdraw-auto-exact=0.16；graphviz-dot=0.16；graphviz-sfdp=0.26。交叉数全场最低的主张**不成立**（neato/ELK 均值更低，代价是排布质量：neato 框压线 1.2 + 净距违规 3.1 + 行对齐 0.05；ELK 框压线 0 但净距违规 3.0——数字见 §7）
- **排布硬门（框压线=0 且 净距违规=0，classic 均值口径）**：达成的工具 = stdraw-auto、stdraw-auto-exact、graphviz-sfdp。stdraw-auto 在该组内交叉数最低/持平，但耗时最贵
- **运行时间（classic 均值）**：stdraw-auto=10.0s vs 基线 graphviz-dot=0.03s、graphviz-neato=0.06s、graphviz-sfdp=0.03s、elk-layered=0.07s——基线快 2~3 个数量级，任何主张必须承认这一代价
- **随机族（WS5 修复后口径）**：stdraw auto-v2 的 n≥20 全 DNF 已修复（根因是 CP-SAT 证最优耗时随 n 爆炸，非 _polish——见 §5 修正记录）；修复后 n≥20 出图率/耗时以 §4 实测为准，「全规模最好」主张仍不成立（运行时间仍慢基线 2~3 个数量级）
- **综合可辩护措辞（草案，§8 展开）**：stdraw 的比较优势限定在「经典 CLD 小图、卡片式画法、硬门语义（框不压线+净距+行对齐+CV）全维度同时达标」这一域；交叉数单项与 Graphviz dot 打平、不敌 neato/ELK 裸交叉值；运行时间为其主要代价

## §2 对比协议（口径声明）

- **同一输入**：同标签、同框尺寸（stdraw textmetrics 统一给出 w×h px；Graphviz 以 inch=px/72 fixedsize 传入、ELK/stdraw 直接 px——各工具 native 坐标同为物理 px）；
- **阈值型指标**（框压线 1px / 净距违规 16px）在 native 坐标按绝对 px 判定；尺度不变指标（交叉/CV/行对齐）不受坐标尺度影响；不做强制缩放归一化（缩放改变阈值物理语义，谁被缩谁吃亏不是质量差异）；另报 bbox 作画布效率参考；
- **六指标**：crossings（相邻边除外折线严格求交）/ box_press（边进非端点框含 1px 余量）/ clear_violations（边-非端点框最小距 <16px 的 (边,框) 对数）/ spacing_cv（最近邻中心距 std/mean）/ row_align_rate（y 差 ≤4px 同行占比）/ runtime_s；
- **指标实现与 stdraw/metrics.py·routing.py 同源**（直接 import seg_cross / sample_polyline / dist_point_rect），评测代码随仓公开可复算；
- **运行时间口径**：stdraw = 进程内核心布局计时（不含解析/渲染/证书）；Graphviz/ELK = 子进程 wall-clock（含启动开销，对基线略不利，报告如实注明）；
- **预算协议**：外部预算：ortho 60s；auto classic 300s / 随机 n≤10 350s / 随机 n≥20 100s；cr(G) 精确层 300s；超预算 = DNF 如实计数（DNF 不是输一场空，是「该预算内不产布局」的事实）；引擎侧确定性设计：无墙钟时限（墙钟截断随机器负载漂移、破坏逐字节复现），n>10 的 CP-SAT 定位自 WS5 起用**确定性时间预算**（max_deterministic_time=8det，操作计数口径，同版本同输入在任何机器上同一 incumbent），n≤10 与布线层求到最优为止——两种口径输出均逐字节可复现；
- **auto-exact 形态** = auto 布局复用（WS2 已证同输入逐字节一致）+ 独立跑 cr(G)，runtime = 布局 + 精确层；
- **环境**：Windows 11 / Python 3.12.10 + networkx + OR-Tools CP-SAT / Graphviz 16.1.0（官方 Release zip，sha256 校验一致）/ elkjs（bundled，node 22.23.2）/OGDF：未运行（见 §6）。stdraw auto/auto-exact 数字为 **WS5 修复后重测**（引擎 b4ea801+）；基线（Graphviz/ELK）与 stdraw-ortho 沿用 WS4 同机实测（两者不在本次修复面，引擎未变）。

## §3 经典 CLD 语料（19 张，n=4…8）逐图大表

### stdraw·ortho(构造法)

| 图 | n | m | loops | 交叉 | 框压线 | 净距违规 | CV | 行对齐率 | 耗时s | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|
| arms-race | 4 | 4 | 1 | 0 | 0 | 0 | 0.218 | 0.00 | 0.00 | ok |
| brand-flywheel | 6 | 8 | 3 | 0 | 2 | 2 | 0.345 | 0.67 | 0.01 | ok |
| bullwhip | 5 | 6 | 2 | 0 | 4 | 4 | 0.347 | 0.40 | 0.01 | ok |
| burnout-attrition | 5 | 6 | 2 | 0 | 0 | 1 | 0.292 | 0.40 | 0.01 | ok |
| classic-cld-growth-and-burden | 8 | 13 | 6 | 0 | 4 | 5 | 0.185 | 0.62 | 0.02 | ok |
| debt-spiral | 5 | 6 | 2 | 0 | 0 | 0 | 0.479 | 0.40 | 0.01 | ok |
| eroding-goals | 5 | 6 | 2 | 0 | 3 | 3 | 0.000 | 0.80 | 0.01 | ok |
| fishing-collapse | 6 | 9 | 5 | 0 | 0 | 1 | 0.601 | 0.67 | 0.01 | ok |
| fixes-that-fail | 4 | 5 | 2 | 0 | 0 | 0 | 0.312 | 0.00 | 0.00 | ok |
| induced-demand | 5 | 7 | 4 | 0 | 3 | 3 | 0.394 | 0.40 | 0.01 | ok |
| learning-flywheel | 4 | 5 | 2 | 0 | 0 | 0 | 0.312 | 0.00 | 0.00 | ok |
| limits-to-growth | 5 | 7 | 3 | 0 | 1 | 2 | 0.314 | 0.40 | 0.01 | ok |
| population-logistic | 4 | 6 | 3 | 0 | 0 | 0 | 0.093 | 0.50 | 0.00 | ok |
| renewable-resource | 5 | 7 | 3 | 0 | 4 | 4 | 0.037 | 0.80 | 0.01 | ok |
| shifting-the-burden | 5 | 8 | 4 | 0 | 2 | 3 | 0.024 | 0.80 | 0.01 | ok |
| soil-erosion | 6 | 8 | 3 | 0 | 1 | 2 | 0.397 | 0.67 | 0.01 | ok |
| tragedy-of-the-commons | 5 | 6 | 2 | 0 | 0 | 1 | 0.545 | 0.40 | 0.01 | ok |
| urban-migration | 6 | 8 | 3 | 0 | 0 | 0 | 0.327 | 0.33 | 0.01 | ok |
| wage-price-spiral | 5 | 6 | 2 | 0 | 2 | 2 | 0.410 | 0.80 | 0.01 | ok |

### stdraw·auto(WS3布线)

| 图 | n | m | loops | 交叉 | 框压线 | 净距违规 | CV | 行对齐率 | 耗时s | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|
| arms-race | 4 | 4 | 1 | 0 | 0 | 0 | 0.065 | 0.00 | 1.85 | ok |
| brand-flywheel | 6 | 8 | 3 | 0 | 0 | 0 | 0.096 | 0.33 | 17.14 | ok |
| bullwhip | 5 | 6 | 2 | 0 | 0 | 0 | 0.021 | 0.00 | 3.77 | ok |
| burnout-attrition | 5 | 6 | 2 | 0 | 0 | 0 | 0.119 | 0.40 | 6.89 | ok |
| classic-cld-growth-and-burden | 8 | 13 | 6 | 1 | 0 | 0 | 0.162 | 0.62 | 50.00 | ok |
| debt-spiral | 5 | 6 | 2 | 0 | 0 | 0 | 0.192 | 0.00 | 4.58 | ok |
| eroding-goals | 5 | 6 | 2 | 0 | 0 | 0 | 0.121 | 0.80 | 3.83 | ok |
| fishing-collapse | 6 | 9 | 5 | 0 | 0 | 0 | 0.156 | 0.33 | 24.14 | ok |
| fixes-that-fail | 4 | 5 | 2 | 0 | 0 | 0 | 0.192 | 0.50 | 1.06 | ok |
| induced-demand | 5 | 7 | 4 | 0 | 0 | 0 | 0.197 | 0.00 | 9.58 | ok |
| learning-flywheel | 4 | 5 | 2 | 0 | 0 | 0 | 0.265 | 0.50 | 1.66 | ok |
| limits-to-growth | 5 | 7 | 3 | 1 | 0 | 0 | 0.197 | 0.60 | 4.80 | ok |
| population-logistic | 4 | 6 | 3 | 0 | 0 | 0 | 0.135 | 0.50 | 7.81 | ok |
| renewable-resource | 5 | 7 | 3 | 0 | 0 | 0 | 0.113 | 0.40 | 11.68 | ok |
| shifting-the-burden | 5 | 8 | 4 | 0 | 0 | 0 | 0.021 | 0.80 | 9.40 | ok |
| soil-erosion | 6 | 8 | 3 | 0 | 0 | 0 | 0.119 | 0.33 | 15.79 | ok |
| tragedy-of-the-commons | 5 | 6 | 2 | 0 | 0 | 0 | 0.202 | 0.00 | 3.77 | ok |
| urban-migration | 6 | 8 | 3 | 1 | 0 | 0 | 0.160 | 0.33 | 8.15 | ok |
| wage-price-spiral | 5 | 6 | 2 | 0 | 0 | 0 | 0.000 | 0.00 | 4.44 | ok |

### stdraw·auto+WS2(精确层)

| 图 | n | m | loops | 交叉 | 框压线 | 净距违规 | CV | 行对齐率 | 耗时s | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|
| arms-race | 4 | 4 | 1 | 0 | 0 | 0 | 0.065 | 0.00 | 2.24 | ok |
| brand-flywheel | 6 | 8 | 3 | 0 | 0 | 0 | 0.096 | 0.33 | 17.56 | ok |
| bullwhip | 5 | 6 | 2 | 0 | 0 | 0 | 0.021 | 0.00 | 4.17 | ok |
| burnout-attrition | 5 | 6 | 2 | 0 | 0 | 0 | 0.119 | 0.40 | 7.38 | ok |
| classic-cld-growth-and-burden | 8 | 13 | 6 | 1 | 0 | 0 | 0.162 | 0.62 | 50.52 | ok |
| debt-spiral | 5 | 6 | 2 | 0 | 0 | 0 | 0.192 | 0.00 | 4.95 | ok |
| eroding-goals | 5 | 6 | 2 | 0 | 0 | 0 | 0.121 | 0.80 | 4.22 | ok |
| fishing-collapse | 6 | 9 | 5 | 0 | 0 | 0 | 0.156 | 0.33 | 24.53 | ok |
| fixes-that-fail | 4 | 5 | 2 | 0 | 0 | 0 | 0.192 | 0.50 | 1.43 | ok |
| induced-demand | 5 | 7 | 4 | 0 | 0 | 0 | 0.197 | 0.00 | 9.98 | ok |
| learning-flywheel | 4 | 5 | 2 | 0 | 0 | 0 | 0.265 | 0.50 | 2.03 | ok |
| limits-to-growth | 5 | 7 | 3 | 1 | 0 | 0 | 0.197 | 0.60 | 5.20 | ok |
| population-logistic | 4 | 6 | 3 | 0 | 0 | 0 | 0.135 | 0.50 | 8.16 | ok |
| renewable-resource | 5 | 7 | 3 | 0 | 0 | 0 | 0.113 | 0.40 | 12.08 | ok |
| shifting-the-burden | 5 | 8 | 4 | 0 | 0 | 0 | 0.021 | 0.80 | 9.78 | ok |
| soil-erosion | 6 | 8 | 3 | 0 | 0 | 0 | 0.119 | 0.33 | 16.18 | ok |
| tragedy-of-the-commons | 5 | 6 | 2 | 0 | 0 | 0 | 0.202 | 0.00 | 4.15 | ok |
| urban-migration | 6 | 8 | 3 | 1 | 0 | 0 | 0.160 | 0.33 | 8.54 | ok |
| wage-price-spiral | 5 | 6 | 2 | 0 | 0 | 0 | 0.000 | 0.00 | 4.83 | ok |

### Graphviz dot

| 图 | n | m | loops | 交叉 | 框压线 | 净距违规 | CV | 行对齐率 | 耗时s | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|
| arms-race | 4 | 4 | 1 | 0 | 0 | 2 | 0.067 | 0.00 | 0.03 | ok |
| brand-flywheel | 6 | 8 | 3 | 0 | 0 | 2 | 0.113 | 0.33 | 0.02 | ok |
| bullwhip | 5 | 6 | 2 | 0 | 0 | 2 | 0.137 | 0.00 | 0.02 | ok |
| burnout-attrition | 5 | 6 | 2 | 0 | 0 | 2 | 0.129 | 0.40 | 0.02 | ok |
| classic-cld-growth-and-burden | 8 | 13 | 6 | 1 | 0 | 5 | 0.342 | 0.62 | 0.02 | ok |
| debt-spiral | 5 | 6 | 2 | 0 | 0 | 4 | 0.046 | 0.00 | 0.14 | ok |
| eroding-goals | 5 | 6 | 2 | 0 | 0 | 2 | 0.063 | 0.80 | 0.04 | ok |
| fishing-collapse | 6 | 9 | 5 | 0 | 0 | 3 | 0.089 | 0.33 | 0.04 | ok |
| fixes-that-fail | 4 | 5 | 2 | 0 | 0 | 2 | 0.133 | 0.50 | 0.02 | ok |
| induced-demand | 5 | 7 | 4 | 0 | 0 | 3 | 0.215 | 0.00 | 0.02 | ok |
| learning-flywheel | 4 | 5 | 2 | 0 | 0 | 2 | 0.145 | 0.50 | 0.02 | ok |
| limits-to-growth | 5 | 7 | 3 | 1 | 0 | 3 | 0.234 | 0.60 | 0.06 | ok |
| population-logistic | 4 | 6 | 3 | 0 | 1 | 3 | 0.192 | 0.50 | 0.02 | ok |
| renewable-resource | 5 | 7 | 3 | 0 | 0 | 1 | 0.186 | 0.40 | 0.02 | ok |
| shifting-the-burden | 5 | 8 | 4 | 0 | 0 | 2 | 0.036 | 0.80 | 0.02 | ok |
| soil-erosion | 6 | 8 | 3 | 0 | 1 | 3 | 0.187 | 0.33 | 0.02 | ok |
| tragedy-of-the-commons | 5 | 6 | 2 | 0 | 0 | 2 | 0.182 | 0.00 | 0.02 | ok |
| urban-migration | 6 | 8 | 3 | 1 | 0 | 4 | 0.123 | 0.33 | 0.02 | ok |
| wage-price-spiral | 5 | 6 | 2 | 0 | 0 | 2 | 0.013 | 0.00 | 0.04 | ok |

### Graphviz neato

| 图 | n | m | loops | 交叉 | 框压线 | 净距违规 | CV | 行对齐率 | 耗时s | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|
| arms-race | 4 | 4 | 1 | 1 | 2 | 3 | 0.007 | 0.00 | 0.14 | ok |
| brand-flywheel | 6 | 8 | 3 | 0 | 0 | 2 | 0.043 | 0.00 | 0.02 | ok |
| bullwhip | 5 | 6 | 2 | 0 | 0 | 3 | 0.028 | 0.00 | 0.02 | ok |
| burnout-attrition | 5 | 6 | 2 | 0 | 2 | 4 | 0.122 | 0.00 | 0.02 | ok |
| classic-cld-growth-and-burden | 8 | 13 | 6 | 0 | 3 | 10 | 0.181 | 0.25 | 0.02 | ok |
| debt-spiral | 5 | 6 | 2 | 0 | 0 | 2 | 0.039 | 0.00 | 0.13 | ok |
| eroding-goals | 5 | 6 | 2 | 0 | 1 | 2 | 0.023 | 0.00 | 0.02 | ok |
| fishing-collapse | 6 | 9 | 5 | 0 | 0 | 1 | 0.053 | 0.00 | 0.13 | ok |
| fixes-that-fail | 4 | 5 | 2 | 0 | 2 | 2 | 0.122 | 0.00 | 0.13 | ok |
| induced-demand | 5 | 7 | 4 | 0 | 2 | 2 | 0.039 | 0.00 | 0.02 | ok |
| learning-flywheel | 4 | 5 | 2 | 0 | 2 | 2 | 0.122 | 0.00 | 0.02 | ok |
| limits-to-growth | 5 | 7 | 3 | 0 | 1 | 5 | 0.152 | 0.00 | 0.18 | ok |
| population-logistic | 4 | 6 | 3 | 0 | 0 | 1 | 0.009 | 0.00 | 0.02 | ok |
| renewable-resource | 5 | 7 | 3 | 0 | 0 | 1 | 0.007 | 0.00 | 0.02 | ok |
| shifting-the-burden | 5 | 8 | 4 | 0 | 1 | 3 | 0.023 | 0.00 | 0.02 | ok |
| soil-erosion | 6 | 8 | 3 | 0 | 2 | 2 | 0.186 | 0.67 | 0.02 | ok |
| tragedy-of-the-commons | 5 | 6 | 2 | 0 | 0 | 4 | 0.028 | 0.00 | 0.02 | ok |
| urban-migration | 6 | 8 | 3 | 0 | 4 | 5 | 0.313 | 0.00 | 0.02 | ok |
| wage-price-spiral | 5 | 6 | 2 | 0 | 0 | 4 | 0.023 | 0.00 | 0.13 | ok |

### Graphviz sfdp

| 图 | n | m | loops | 交叉 | 框压线 | 净距违规 | CV | 行对齐率 | 耗时s | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|
| arms-race | 4 | 4 | 1 | 0 | 0 | 0 | 0.001 | 0.00 | 0.13 | ok |
| brand-flywheel | 6 | 8 | 3 | 0 | 0 | 0 | 0.047 | 0.33 | 0.02 | ok |
| bullwhip | 5 | 6 | 2 | 0 | 0 | 0 | 0.173 | 0.60 | 0.02 | ok |
| burnout-attrition | 5 | 6 | 2 | 1 | 0 | 0 | 0.143 | 0.00 | 0.02 | ok |
| classic-cld-growth-and-burden | 8 | 13 | 6 | 1 | 0 | 0 | 0.309 | 0.00 | 0.03 | ok |
| debt-spiral | 5 | 6 | 2 | 0 | 0 | 0 | 0.039 | 0.00 | 0.02 | ok |
| eroding-goals | 5 | 6 | 2 | 0 | 0 | 0 | 0.129 | 0.80 | 0.02 | ok |
| fishing-collapse | 6 | 9 | 5 | 0 | 0 | 0 | 0.096 | 0.00 | 0.13 | ok |
| fixes-that-fail | 4 | 5 | 2 | 0 | 0 | 0 | 0.085 | 0.50 | 0.02 | ok |
| induced-demand | 5 | 7 | 4 | 0 | 0 | 0 | 0.036 | 0.00 | 0.02 | ok |
| learning-flywheel | 4 | 5 | 2 | 0 | 0 | 0 | 0.085 | 0.50 | 0.02 | ok |
| limits-to-growth | 5 | 7 | 3 | 1 | 0 | 0 | 0.234 | 0.00 | 0.03 | ok |
| population-logistic | 4 | 6 | 3 | 0 | 0 | 0 | 0.124 | 0.50 | 0.02 | ok |
| renewable-resource | 5 | 7 | 3 | 0 | 0 | 0 | 0.135 | 0.60 | 0.02 | ok |
| shifting-the-burden | 5 | 8 | 4 | 0 | 0 | 0 | 0.128 | 0.80 | 0.02 | ok |
| soil-erosion | 6 | 8 | 3 | 0 | 0 | 0 | 0.179 | 0.33 | 0.02 | ok |
| tragedy-of-the-commons | 5 | 6 | 2 | 0 | 0 | 0 | 0.179 | 0.60 | 0.03 | ok |
| urban-migration | 6 | 8 | 3 | 2 | 0 | 0 | 0.240 | 0.67 | 0.02 | ok |
| wage-price-spiral | 5 | 6 | 2 | 0 | 0 | 0 | 0.133 | 0.80 | 0.02 | ok |

### ELK layered

| 图 | n | m | loops | 交叉 | 框压线 | 净距违规 | CV | 行对齐率 | 耗时s | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|
| arms-race | 4 | 4 | 1 | 0 | 0 | 2 | 0.001 | 1.00 | 0.06 | ok |
| brand-flywheel | 6 | 8 | 3 | 0 | 0 | 3 | 0.236 | 0.67 | 0.09 | ok |
| bullwhip | 5 | 6 | 2 | 0 | 0 | 3 | 0.171 | 0.00 | 0.07 | ok |
| burnout-attrition | 5 | 6 | 2 | 0 | 0 | 4 | 0.203 | 0.60 | 0.07 | ok |
| classic-cld-growth-and-burden | 8 | 13 | 6 | 0 | 0 | 5 | 0.330 | 0.50 | 0.08 | ok |
| debt-spiral | 5 | 6 | 2 | 0 | 0 | 5 | 0.036 | 1.00 | 0.08 | ok |
| eroding-goals | 5 | 6 | 2 | 0 | 0 | 2 | 0.318 | 0.00 | 0.07 | ok |
| fishing-collapse | 6 | 9 | 5 | 1 | 0 | 4 | 0.122 | 0.83 | 0.07 | ok |
| fixes-that-fail | 4 | 5 | 2 | 0 | 0 | 3 | 0.222 | 0.50 | 0.06 | ok |
| induced-demand | 5 | 7 | 4 | 0 | 0 | 2 | 0.102 | 0.40 | 0.08 | ok |
| learning-flywheel | 4 | 5 | 2 | 0 | 0 | 2 | 0.278 | 0.50 | 0.08 | ok |
| limits-to-growth | 5 | 7 | 3 | 0 | 0 | 2 | 0.367 | 0.00 | 0.07 | ok |
| population-logistic | 4 | 6 | 3 | 0 | 0 | 2 | 0.228 | 0.50 | 0.07 | ok |
| renewable-resource | 5 | 7 | 3 | 0 | 0 | 2 | 0.190 | 0.00 | 0.06 | ok |
| shifting-the-burden | 5 | 8 | 4 | 0 | 0 | 2 | 0.272 | 0.00 | 0.08 | ok |
| soil-erosion | 6 | 8 | 3 | 0 | 0 | 5 | 0.151 | 0.50 | 0.08 | ok |
| tragedy-of-the-commons | 5 | 6 | 2 | 0 | 0 | 2 | 0.279 | 0.40 | 0.07 | ok |
| urban-migration | 6 | 8 | 3 | 0 | 0 | 5 | 0.249 | 0.33 | 0.06 | ok |
| wage-price-spiral | 5 | 6 | 2 | 0 | 0 | 2 | 0.199 | 0.00 | 0.07 | ok |

### stdraw WS2 精确层 cr(G) 参考真值（classic 全量）

| 图 | cr(G) | proven_optimal | coverage | 耗时s | 状态 |
|---|---|---|---|---|---|
| arms-race | 0 | True | full | 0.39 | ok |
| brand-flywheel | 0 | True | full | 0.43 | ok |
| bullwhip | 0 | True | full | 0.40 | ok |
| burnout-attrition | 0 | True | full | 0.49 | ok |
| classic-cld-growth-and-burden | 0 | True | full | 0.52 | ok |
| debt-spiral | 0 | True | full | 0.37 | ok |
| eroding-goals | 0 | True | full | 0.40 | ok |
| fishing-collapse | 0 | True | full | 0.39 | ok |
| fixes-that-fail | 0 | True | full | 0.36 | ok |
| induced-demand | 0 | True | full | 0.40 | ok |
| learning-flywheel | 0 | True | full | 0.36 | ok |
| limits-to-growth | 0 | True | full | 0.41 | ok |
| population-logistic | 0 | True | full | 0.36 | ok |
| renewable-resource | 0 | True | full | 0.40 | ok |
| shifting-the-burden | 0 | True | full | 0.38 | ok |
| soil-erosion | 0 | True | full | 0.39 | ok |
| tragedy-of-the-commons | 0 | True | full | 0.39 | ok |
| urban-migration | 0 | True | full | 0.39 | ok |
| wage-price-spiral | 0 | True | full | 0.39 | ok |

## §4 随机稀疏图族（n∈{10,20,30,50} × 20 张，seed 可复现）聚合

聚合口径：均值（交叉/压线/违规/CV/对齐），中位耗时，DNF 率如实单列。

| 工具 | n | 张数 | 交叉均值 | 框压线均值 | 净距违规均值 | CV均值 | 行对齐均值 | 耗时的中位数s | DNF率 |
|---|---|---|---|---|---|---|---|---|---|
| stdraw·ortho(构造法) | 10 | 20 | 0.0 | 2.6 | 4.6 | 0.325 | 0.67 | 0.03 | 20% |
| stdraw·ortho(构造法) | 20 | 20 | 0.0 | 5.0 | 10.0 | 0.455 | 0.85 | 0.21 | 95% |
| stdraw·ortho(构造法) | 30 | 20 | — | — | — | — | — | — | 100% |
| stdraw·ortho(构造法) | 50 | 20 | — | — | — | — | — | — | 100% |
| stdraw·auto(WS3布线) | 10 | 20 | 2.2 | 0.0 | 0.2 | 0.185 | 0.81 | 54.48 | 0% |
| stdraw·auto(WS3布线) | 20 | 20 | 32.0 | 0.9 | 8.2 | 0.195 | 0.91 | 21.10 | 0% |
| stdraw·auto(WS3布线) | 30 | 20 | 100.1 | 4.2 | 20.7 | 0.162 | 0.96 | 31.75 | 0% |
| stdraw·auto(WS3布线) | 50 | 20 | 421.5 | 13.1 | 49.1 | 0.197 | 0.98 | 75.87 | 5% |
| stdraw·auto+WS2(精确层) | 10 | 20 | 2.2 | 0.0 | 0.2 | 0.185 | 0.81 | 54.91 | 0% |
| stdraw·auto+WS2(精确层) | 20 | 20 | 32.0 | 0.9 | 8.2 | 0.195 | 0.91 | 24.17 | 0% |
| stdraw·auto+WS2(精确层) | 30 | 20 | 100.1 | 4.2 | 20.7 | 0.162 | 0.96 | 32.64 | 0% |
| stdraw·auto+WS2(精确层) | 50 | 20 | 421.5 | 13.1 | 49.1 | 0.197 | 0.98 | 75.87 | 5% |
| Graphviz dot | 10 | 20 | 1.9 | 0.0 | 7.0 | 0.133 | 0.84 | 0.02 | 0% |
| Graphviz dot | 20 | 20 | 13.4 | 0.5 | 21.5 | 0.190 | 0.94 | 0.03 | 0% |
| Graphviz dot | 30 | 20 | 31.4 | 2.1 | 39.0 | 0.178 | 0.97 | 0.02 | 0% |
| Graphviz dot | 50 | 20 | 98.9 | 11.6 | 94.8 | 0.192 | 0.98 | 0.03 | 0% |
| Graphviz neato | 10 | 20 | 0.1 | 5.0 | 11.8 | 0.248 | 0.21 | 0.02 | 0% |
| Graphviz neato | 20 | 20 | 0.2 | 16.7 | 36.9 | 0.364 | 0.31 | 0.03 | 0% |
| Graphviz neato | 30 | 20 | 0.7 | 30.4 | 63.5 | 0.383 | 0.45 | 0.03 | 0% |
| Graphviz neato | 50 | 20 | 2.4 | 85.7 | 167.6 | 0.483 | 0.55 | 0.03 | 0% |
| Graphviz sfdp | 10 | 20 | 1.8 | 0.9 | 1.2 | 0.226 | 0.06 | 0.02 | 0% |
| Graphviz sfdp | 20 | 20 | 8.1 | 5.0 | 7.5 | 0.287 | 0.17 | 0.03 | 0% |
| Graphviz sfdp | 30 | 20 | 10.4 | 10.3 | 15.3 | 0.316 | 0.23 | 0.02 | 0% |
| Graphviz sfdp | 50 | 20 | 28.9 | 38.8 | 58.9 | 0.400 | 0.34 | 0.03 | 0% |
| ELK layered | 10 | 20 | 2.4 | 0.0 | 8.3 | 0.237 | 0.30 | 0.09 | 0% |
| ELK layered | 20 | 20 | 16.2 | 0.0 | 16.4 | 0.322 | 0.36 | 0.11 | 0% |
| ELK layered | 30 | 20 | 47.0 | 0.0 | 24.1 | 0.384 | 0.31 | 0.13 | 0% |
| ELK layered | 50 | 20 | 163.2 | 0.0 | 41.1 | 0.431 | 0.33 | 0.14 | 0% |

### 构造法（ortho-v1）的可平面分层实况（随机族）

- n=10：可平面 16/20，ortho 成功出图 16，不可平面诚实跳过 4
- n=20：可平面 1/20，ortho 成功出图 1，不可平面诚实跳过 19
- n=30：可平面 0/20，ortho 成功出图 0，不可平面诚实跳过 20
- n=50：可平面 0/20，ortho 成功出图 0，不可平面诚实跳过 20

## §5 stdraw auto-v2 可扩展性瓶颈（实测定位 → WS5 修复）

- **WS4 实测（修复前）**：n10 每张 ~285s（打点：CP-SAT 定位 <1s，其余全耗在 `_polish` 的每候选横移全图重布线 route_all，n10 ≈121 次/图）；n≥20 在 100s 预算 全 DNF，n30/n50 在 300-420s 预算亦不完成；
- **根因修正（WS5 打点证据，修正 WS4 §5 的归因）**：`_polish` 带 core≤10 门，n≥20 根本不执行——它只解释 n≤10 慢，**不是** n≥20 DNF 的根因；n≥20 的真瓶颈是 `_cpsat_positions` 把交叉对 O(m²) 布尔化后**求到全局最优**：random-n20-i00 实测 5min+ 未返回（construct 定位下 route_all 同图仅 8.2s，n50 冷缓存 410.6s）；
- **WS5 修复**：① n>10 的 CP-SAT 定位改用确定性时间预算 `max_deterministic_time=8`（操作计数口径，非墙钟——输出仍逐字节可复现；小图 ≤10 不受预算约束、照常证最优，输出与修复前逐字节一致）；② 布线层精确等价提速（`visibility._visible` / `routing._evaluate` 包围盒下界剪枝 + `route_all` routed_segs 增量维护）——route_all 指纹逐位不变，墙钟 n20 8.2→2.3s、n30 53.9→11.0s、n50 410.6→62.1s；③ 等价性验证：classic 19 张 + n10 抽样 2 张 layout.json sha256 新旧逐字节一致（21/21）；`_visible` 差分对拍 3000 例 0 差异；
- **修复后实况（本表 §4 为准）**：stdraw-auto n20 出图 20/20，n30 出图 20/20，n50 出图 19/20（修复前 n≥20 全 DNF）；n10 布局输出逐字节不变、耗时下降（同机同条件 ~285s → 45-60s/张）；定位质量口径变化如实声明：n>10 的解从「证到最优」变为「8det 预算内最优 incumbent」，layout.json meta 的 solver_status/solver_det_budget 字段如实标注；
- 边界（诚实）：随机稀疏图 n≥20 的框压线/净距不再是 0（布线目标是惩罚最小化而非定理保证，稠密随机图存在无零压线候选的情形——§4 框压线均值即实测值）；运行时间仍慢基线 2~3 个数量级；`_polish`（布线可行性回喂定位）仍只在 n≤10 执行，n≥20 的定位质量依赖 CP-SAT 预算内 incumbent + 构造法兜底。

## §5b WS3-Q 布线质量返修（2026-11-06，随机 n10 抽样 4/10 例 check1/check3 fail 的根因与修复；人工修正记录，非 collect.py 生成）

- **现象**：`corpus/random` 抽样 10 张 n10 中 4 张 auto 配方 CLI exit 1（check1 交叉 3~5 > 门 2；i01 另有 check3 净距 11.6px < 16）；d483639 复跑证实为存量问题，非 F3 viewBox 返修引入；
- **根因（实测定位）**：4 张图抽象拓扑**全部可平面**（networkx Boyer-Myrvold），交叉不是数学边界而是**摆放层质量**：DAG 最长路行分配 + CP-SAT 保守交叉代理（跳过端点同行/区间不重叠的对）+ 弱 polish 把「拓扑交错对」顶到 3~11 个，贪心路由只能躲掉一部分；另有结构性死角——单 lane 候选全部压在中点行 y 上，被中间行的水平连接器整体封死（i04 的 N02->N03 全候选 cross≥1）；pass2 坐标下降存在「互为最优」僵局（对每条边各自局部最优、成对交叉稳定）；
- **修复（三手，全部确定性、门控触发——布线硬门 [交叉>2 / 净距<16 / 锚点违例 / 压线] 本来达标的布局零扰动）**：① 布局层：确定性 (行, 行内序) 重排局部搜索（最小化拓扑交错对，允许跨行移动）→ 24px 重打包 → hard-gate polish（净距/锚点硬罚）；② 路由层：`Router(quality=True)` 扩充跨多行 stair 候选（a/b 行旁行间走廊 + 中间行侧外垂直，结构上不进中间行卡带）；③ 交叉对联合重定线 `joint_reroute`（对当前交叉边对联合枚举候选组合取总评最优，打破坐标下降僵局）；三手在同一门控元组（交叉对/净距违例/锚点违例/压线）下与原摆放择优；
- **修复后实测（同机，rebased 于 v0.5.0 ring layout 之上，1f3d82f）**：4 张失败例全部 exit 0（i00 交叉 5→2），确定性两遍逐字节一致；随机 n10 抽样 10/10 exit 0。v0.5.0 的 ring 判定截胡 9/10 张抽样与 classic 全域，但 `_ring_trial` 自带硬门代理、不达门即回退分层路径——本卡门控修复在该回退路径上生效；classic 19 张与随机 n10 另 4 张（i02/i03/i07/i08/i09）相对 v0.5.0 **逐字节不变**；仅 i06 因内部门比 CLI 门更严（router 理论口径/压线余量）触发重排产生**漂移但全过**（交叉 2、净距 17.5px、锚点 0 违例，确定性已验），漂移如实记录；
- **回归门**：`tests/ci_checks.py` 新增 B2 层——4 张抽样 exit 0 + 硬门 + 两遍确定性断言；
- **边界（诚实）**：门控重排路径每例新增 ~1-2min（hard-gate polish 的逐候选全图重布线），n10 随机族总耗时仍在预算内；n≥20 不走门控（core≤10 门），行为不变；全随机族 80 张的完整 re-bench 未重跑（classic 不受影响，随机族数字以本节修正为准，待下次全量 bench 刷新 §4）。

## §6 OGDF：未运行（构建成本如实评估）

- 本机（Windows 11，Medium 完整性，无 cmake / 无 MSVC cl）不具备 OGDF 构建工具链，OGDF 无官方 Windows 预编译分发；按卡面预案降级为**引用其论文公开数据**做数值对照：OGDF 团队在 Rome graphs 上的精确/启发式交叉数结果（Chimani et al.）与本基准不可直接同题——本基准图集（经典 CLD + 合成稀疏图）不在其公开逐图结果内，故只作量级对照并在结论中明示口径差异；
- 因此「对比 OGDF」在本报告中的诚实表述是：**未同题运行，不参与胜负判定**；stdraw WS2 精确层的 proven-optimal 证书（K5/K3,3/Petersen 等）与 OGDF 的 ExactLib/subgraph 抓逼在方法学上同属精确交叉数路线，文献口径见 docs/crossing-exact.md。

## §7 逐指标自动结论（classic 全量均值 + 随机族；由 collect.py 机械生成，无人工修饰）

### classic 均值

| 工具 | 交叉均值 | 框压线均值 | 净距违规均值 | CV均值 | 行对齐均值 | 耗时均值s | 成功率 |
|---|---|---|---|---|---|---|---|
| stdraw·ortho(构造法) | 0.0 | 1.4 | 1.7 | 0.296 | 0.48 | 0.01 | 19/19 |
| stdraw·auto(WS3布线) | 0.2 | 0.0 | 0.0 | 0.133 | 0.34 | 10.02 | 19/19 |
| stdraw·auto+WS2(精确层) | 0.2 | 0.0 | 0.0 | 0.133 | 0.34 | 10.42 | 19/19 |
| Graphviz dot | 0.2 | 0.1 | 2.6 | 0.139 | 0.34 | 0.03 | 19/19 |
| Graphviz neato | 0.1 | 1.2 | 3.1 | 0.080 | 0.05 | 0.06 | 19/19 |
| Graphviz sfdp | 0.3 | 0.0 | 0.0 | 0.131 | 0.37 | 0.03 | 19/19 |
| ELK layered | 0.1 | 0.0 | 3.0 | 0.208 | 0.41 | 0.07 | 19/19 |

### classic 交叉数逐工具对比（vs stdraw-auto 基准行）

- stdraw·ortho(构造法)：交叉均值 0.00 低于 stdraw-auto 0.16（**stdraw-auto 落后**）
- stdraw·auto+WS2(精确层)：与 stdraw-auto 打平（0.16）
- Graphviz dot：与 stdraw-auto 打平（0.16）
- Graphviz neato：交叉均值 0.05 低于 stdraw-auto 0.16（**stdraw-auto 落后**）
- Graphviz sfdp：交叉均值 0.26 高于 stdraw-auto 0.16（**stdraw-auto 领先**）
- ELK layered：交叉均值 0.05 低于 stdraw-auto 0.16（**stdraw-auto 落后**）

### 随机族可用性结论

- stdraw·ortho(构造法)：n10 成功 16/20，n20 成功 1/20
- stdraw·auto(WS3布线)：n10 成功 20/20，n20 成功 20/20，n50 成功 19/20
- stdraw·auto+WS2(精确层)：n10 成功 20/20，n20 成功 20/20，n50 成功 19/20
- Graphviz dot：n10 成功 20/20，n20 成功 20/20，n50 成功 20/20
- Graphviz neato：n10 成功 20/20，n20 成功 20/20，n50 成功 20/20
- Graphviz sfdp：n10 成功 20/20，n20 成功 20/20，n50 成功 20/20
- ELK layered：n10 成功 20/20，n20 成功 20/20，n50 成功 20/20

## §8 「最好」主张的可辩护措辞（草案，待 default 复核）

以下措辞只允许引用本报告表格中实际出现的数字与口径：

1. 在经典 CLD 语料上，stdraw auto-v2 于交叉数/框压线/净距/行对齐各列的每项表现，以 §7 classic 均值表为准逐列对比，不合并总分；
2. 任何「优于 Graphviz/ELK」的主张必须同时注明：ELK/Graphviz 为通用图布局工具，未针对 CLD 卡片式画法调优；stdraw 的比较优势限定在同输入同框尺寸的 CLD 场景；
3. 随机族 n≥20 的全 DNF 已由 WS5 修复（§5；出图率见 §4），但运行时间仍慢基线 2~3 个数量级、且随机族框压线/净距非 0（惩罚最小化非定理保证）——任何「全规模最好」主张**仍不成立**，README 只可主张「经典 CLD 小图域」内的领先（且以 §7 数字为准）；
4. OGDF 未同题运行，不作对比对象引用（§6 口径）。

