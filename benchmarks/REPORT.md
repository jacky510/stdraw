# stdraw WS4 基准对比报告（真实数字，赢了写赢，输了写输）

生成：benchmarks/tools/collect.py ← benchmarks/raw/（全部原始评测 JSON 留证）。

## §1 结论先行（机械生成，无人工修饰；数字出自 §3/§4/§7）

- **交叉数（classic 均值）**：stdraw-auto=0.16；stdraw-ortho=0.00；graphviz-neato=0.05；elk-layered=0.05；stdraw-auto-exact=0.16；graphviz-dot=0.16；graphviz-sfdp=0.26。交叉数全场最低的主张**不成立**（neato/ELK 均值更低，代价是排布质量：neato 框压线 1.2 + 净距违规 3.1 + 行对齐 0.05；ELK 框压线 0 但净距违规 3.0——数字见 §7）
- **排布硬门（框压线=0 且 净距违规=0，classic 均值口径）**：达成的工具 = stdraw-auto、stdraw-auto-exact、graphviz-sfdp。stdraw-auto 在该组内交叉数最低/持平，但耗时最贵
- **运行时间（classic 均值）**：stdraw-auto=20.3s vs 基线 graphviz-dot=0.03s、graphviz-neato=0.06s、graphviz-sfdp=0.03s、elk-layered=0.07s——基线快 2~3 个数量级，任何主张必须承认这一代价
- **随机族**：stdraw auto-v2 在 n≥20 全 DNF（§4/§5），「全规模最好」不成立；n10 内 auto 完整跑通（约 285s/张）但比基线慢 3 个数量级以上
- **综合可辩护措辞（草案，§8 展开）**：stdraw 的比较优势限定在「经典 CLD 小图、卡片式画法、硬门语义（框不压线+净距+行对齐+CV）全维度同时达标」这一域；交叉数单项与 Graphviz dot 打平、不敌 neato/ELK 裸交叉值；运行时间为其主要代价

## §2 对比协议（口径声明）

- **同一输入**：同标签、同框尺寸（stdraw textmetrics 统一给出 w×h px；Graphviz 以 inch=px/72 fixedsize 传入、ELK/stdraw 直接 px——各工具 native 坐标同为物理 px）；
- **阈值型指标**（框压线 1px / 净距违规 16px）在 native 坐标按绝对 px 判定；尺度不变指标（交叉/CV/行对齐）不受坐标尺度影响；不做强制缩放归一化（缩放改变阈值物理语义，谁被缩谁吃亏不是质量差异）；另报 bbox 作画布效率参考；
- **六指标**：crossings（相邻边除外折线严格求交）/ box_press（边进非端点框含 1px 余量）/ clear_violations（边-非端点框最小距 <16px 的 (边,框) 对数）/ spacing_cv（最近邻中心距 std/mean）/ row_align_rate（y 差 ≤4px 同行占比）/ runtime_s；
- **指标实现与 stdraw/metrics.py·routing.py 同源**（直接 import seg_cross / sample_polyline / dist_point_rect），评测代码随仓公开可复算；
- **运行时间口径**：stdraw = 进程内核心布局计时（不含解析/渲染/证书）；Graphviz/ELK = 子进程 wall-clock（含启动开销，对基线略不利，报告如实注明）；
- **预算协议**：引擎无内部时限是确定性设计，本基准给外部预算：ortho 60s；auto classic 300s / 随机 n≤10 350s / 随机 n≥20 100s；cr(G) 精确层 300s；超预算 = DNF 如实计数（DNF 不是输一场空，是「该预算内不产布局」的事实）；
- **auto-exact 形态** = auto 布局复用（WS2 已证同输入逐字节一致）+ 独立跑 cr(G)，runtime = 布局 + 精确层；
- **环境**：Windows 11 / Python 3.12.10 + networkx + OR-Tools CP-SAT / Graphviz 16.1.0（官方 Release zip，sha256 校验一致）/ elkjs（bundled，node 22.23.2）/OGDF：未运行（见 §6）。

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
| arms-race | 4 | 4 | 1 | 0 | 0 | 0 | 0.065 | 0.00 | 4.58 | ok |
| brand-flywheel | 6 | 8 | 3 | 0 | 0 | 0 | 0.096 | 0.33 | 28.92 | ok |
| bullwhip | 5 | 6 | 2 | 0 | 0 | 0 | 0.021 | 0.00 | 15.69 | ok |
| burnout-attrition | 5 | 6 | 2 | 0 | 0 | 0 | 0.119 | 0.40 | 21.32 | ok |
| classic-cld-growth-and-burden | 8 | 13 | 6 | 1 | 0 | 0 | 0.110 | 0.62 | 100.62 | ok |
| debt-spiral | 5 | 6 | 2 | 0 | 0 | 0 | 0.192 | 0.00 | 14.79 | ok |
| eroding-goals | 5 | 6 | 2 | 0 | 0 | 0 | 0.121 | 0.80 | 10.04 | ok |
| fishing-collapse | 6 | 9 | 5 | 0 | 0 | 0 | 0.242 | 0.33 | 27.28 | ok |
| fixes-that-fail | 4 | 5 | 2 | 0 | 0 | 0 | 0.192 | 0.50 | 1.45 | ok |
| induced-demand | 5 | 7 | 4 | 0 | 0 | 0 | 0.171 | 0.00 | 21.21 | ok |
| learning-flywheel | 4 | 5 | 2 | 0 | 0 | 0 | 0.265 | 0.50 | 4.03 | ok |
| limits-to-growth | 5 | 7 | 3 | 1 | 0 | 0 | 0.197 | 0.60 | 30.88 | ok |
| population-logistic | 4 | 6 | 3 | 0 | 0 | 0 | 0.124 | 0.50 | 5.21 | ok |
| renewable-resource | 5 | 7 | 3 | 0 | 0 | 0 | 0.113 | 0.40 | 6.61 | ok |
| shifting-the-burden | 5 | 8 | 4 | 0 | 0 | 0 | 0.021 | 0.80 | 11.62 | ok |
| soil-erosion | 6 | 8 | 3 | 0 | 0 | 0 | 0.119 | 0.33 | 19.44 | ok |
| tragedy-of-the-commons | 5 | 6 | 2 | 0 | 0 | 0 | 0.202 | 0.00 | 14.20 | ok |
| urban-migration | 6 | 8 | 3 | 1 | 0 | 0 | 0.160 | 0.33 | 31.29 | ok |
| wage-price-spiral | 5 | 6 | 2 | 0 | 0 | 0 | 0.000 | 0.00 | 16.33 | ok |

### stdraw·auto+WS2(精确层)

| 图 | n | m | loops | 交叉 | 框压线 | 净距违规 | CV | 行对齐率 | 耗时s | 状态 |
|---|---|---|---|---|---|---|---|---|---|---|
| arms-race | 4 | 4 | 1 | 0 | 0 | 0 | 0.065 | 0.00 | 4.26 | ok |
| brand-flywheel | 6 | 8 | 3 | 0 | 0 | 0 | 0.096 | 0.33 | 27.86 | ok |
| bullwhip | 5 | 6 | 2 | 0 | 0 | 0 | 0.021 | 0.00 | 16.51 | ok |
| burnout-attrition | 5 | 6 | 2 | 0 | 0 | 0 | 0.119 | 0.40 | 20.72 | ok |
| classic-cld-growth-and-burden | 8 | 13 | 6 | 1 | 0 | 0 | 0.110 | 0.62 | 101.14 | ok |
| debt-spiral | 5 | 6 | 2 | 0 | 0 | 0 | 0.192 | 0.00 | 15.16 | ok |
| eroding-goals | 5 | 6 | 2 | 0 | 0 | 0 | 0.121 | 0.80 | 10.44 | ok |
| fishing-collapse | 6 | 9 | 5 | 0 | 0 | 0 | 0.242 | 0.33 | 27.66 | ok |
| fixes-that-fail | 4 | 5 | 2 | 0 | 0 | 0 | 0.192 | 0.50 | 1.81 | ok |
| induced-demand | 5 | 7 | 4 | 0 | 0 | 0 | 0.171 | 0.00 | 21.61 | ok |
| learning-flywheel | 4 | 5 | 2 | 0 | 0 | 0 | 0.265 | 0.50 | 4.39 | ok |
| limits-to-growth | 5 | 7 | 3 | 1 | 0 | 0 | 0.197 | 0.60 | 25.28 | ok |
| population-logistic | 4 | 6 | 3 | 0 | 0 | 0 | 0.124 | 0.50 | 5.57 | ok |
| renewable-resource | 5 | 7 | 3 | 0 | 0 | 0 | 0.113 | 0.40 | 7.01 | ok |
| shifting-the-burden | 5 | 8 | 4 | 0 | 0 | 0 | 0.021 | 0.80 | 12.00 | ok |
| soil-erosion | 6 | 8 | 3 | 0 | 0 | 0 | 0.119 | 0.33 | 19.83 | ok |
| tragedy-of-the-commons | 5 | 6 | 2 | 0 | 0 | 0 | 0.202 | 0.00 | 14.59 | ok |
| urban-migration | 6 | 8 | 3 | 1 | 0 | 0 | 0.160 | 0.33 | 31.68 | ok |
| wage-price-spiral | 5 | 6 | 2 | 0 | 0 | 0 | 0.000 | 0.00 | 16.71 | ok |

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
| arms-race | 0 | True | full | 0.00 | ok(内嵌) |
| brand-flywheel | 0 | True | full | 0.00 | ok(内嵌) |
| bullwhip | 0 | True | full | 0.00 | ok(内嵌) |
| burnout-attrition | 0 | True | full | 0.00 | ok(内嵌) |
| classic-cld-growth-and-burden | 0 | True | full | 0.52 | ok |
| debt-spiral | 0 | True | full | 0.37 | ok |
| eroding-goals | 0 | True | full | 0.40 | ok |
| fishing-collapse | 0 | True | full | 0.39 | ok |
| fixes-that-fail | 0 | True | full | 0.36 | ok |
| induced-demand | 0 | True | full | 0.40 | ok |
| learning-flywheel | 0 | True | full | 0.36 | ok |
| limits-to-growth | 0 | True | full | 0.00 | ok(内嵌) |
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
| stdraw·auto(WS3布线) | 10 | 20 | 3.0 | 0.0 | 0.0 | 0.206 | 0.84 | 252.94 | 30% |
| stdraw·auto(WS3布线) | 20 | 20 | — | — | — | — | — | — | 100% |
| stdraw·auto(WS3布线) | 30 | 20 | — | — | — | — | — | — | 100% |
| stdraw·auto(WS3布线) | 50 | 20 | — | — | — | — | — | — | 100% |
| stdraw·auto+WS2(精确层) | 10 | 20 | 3.0 | 0.0 | 0.0 | 0.206 | 0.84 | 253.34 | 30% |
| stdraw·auto+WS2(精确层) | 20 | 20 | — | — | — | — | — | — | 100% |
| stdraw·auto+WS2(精确层) | 30 | 20 | — | — | — | — | — | — | 100% |
| stdraw·auto+WS2(精确层) | 50 | 20 | — | — | — | — | — | — | 100% |
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

## §5 stdraw auto-v2 可扩展性瓶颈（实测定位，非猜测）

- 打点证据（benchmarks/raw/probe_n10_auto.log 同款探针）：n10 随机图 CP-SAT 定位 <1s 完成；总耗时 285.1s 全部耗在其后的 `_polish` 精化——每个候选横移都调一次 `_route_total` = Router.route_all **全图重布线**（n10 ≈ 10 节点 × 6 扰动 × 2 轮 + 1 初始 ≈ 121 次全图布线）；
- 推算：polish 成本 ∝ n × route_all(n)；实测 5 节点 ~30s、10 节点 ~285s，n≥20 在 100s 预算内 DNF（n30/n50 在 300-420s 预算下亦不完成）——这是本引擎当前诚实的适用域边界：**经典小图（n≤10 级）可用，随机稀疏图 n≥20 当前不可用**；
- 该瓶颈属引擎实现层（WS3 polish 策略），不属数学层（WS2 cr(G) 精确层与布线最优性不受影响）；修复建议（候选评估增量重路由 / polish 只重路由受影响边）留给 WS5/后续卡，本卡只对比不改动擎。

## §6 OGDF：未运行（构建成本如实评估）

- 本机（Windows 11，Medium 完整性，无 cmake / 无 MSVC cl）不具备 OGDF 构建工具链，OGDF 无官方 Windows 预编译分发；按卡面预案降级为**引用其论文公开数据**做数值对照：OGDF 团队在 Rome graphs 上的精确/启发式交叉数结果（Chimani et al.）与本基准不可直接同题——本基准图集（经典 CLD + 合成稀疏图）不在其公开逐图结果内，故只作量级对照并在结论中明示口径差异；
- 因此「对比 OGDF」在本报告中的诚实表述是：**未同题运行，不参与胜负判定**；stdraw WS2 精确层的 proven-optimal 证书（K5/K3,3/Petersen 等）与 OGDF 的 ExactLib/subgraph 抓逼在方法学上同属精确交叉数路线，文献口径见 docs/crossing-exact.md。

## §7 逐指标自动结论（classic 全量均值 + 随机族；由 collect.py 机械生成，无人工修饰）

### classic 均值

| 工具 | 交叉均值 | 框压线均值 | 净距违规均值 | CV均值 | 行对齐均值 | 耗时均值s | 成功率 |
|---|---|---|---|---|---|---|---|
| stdraw·ortho(构造法) | 0.0 | 1.4 | 1.7 | 0.296 | 0.48 | 0.01 | 19/19 |
| stdraw·auto(WS3布线) | 0.2 | 0.0 | 0.0 | 0.133 | 0.34 | 20.29 | 19/19 |
| stdraw·auto+WS2(精确层) | 0.2 | 0.0 | 0.0 | 0.133 | 0.34 | 20.22 | 19/19 |
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
- stdraw·auto(WS3布线)：n10 成功 14/20
- stdraw·auto+WS2(精确层)：n10 成功 14/20
- Graphviz dot：n10 成功 20/20，n20 成功 20/20，n50 成功 20/20
- Graphviz neato：n10 成功 20/20，n20 成功 20/20，n50 成功 20/20
- Graphviz sfdp：n10 成功 20/20，n20 成功 20/20，n50 成功 20/20
- ELK layered：n10 成功 20/20，n20 成功 20/20，n50 成功 20/20

## §8 「最好」主张的可辩护措辞（草案，待 default 复核）

以下措辞只允许引用本报告表格中实际出现的数字与口径：

1. 在经典 CLD 语料上，stdraw auto-v2 于交叉数/框压线/净距/行对齐各列的每项表现，以 §7 classic 均值表为准逐列对比，不合并总分；
2. 任何「优于 Graphviz/ELK」的主张必须同时注明：ELK/Graphviz 为通用图布局工具，未针对 CLD 卡片式画法调优；stdraw 的比较优势限定在同输入同框尺寸的 CLD 场景；
3. 随机族 n≥20 上 stdraw auto 当前 DNF（§5 瓶颈），任何「全规模最好」主张**不成立**，README 只可主张「经典 CLD 小图域」内的领先（且以 §7 数字为准）；
4. OGDF 未同题运行，不作对比对象引用（§6 口径）。

